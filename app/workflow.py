import asyncio
import time
import uuid
from contextlib import suppress
from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from app.budget import budget_for_job
from app.generation_models import (
    Draft,
    Evidence,
    Plan,
    Review,
    ReviewDraft,
    WritingReview,
)
from app.generation_service import GenerationService
from app.model_client import ModelOutputError
from app.models import resume_hash
from app.providers import ProviderError
from app.skill import validate_draft
from app.store import Conflict


class StaleRun(Exception):
    pass


class Workflow(GenerationService):
    def __init__(self, *args):
        super().__init__(*args)
        self._signal = asyncio.Event()
        self._worker = None
        self._active = None
        self.execution_lock = asyncio.Lock()
        self.service_warning = ""

    async def start(self):
        self.jobs.recover_unfinished()
        self._worker = asyncio.create_task(self._loop())

    async def close(self):
        if self._worker:
            self._worker.cancel()
            with suppress(asyncio.CancelledError):
                await self._worker
        self.jobs.recover_unfinished()

    def wake(self):
        self._signal.set()

    def cancel(self, job_id):
        job = super().cancel(job_id)
        if self._active and self._active[0] == job_id:
            self._active[1].cancel()
        self.wake()
        return job

    async def _loop(self):
        needs_recovery = False
        while True:
            try:
                if needs_recovery:
                    self.jobs.recover_unfinished()
                    needs_recovery = False
                    self.service_warning = ""
                self._signal.clear()
                if not await self.run_one():
                    await self._signal.wait()
            except (SQLAlchemyError, OSError):
                self.service_warning = "本机存储暂时不可用，执行已暂停。请检查磁盘空间；恢复后任务会标为中断，由你明确继续。"
                needs_recovery = True
                await asyncio.sleep(1)

    def _change(self, job_id, token, apply):
        def guarded(job, connection):
            if job["state"] != "running" or job["run_token"] != token:
                raise StaleRun
            before = (job["stage"], job["revisions"])
            from app.phases import phase_key

            before_key = phase_key(job)
            apply(job, connection)
            if before != (job["stage"], job["revisions"]) or job["state"] in ("ready", "waiting_input"):
                job.setdefault("step_receipts", []).append({"step": f"{before[0]}:{before[1]}",
                    "next_stage": job["stage"], "state": job["state"], "calls": job["calls"],
                    "step_id": before_key, "engine_version": job.get("engine_version", "legacy")})

        return self.jobs.mutate(job_id, guarded)

    def _evidence_for(self, job, stage):
        evidence = job["evidence"]
        if stage not in ("draft", "revise"):
            return evidence
        plan = job.get("plan") or {}
        selected = plan.get("selected_fact_ids") if isinstance(plan, dict) else []
        if not isinstance(selected, list):
            selected = []
        answers = [fact_id for row in job.get("answer_context") or [] for fact_id in (row.get("fact_ids") or [])]
        allowed = {*selected, *answers, *(item["id"] for item in evidence if str(item.get("id", "")).startswith("profile-"))}
        return [item for item in evidence if item["id"] in allowed]

    def _context(self, job, stage):
        if stage == "supervise":
            from app.supervisor import supervisor_context

            return supervisor_context(job)
        reference = datetime.fromisoformat(job["created_at"]).astimezone(timezone(timedelta(hours=8)))
        context = {"instructions": job["skill"].get("stage_instructions", {}).get(stage, job["skill"]["instructions"]), "target_role": job["input"]["target_role"],
                   "reference_date": reference.date().isoformat(), "reference_timezone": "Asia/Shanghai",
                   "target_basis": {"type": "specific_jd" if job["input"]["jd"] else "maintained_general_profile",
                                    "jd": job["input"]["jd"], "role": job["skill"]["role"]},
                   "evidence": self._evidence_for(job, stage), "answer_context": job.get("answer_context", [])}
        policy = budget_for_job(job)
        context["_budget_policy"] = policy.model_dump()
        context["fixed_education"] = job["input"].get("education", [])
        context["loaded_resources"] = job["skill"].get("stage_resources", {}).get(stage, [])
        context["candidate_context"] = {"career_stage": job["input"].get("career_stage", "unspecified"),
                                        "has_career_gap": job["input"].get("has_career_gap", False)}
        if stage == "plan":
            context["question_budget"] = policy.question_limit if job["input"]["allow_questions"] and not job["answered"] else 0
        if stage in ("draft", "revise"):
            context["plan"] = job["plan"]
            if job.get("answered") and not job.get("answer_context"):
                context["followup_skipped"] = True
                context["instructions"] += ("\n用户跳过了追问。有材料的经历仍要写全，获奖、获评和原文中的数量结果不能删。"
                                            "不要输出没有材料的板块，也不要给空板块加缺口标记。"
                                            "某一条已经写了、但缺关键事实时，在该条末尾加【待补充：…】。"
                                            "同一事实出现两个口径时不要选边，加【待确认：…】。")
        if stage in ("review", "revise"):
            context["candidate"] = job["draft"]
        if stage == "revise":
            context["issues_to_fix"] = job["issues"]
            if job.get("repair_decision"):
                from app.supervisor import allowed_change_ids

                context["issues_to_fix"] = [job["issues"][i] for i in job["repair_decision"]["issue_indices"]]
                context["allowed_change_ids"] = sorted(allowed_change_ids(job))
                context["instructions"] += "\n仅修改allowed_change_ids范围；其余字段、段落及标识原样保留。document代表整篇。"
        if job.get("feedback_key") == f"{stage}:{job['revisions']}" and job.get("last_diagnostic"):
            context["validation_feedback"] = job["last_diagnostic"]
        return context

    async def _request(self, job, token, schema):
        stage = job["stage"]
        key = f"{stage}:{job['revisions']}"
        config = self.registry.get(job["config_revision"])
        policy = budget_for_job(job)

        def reserve(current, _):
            policy.validate_request(stage, current)
            current["calls"] += 1
            current["request_started"] = time.time()
            current["attempts"][key] = current["attempts"].get(key, 0) + 1

        job = self._change(job["id"], token, reserve)
        start = time.monotonic()
        error = None
        value = None
        try:
            timeout = policy.request_timeout_ms(stage, job["elapsed_ms"]) / 1000
            async with asyncio.timeout(timeout):
                context = self._context(job, stage)
                call = self.client.delegate(config, context) if stage == "supervise" else self.client.complete(config, stage, context, schema)
                task = asyncio.create_task(call)
                self._active = (job["id"], task)
                value = await task
            if stage in ("draft", "revise"):
                from app.phases import prepare_draft

                value.value = prepare_draft(job, value.value)
            if stage == "supervise":
                from app.supervisor import validate_decision

                validate_decision(job, value.value)
            if stage == "revise" and job.get("repair_decision"):
                from app.supervisor import validate_revision_scope

                validate_revision_scope(job, value.value)
            if isinstance(value.value, Plan) and any(ref not in {e["id"] for e in job["evidence"]} for ref in value.value.selected_fact_ids):
                raise ModelOutputError("选材引用不存在，不能继续起草")
            if isinstance(value.value, Review):
                candidate_type = ReviewDraft if job["mode"] == "recheck" else Draft
                allowed = {"document", *[c.id for c in candidate_type.model_validate(job["draft"]).claims()],
                           *[s["id"] for s in job["draft"]["sections"]], *[e["id"] for e in job["draft"].get("education", [])]}
                if any(i.item_id not in allowed for i in value.value.issues):
                    raise ModelOutputError("审阅问题没有定位到本次正文")
                if value.value.quality is not None:
                    source_ids = {e["id"] for e in job["evidence"]}
                    report = value.value.quality
                    if (any(set(row.item_ids) - allowed or set(row.evidence_ids) - source_ids for row in report.dimensions)
                            or any(topic.item_id not in allowed or set(topic.evidence_ids) - source_ids for topic in report.interview_topics)):
                        raise ModelOutputError("质量报告或面试讨论点引用了不存在的内容或材料")
        except asyncio.CancelledError:
            if self.jobs.get(job["id"])["state"] == "cancelled":
                raise StaleRun from None
            raise
        except TimeoutError:
            error = ProviderError("模型或任务执行超时；请求可能已计费，预算保留")
        except ProviderError as exc:
            error = exc
        finally:
            self._active = None
        elapsed = int((time.monotonic() - start) * 1000)

        def charge(current, _):
            current["elapsed_ms"] += elapsed
            current["request_started"] = None
            entry = {"stage": stage, "duration_ms": elapsed,
                     "usage": error.usage if isinstance(error, ModelOutputError) else value.usage if value and not error else {},
                     "outcome": "invalid_output" if isinstance(error, ModelOutputError) else "failed" if error else "ok"}
            if isinstance(error, ModelOutputError):
                failures = current.setdefault("invalid_outputs", {})
                failures[key] = failures.get(key, 0) + 1
                current.update(last_diagnostic=error.diagnostic, feedback_key=key)
                entry["diagnostic"] = error.diagnostic
            current["call_log"].append(entry)

        self._change(job["id"], token, charge)
        if error:
            raise error
        return value.value

    def _finish(self, job, token):
        return self._change(job["id"], token, self._finish_state)

    def _finish_state(self, current, connection):
        if current["mode"] == "recheck":
            resume_id = current["input"]["review_resume_id"]
            record = self.store._read(connection, resume_id)
            if record.revision != current["input"]["base_revision"] or resume_hash(record.content) != current["target_hash"]:
                raise Conflict("简历已在审阅期间变化，旧结论没有覆盖当前内容；请重新审阅")
            status = "passed" if current["review"] and current["review"]["verdict"] == "pass" and not any(
                i["severity"] == "blocking" for i in current["issues"]) else "blocked"
            info = record.ai.model_copy(update={"review_job_id": current["id"], "review_status": status,
                                                "content_hash": resume_hash(record.content), "issues": current["issues"],
                                                "manual_takeover": False, "quality": current["review"].get("quality") if current["review"] else None})
            self.store.write_ai(connection, resume_id, record.revision, info)
        current.update(state="ready", run_token="", error="")

    async def run_one(self):
        if self.execution_lock.locked():
            return False
        async with self.execution_lock:
            return await self._run_one()

    async def _run_one(self):
        job = self.jobs.claim_next()
        if not job:
            return False
        token = job["run_token"]
        try:
            from app.execution import run_engine

            await run_engine(self, job)
        except StaleRun:
            pass
        except (ProviderError, Conflict) as exc:
            with suppress(StaleRun):
                self._change(job["id"], token, lambda j, _, message=str(exc): j.update(state="failed", error=message, run_token="", request_started=None))
        except Exception:  # noqa: BLE001 -- do not log model text, user material or credentials.
            with suppress(StaleRun):
                self._change(job["id"], token, lambda j, _: j.update(state="failed", error="任务处理失败，材料与已完成步骤已保留，请查看后继续。", run_token="", request_started=None))
        return True

    async def _stage_call(self, job, token, stage, schema):
        from app.budget import budget_for_job
        from app.phases import StageResult, phase_key

        key = phase_key(job)
        try:
            output = await self._request(job, token, schema)
        except ModelOutputError:
            current = self.jobs.get(job["id"])
            policy = budget_for_job(current)
            retry = (current.get("invalid_outputs", {}).get(f"{stage}:{current['revisions']}", 0) < policy.max_invalid_outputs
                     and current["calls"] < policy.max_calls)
            if stage == "supervise":
                retry = retry and policy.can_supervise(current)
            if retry:
                return StageResult(stage, key, "retry")
            raise
        return StageResult(stage, key, "output", output)

    async def plan_stage(self, job, token):
        return await self._stage_call(job, token, "plan", Plan)

    async def draft_stage(self, job, token):
        return await self._stage_call(job, token, "draft", Draft)

    async def revise_stage(self, job, token):
        return await self._stage_call(job, token, "revise", Draft)

    async def review_stage(self, job, token):
        from app.phases import StageResult, phase_key

        candidate_type = ReviewDraft if job["mode"] == "recheck" else Draft
        candidate = candidate_type.model_validate(job["draft"])
        from app.gates import blocking_gates

        checks = [*validate_draft(candidate, [Evidence.model_validate(e) for e in job["evidence"]]), *blocking_gates(job, candidate)]
        if checks:
            return StageResult("review", phase_key(job), "program_issues", [i.model_dump() for i in checks])
        schema = WritingReview if job["skill"].get("stage_instructions") else Review
        return await self._stage_call(job, token, "review", schema)

    async def supervise_stage(self, job, token):
        from app.budget import budget_for_job
        from app.phases import StageResult, phase_key
        from app.supervisor import RepairDecision

        if not budget_for_job(job).can_supervise(job):
            return StageResult("supervise", phase_key(job), "stop")
        return await self._stage_call(job, token, "supervise", RepairDecision)

    def commit_stage(self, job, token, result):
        from app.phases import ALLOWED, phase_key, transition

        decision = []
        def commit(current, connection):
            if result.stage != current["stage"] or result.key != phase_key(current):
                raise StaleRun
            move = transition(current, result)
            if move.target not in ALLOWED[result.stage]:
                raise Conflict("阶段转移不合法，已有结果保留")
            current.update(move.updates)
            if move.target == "done":
                self._finish_state(current, connection)
            elif move.target == "wait":
                current.update(state="waiting_input", question_group=uuid.uuid4().hex, run_token="")
            else:
                current["stage"] = move.target
            decision.append(move.target)
        self._change(job["id"], token, commit)
        return decision[0]

    async def execute_step(self, job, token):
        # Compatibility adapter only: old tasks keep their pinned engine.
        handlers = {"plan": self.plan_stage, "draft": self.draft_stage, "review": self.review_stage,
                    "revise": self.revise_stage, "supervise": self.supervise_stage}
        result = await handlers[job["stage"]](job, token)
        self.commit_stage(job, token, result)

    @staticmethod
    def _can_revise(job):
        from app.budget import budget_for_job

        return budget_for_job(job).can_revise(job)
