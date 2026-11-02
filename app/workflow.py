import asyncio
import time
import uuid
from contextlib import suppress

from sqlalchemy.exc import SQLAlchemyError

from app.generation_models import (
    Draft,
    DraftEducation,
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
from app.skill import validate_draft, validate_quality
from app.store import Conflict
from app.writing_quality import editorial_quality, quality_issues


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
            apply(job, connection)

        return self.jobs.mutate(job_id, guarded)

    def _context(self, job, stage):
        context = {"instructions": job["skill"].get("stage_instructions", {}).get(stage, job["skill"]["instructions"]), "target_role": job["input"]["target_role"],
                   "reference_date": job["created_at"][:10], "reference_timezone": "UTC",
                   "target_basis": {"type": "specific_jd" if job["input"]["jd"] else "maintained_general_profile",
                                    "jd": job["input"]["jd"], "role": job["skill"]["role"]},
                   "evidence": job["evidence"], "answer_context": job.get("answer_context", [])}
        context["fixed_education"] = job["input"].get("education", [])
        context["loaded_resources"] = job["skill"].get("stage_resources", {}).get(stage, [])
        context["candidate_context"] = {"career_stage": job["input"].get("career_stage", "unspecified"),
                                        "has_career_gap": job["input"].get("has_career_gap", False)}
        if stage == "plan":
            context["question_budget"] = 3 if job["input"]["allow_questions"] and not job["answered"] else 0
        if stage in ("draft", "revise"):
            context["plan"] = job["plan"]
        if stage in ("review", "revise"):
            context["candidate"] = job["draft"]
        if stage == "revise":
            context["issues_to_fix"] = job["issues"]
        if job.get("feedback_key") == f"{stage}:{job['revisions']}" and job.get("last_diagnostic"):
            context["validation_feedback"] = job["last_diagnostic"]
        return context

    async def _request(self, job, token, schema):
        stage = job["stage"]
        key = f"{stage}:{job['revisions']}"
        config = self.registry.get(job["config_revision"])

        def reserve(current, _):
            if current["calls"] >= 8 or current["elapsed_ms"] >= 180000:
                raise ProviderError("任务预算已用尽，已有材料和候选已保留；请查看候选或新建任务")
            if current.get("invalid_outputs", {}).get(key, 0) >= 2:
                raise ProviderError("这个阶段的结构重试已用尽，已有内容已保留")
            current["calls"] += 1
            current["request_started"] = time.time()
            current["attempts"][key] = current["attempts"].get(key, 0) + 1

        job = self._change(job["id"], token, reserve)
        start = time.monotonic()
        error = None
        value = None
        try:
            async with asyncio.timeout(min(45, (180000 - job["elapsed_ms"]) / 1000)):
                task = asyncio.create_task(self.client.complete(config, stage, self._context(job, stage), schema))
                self._active = (job["id"], task)
                value = await task
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
        def apply(current, connection):
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

        return self._change(job["id"], token, apply)

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
            while True:
                job = self.jobs.get(job["id"])
                if job["state"] != "running" or job["run_token"] != token:
                    return True
                stage = job["stage"]
                if stage == "review":
                    candidate_type = ReviewDraft if job["mode"] == "recheck" else Draft
                    checks = validate_draft(candidate_type.model_validate(job["draft"]), [Evidence.model_validate(e) for e in job["evidence"]])
                    if checks:
                        check_payload = [i.model_dump() for i in checks]
                        job = self._change(job["id"], token, lambda j, _, issues=check_payload: j.update(issues=issues, review=None))
                        if not self._can_revise(job):
                            self._finish(job, token)
                            return True
                        self._change(job["id"], token, lambda j, _: j.update(stage="revise"))
                        continue
                review_schema = WritingReview if job["skill"].get("stage_instructions") else Review
                schema = {"plan": Plan, "draft": Draft, "review": review_schema, "revise": Draft}[stage]
                try:
                    output = await self._request(job, token, schema)
                except ModelOutputError:
                    current = self.jobs.get(job["id"])
                    if current.get("invalid_outputs", {}).get(f"{stage}:{current['revisions']}", 0) < 2 and current["calls"] < 8:
                        continue
                    raise
                if stage == "plan":
                    def plan_done(current, _, plan=output):
                        current["plan"] = plan.model_dump()
                        if plan.decision == "ask" and current["input"]["allow_questions"]:
                            current.update(state="waiting_input", question_group=uuid.uuid4().hex, run_token="")
                        else:
                            current["stage"] = "draft"

                    job = self._change(job["id"], token, plan_done)
                    if job["state"] == "waiting_input":
                        return True
                elif stage in ("draft", "revise"):
                    def draft_done(current, _, draft=output, completed_stage=stage):
                        if current["input"].get("education"):
                            fixed = [DraftEducation(**row, fact_ids=[e["id"] for e in current["evidence"]
                                     if e["id"].startswith(f"profile-{row['id']}-")])
                                     for row in current["input"]["education"]]
                            draft = Draft.model_validate({**draft.model_dump(), "education": [row.model_dump() for row in fixed]})
                        current.update(draft=draft.model_dump(), stage="review", review=None, issues=[])
                        if completed_stage == "revise":
                            current["revisions"] += 1

                    self._change(job["id"], token, draft_done)
                else:
                    candidate_type = ReviewDraft if job["mode"] == "recheck" else Draft
                    quality = validate_quality(candidate_type.model_validate(job["draft"]))
                    report = editorial_quality(getattr(output, "quality", None), quality, job["evidence"])
                    review_payload = output.model_dump()
                    if report:
                        review_payload["quality"] = report.model_dump()
                    all_issues = [i.model_dump() for i in [*output.issues, *quality, *quality_issues(report)]]
                    job = self._change(job["id"], token, lambda j, _, review=review_payload, issues=all_issues: j.update(review=review, issues=issues))
                    editorial_fix = (report and report.status == "revise") or any("压缩" in i.message or "合并" in i.message or "重复" in i.message for i in quality)
                    if (output.verdict == "pass" and not editorial_fix) or not self._can_revise(job):
                        self._finish(job, token)
                        return True
                    self._change(job["id"], token, lambda j, _: j.update(stage="revise"))
        except StaleRun:
            pass
        except (ProviderError, Conflict) as exc:
            with suppress(StaleRun):
                self._change(job["id"], token, lambda j, _, message=str(exc): j.update(state="failed", error=message, run_token="", request_started=None))
        except Exception:  # noqa: BLE001 -- do not log model text, user material or credentials.
            with suppress(StaleRun):
                self._change(job["id"], token, lambda j, _: j.update(state="failed", error="任务处理失败，材料与已完成步骤已保留，请查看后继续。", run_token="", request_started=None))
        return True

    @staticmethod
    def _can_revise(job):
        return job["mode"] == "generate" and job["revisions"] < 2 and job["calls"] <= 6 and job["elapsed_ms"] < 180000
