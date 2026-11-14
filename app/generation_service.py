
from app.budget import budget_for_job
from app.generation_models import (
    AnswerInput,
    Draft,
    DraftEducation,
    GenerationInput,
    ReviewClaim,
    ReviewDraft,
    ReviewSection,
    ReviewSummaryClaim,
)
from app.jobs import JobStore, fingerprint
from app.model_client import OUTPUT_CONTRACT_VERSION, ModelRegistry
from app.models import AIInfo, Education, ResumeContent, resume_hash
from app.resume_layout import education_text, period_text
from app.skill import build_evidence, load_skill, validate_draft
from app.store import Conflict, ResumeStore


def content_draft(content, evidence, source_map) -> ReviewDraft:
    refs = [e["id"] for e in evidence]

    def cited(item_id):
        # A stored empty list means "no citation", not "every evidence id".
        if item_id in source_map:
            return list(source_map[item_id] or [])
        return list(refs)

    def claim(item_id, text, highlights=None):
        model = ReviewSummaryClaim if item_id == "__summary" else ReviewClaim
        return model(id=item_id, text=text, highlights=highlights or [], fact_ids=cited(item_id))

    return ReviewDraft(summary=claim("__summary", content.summary) if content.summary else None,
                       education=[DraftEducation(**e.model_dump(), fact_ids=cited(e.id)) for e in content.education],
                       sections=[ReviewSection(**s.model_dump(exclude={"items"}), fact_ids=cited(s.id),
                                               items=[claim(i.id, i.text, i.highlights) for i in s.items])
                                 for s in content.sections])


class GenerationService:
    def __init__(self, store: ResumeStore, jobs: JobStore, registry: ModelRegistry, client):
        self.store, self.jobs, self.registry, self.client = store, jobs, registry, client

    def wake(self):
        pass

    def submit(self, inputs: GenerationInput):
        from app.intake import complete_intake

        inputs = complete_intake(inputs)
        if inputs.source_text and inputs.execution_mode == "supervisor" and not self.registry.supports_tools(self.registry.current):
            raise ValueError("请先在模型连接中测试工具调用能力，再启用智能修正策略")
        if inputs.source_text and not inputs.send_materials:
            raise ValueError("请先确认将材料发送给所选模型服务")
        config = self.registry.get(self.registry.current) if inputs.source_text else None
        skill = load_skill(inputs.target_role, inputs.career_stage, inputs.has_career_gap, inputs.role_direction)
        extra = None if inputs.source_text else {"state": "ready", "framework": True,
                                                "error": "当前只有目标，没有个人材料。请补充课程、实践、作品或工作片段后重新生成。"}
        evidence = [e.model_dump() for e in build_evidence(inputs.source_text)]
        for row in inputs.education:
            text = " ".join(filter(None, (education_text(row), period_text(row))))
            if text:
                evidence.extend(e.model_dump() for e in build_evidence(text, prefix=f"profile-{row.id}-"))
        job = self.jobs.create(inputs.model_dump(), self.registry.current or "", self.registry.describe(config) if config else {},
                               skill, evidence, extra=extra)
        self.wake()
        return job

    def answer(self, job_id, payload):
        answer = AnswerInput.model_validate(payload)
        digest = fingerprint(answer.model_dump())

        def apply(job, _):
            if job["answer_submission"] == {"group": answer.question_group, "hash": digest}:
                return
            if job["state"] != "waiting_input" or job["question_group"] != answer.question_group:
                raise Conflict("这组问题已处理或任务状态已变化，请刷新")
            questions = {q["id"]: q["text"] for q in job["plan"]["questions"]}
            if any(key not in questions for key in answer.answers):
                raise ValueError("回答包含不存在的问题")
            job["answer_context"] = []
            for index, (key, text) in enumerate(answer.answers.items()):
                evidence = build_evidence(text, prefix=f"a{index}-")
                job["evidence"].extend(e.model_dump() for e in evidence)
                job["answer_context"].append({"question": questions[key], "answer": text, "fact_ids": [e.id for e in evidence]})
            job.update(state="queued", stage="draft", answered=True, error="",
                       answer_submission={"group": answer.question_group, "hash": digest})

        job = self.jobs.mutate(job_id, apply)
        self.wake()
        return job

    def cancel(self, job_id):
        def apply(job, _):
            if job["state"] == "cancelled":
                return
            if job["state"] == "ready":
                raise Conflict("任务已经完成，无需取消")
            job.update(state="cancelled", run_token="", request_started=None, error="任务已取消，已发送的请求可能已计费。")

        return self.jobs.mutate(job_id, apply)

    def resume(self, job_id):
        config = self.registry.get(self.registry.current)

        def apply(job, _):
            if job["state"] not in ("failed", "interrupted"):
                raise Conflict("只有失败或中断的任务可以继续")
            if job.get("engine") == "supervisor" and not self.registry.supports_tools(self.registry.current):
                raise Conflict("请先为当前模型重新测试工具调用能力；任务引擎和已用预算保留")
            if self.registry.describe(config) != job["provider"]:
                raise Conflict("请连接原任务相同的供应商、地址和模型后继续；切换目标模型请新建任务")
            continuation = self.continuation(job)
            if not continuation["allowed"]:
                raise Conflict(continuation["reason"])
            if job.get("output_contract_version", "legacy") != OUTPUT_CONTRACT_VERSION:
                job.setdefault("validation_history", []).append({"version": job.get("output_contract_version", "legacy"),
                                                                 "invalid_outputs": job.get("invalid_outputs", {})})
                job.update(output_contract_version=OUTPUT_CONTRACT_VERSION, invalid_outputs={})
            job.update(state="queued", config_revision=self.registry.current, error="")

        job = self.jobs.mutate(job_id, apply)
        self.wake()
        return job

    @staticmethod
    def continuation(job):
        policy = budget_for_job(job)
        if job["state"] not in ("failed", "interrupted"):
            return {"allowed": False, "reason": "任务当前无需继续"}
        if job["calls"] >= policy.max_calls:
            return {"allowed": False, "reason": "这次已经问过模型很多次，材料还在。请改一改材料后再生成。"}
        if job["elapsed_ms"] >= policy.total_ms:
            return {"allowed": False, "reason": "这次花费的时间已经比较长，材料还在。请改一改材料后再生成。"}
        if job["stage"] in ("draft", "revise") and (job["calls"] >= policy.max_calls - 1 or job["elapsed_ms"] >= policy.total_ms - policy.review_reserve_ms):
            return {"allowed": False, "reason": "剩下的次数不够再生成并核对一整版。已有内容还在，可以手工修改，或重新开始。"}
        key = f"{job['stage']}:{job['revisions']}"
        if job.get("invalid_outputs", {}).get(key, 0) >= policy.max_invalid_outputs and job.get("output_contract_version", "legacy") == OUTPUT_CONTRACT_VERSION:
            return {"allowed": False, "reason": "连续两次没能整理成可用的简历，已先停下来。材料还在，可以改一改后再生成。"}
        return {"allowed": True, "reason": "可以接着上次继续，已完成的部分会保留。"}

    def adopt(self, job_id):
        result = []

        def apply(job, connection):
            if (job["mode"] != "generate" or job["state"] not in ("ready", "failed", "interrupted")
                    or (not job["draft"] and not job["framework"])):
                raise Conflict("任务仍在执行、已取消或没有候选，请等待或先处理错误")
            result.append(self._materialize(job, connection))

        self.jobs.mutate(job_id, apply)
        return result[0]

    def _materialize(self, job, connection):
        """Create the editable resume once; safe to call from completion and the legacy endpoint."""
        if job["adopted_resume_id"]:
            return self.store._read(connection, job["adopted_resume_id"])
        inputs = job["input"]
        draft = Draft.model_validate(job["draft"]) if job["draft"] else None
        fixed = [Education.model_validate(e) for e in inputs.get("education", [])]
        from app.gates import header_contact

        contact = header_contact(inputs.get("contact") or "", inputs.get("source_text") or "")
        content = draft.to_content(inputs["name"], contact, inputs["target_role"], fixed or None) if draft else ResumeContent(
            name=inputs["name"], contact=contact, target_role=inputs["target_role"], education=fixed)
        status = "passed" if job["review"] and job["review"]["verdict"] == "pass" and not any(
            i["severity"] == "blocking" for i in job["issues"]) else "blocked" if job["issues"] else "unreviewed"
        info = AIInfo(job_id=job["id"], review_job_id=job["id"], review_status=status, content_hash=resume_hash(content),
                      skill_version=job["skill"]["version"], issues=job["issues"], quality=job.get("review", {}).get("quality") if job.get("review") else None,
                      source_map={c.id: c.fact_ids for c in draft.claims() + draft.metadata_claims([e["id"] for e in job["evidence"]])} if draft else {})
        record = self.store.create(content, "ai", inputs["source_text"], ai=info, connection=connection)
        job["adopted_resume_id"] = record.id
        return record

    def recheck(self, resume_id, revision, request_id):
        record = self.store.get(resume_id)
        if record.revision != revision or not record.ai:
            raise Conflict("请先保存当前 AI 简历，再审阅这个版本")
        original = self.jobs.get(record.ai.job_id)
        draft = content_draft(record.content, original["evidence"], record.ai.source_map)
        if not draft.claims():
            raise Conflict("没有可审阅正文，请先补充材料")
        config = self.registry.get(self.registry.current)
        inputs = {**original["input"], "request_id": request_id, "target_role": record.content.target_role,
                  "review_resume_id": resume_id, "base_revision": revision}
        skill = load_skill(record.content.target_role, inputs.get("career_stage", "unspecified"), inputs.get("has_career_gap", False),
                           pinned_role=original.get("skill", {}).get("role"))
        job = self.jobs.create(inputs, self.registry.current, self.registry.describe(config), skill,
                               original["evidence"], mode="recheck", extra={"stage": "review", "draft": draft.model_dump(),
                               "answer_context": original.get("answer_context", []), "target_hash": resume_hash(record.content)})
        self.wake()
        return job

    def takeover(self, resume_id, revision):
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            record = self.store._read(connection, resume_id)
            if record.revision != revision or not record.ai:
                raise Conflict("版本已变化或当前不是 AI 简历")
            if record.ai.has_blockers():
                raise Conflict("仍有已知阻断，请先修正并重新审阅，不能直接切换标签消除")
            original = self.jobs._get(connection, record.ai.job_id)
            if original["evidence"]:
                draft = content_draft(record.content, original["evidence"], record.ai.source_map)
                from app.gates import blocking_gates
                from app.generation_models import Evidence

                issues = [*validate_draft(draft, [Evidence.model_validate(e) for e in original["evidence"]]),
                          *blocking_gates({**original, "mode": "recheck"}, draft)]
                if issues:
                    raise Conflict("程序仍发现事实风险，请修正或补充原材料后重新生成")
            info = record.ai.model_copy(update={"review_status": "unreviewed", "manual_takeover": True,
                                                "content_hash": resume_hash(record.content)})
            self.store.write_ai(connection, resume_id, revision, info)
            return self.store._read(connection, resume_id)

    def resolve_issue(self, resume_id, payload):
        from app.manual_review import resolve_issue

        return resolve_issue(self.store, self.jobs, resume_id, payload)
