"""Target-bound resume editing Agent.

The model can only propose a candidate. Program gates recompute the actual
diff and explicit apply writes a new resume revision with optimistic locking.
"""

from __future__ import annotations

import copy
import json
import uuid
from typing import Literal

from pydantic import Field
from sqlalchemy import Column, MetaData, String, Table, Text, insert, select, update

from app.budget import DEFAULT_POLICY
from app.gates import blocking_gates
from app.generation_models import Draft, Evidence
from app.generation_service import content_draft
from app.jobs import fingerprint
from app.models import AIInfo, ResumeContent, StrictModel, resume_hash
from app.providers import ProviderError
from app.resume_layout import education_text, period_text, section_text
from app.skill import build_evidence, load_skill, validate_draft
from app.store import Conflict, NotFound, timestamp


metadata = MetaData()
agent_sessions = Table(
    "agent_sessions", metadata,
    Column("id", String, primary_key=True),
    Column("target_type", String, nullable=False),
    Column("target_id", String, nullable=False),
    Column("data", Text, nullable=False),
)


class AgentTargetInput(StrictModel):
    target_type: Literal["resume", "job"]
    target_id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")


class AgentMessageInput(StrictModel):
    text: str = Field(min_length=1, max_length=2000)


class AgentReason(StrictModel):
    item_id: str = Field(min_length=1, max_length=80)
    reason: str = Field(min_length=1, max_length=300)
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)


class AgentEditOutput(StrictModel):
    reply: str = Field(min_length=1, max_length=1000)
    content: ResumeContent
    reasons: list[AgentReason] = Field(default_factory=list, max_length=20)


def _blocks(content: ResumeContent) -> dict[str, str]:
    rows = {"__summary": content.summary} if content.summary else {}
    rows.update({row.id: " ".join(filter(None, (education_text(row), period_text(row)))) for row in content.education})
    for section in content.sections:
        rows[section.id] = " ".join(filter(None, (section_text(section), period_text(section))))
        rows.update({item.id: item.text for item in section.items})
    return rows


def _issue_key(issue) -> tuple[str, str, str]:
    return issue.item_id, issue.code, issue.message


class AgentService:
    def __init__(self, workflow):
        self.workflow = workflow
        self.store, self.jobs = workflow.store, workflow.jobs
        self.registry, self.client = workflow.registry, workflow.client
        metadata.create_all(self.store.engine)

    def create(self, target: AgentTargetInput) -> dict:
        resolved = self._resolve_target(target)
        with self.store.engine.connect() as connection:
            data = connection.execute(select(agent_sessions.c.data).where(
                agent_sessions.c.target_type == resolved.target_type,
                agent_sessions.c.target_id == resolved.target_id,
            )).scalar_one_or_none()
        if data:
            return self.view(json.loads(data))
        snapshot = self._snapshot(resolved)
        session = {
            "id": uuid.uuid4().hex,
            "target_type": resolved.target_type,
            "target_id": resolved.target_id,
            "messages": [{"role": "assistant", "text": f"已连接到「{snapshot['label']}」。告诉我想怎么改，我会先给出可核对的提案，不会直接覆盖当前版本。"}],
            "proposal": None,
            "status": "idle",
            "error": "",
        }
        self._write(session)
        return self.view(session)

    def get(self, session_id: str) -> dict:
        return self.view(self._read(session_id))

    async def post(self, session_id: str, message: AgentMessageInput) -> dict:
        session = self._read(session_id)
        if session.get("status") == "running":
            raise Conflict("Agent 正在处理上一条请求")
        if (session.get("proposal") or {}).get("state") in {"ready", "blocked"}:
            raise Conflict("请先应用或放弃当前提案，再提出下一项修改")
        snapshot = self._snapshot(AgentTargetInput(target_type=session["target_type"], target_id=session["target_id"]))
        session["messages"].append({"role": "user", "text": message.text})
        session.update(status="running", error="")
        self._write(session)
        try:
            context = self._context(snapshot, session, message.text)
            config = self.registry.get(self.registry.current)
            completion = await self.client.propose_edit(config, context, AgentEditOutput)
            proposal = self._proposal(snapshot, completion.value)
            session["proposal"] = proposal
            session["messages"].append({"role": "assistant", "text": completion.value.reply})
            session.update(status="idle", error="")
        except ProviderError as exc:
            session["messages"].append({"role": "assistant", "text": str(exc)})
            session.update(status="error", error=str(exc), proposal=None)
        self._write(session)
        return self.view(session)

    def apply(self, session_id: str, proposal_id: str) -> dict:
        session = self._read(session_id)
        proposal = session.get("proposal") or {}
        if proposal.get("id") != proposal_id or proposal.get("state") not in {"ready", "blocked"}:
            raise Conflict("修改提案不存在或已处理")
        if proposal["state"] == "blocked":
            raise Conflict("当前提案有新增事实风险，不能应用")
        target = AgentTargetInput(target_type=session["target_type"], target_id=session["target_id"])
        snapshot = self._snapshot(target)
        if (snapshot["base_revision"] != proposal["base_revision"]
                or snapshot["target_token"] != proposal["target_token"]):
            raise Conflict("当前内容已变化，请基于最新版本重新提出修改")
        candidate = ResumeContent.model_validate(proposal["content"])
        agent_job = self._record_agent_job(snapshot, proposal)
        info = AIInfo(
            job_id=agent_job["id"], review_job_id=agent_job["id"], review_status="unreviewed",
            content_hash=resume_hash(candidate), skill_version=agent_job["skill"]["version"],
            source_map=proposal["source_map"], issues=proposal["issues"], quality=None,
        )
        if target.target_type == "job":
            record = self.workflow.adopt(target.target_id)
            if record.revision != 1 or resume_hash(record.content) != snapshot["base_hash"]:
                raise Conflict("生成候选已经被采用并修改，请打开最新简历后重试")
            saved = self.store.save(record.id, record.revision, candidate, ai=info)
            session.update(target_type="resume", target_id=saved.id)
        else:
            saved = self.store.save(target.target_id, proposal["base_revision"], candidate, ai=info)
        proposal["state"] = "applied"
        session["messages"].append({"role": "assistant", "text": f"已应用为版本 v{saved.revision}。事实审阅需要针对这个新版本重新运行。"})
        session["status"] = "idle"
        self._write(session)
        return {"session": self.view(session), "resume": saved}

    def discard(self, session_id: str, proposal_id: str) -> dict:
        session = self._read(session_id)
        proposal = session.get("proposal") or {}
        if proposal.get("id") != proposal_id or proposal.get("state") not in {"ready", "blocked"}:
            raise Conflict("修改提案不存在或已处理")
        proposal["state"] = "discarded"
        session["messages"].append({"role": "assistant", "text": "已放弃这份提案，当前简历没有改变。"})
        self._write(session)
        return self.view(session)

    def view(self, session: dict) -> dict:
        snapshot = self._snapshot(AgentTargetInput(target_type=session["target_type"], target_id=session["target_id"]))
        return {
            "id": session["id"],
            "target": {"type": session["target_type"], "id": session["target_id"], "label": snapshot["label"],
                       "revision": snapshot["base_revision"], "state": snapshot.get("state")},
            "messages": session.get("messages", [])[-40:],
            "proposal": session.get("proposal"),
            "status": session.get("status", "idle"),
            "error": session.get("error", ""),
        }

    def _resolve_target(self, target: AgentTargetInput) -> AgentTargetInput:
        if target.target_type == "job":
            job = self.jobs.get(target.target_id)
            if job.get("adopted_resume_id"):
                return AgentTargetInput(target_type="resume", target_id=job["adopted_resume_id"])
        return target

    def _snapshot(self, target: AgentTargetInput) -> dict:
        if target.target_type == "job":
            job = self.jobs.get(target.target_id)
            if job.get("state") not in {"ready", "failed", "interrupted"} or not job.get("draft"):
                raise Conflict("这个生成任务还没有可编辑的候选，请等待生成完成")
            draft = Draft.model_validate(job["draft"])
            content = draft.to_content(job["input"].get("name", ""), job["input"].get("contact", ""),
                                       job["input"].get("target_role", ""), job["input"].get("education") or None)
            refs = [row["id"] for row in job["evidence"]]
            source_map = {claim.id: claim.fact_ids for claim in draft.claims() + draft.metadata_claims(refs)}
            return {"target_type": "job", "target_id": target.target_id, "label": job["input"].get("target_role") or "生成任务候选",
                    "state": job["state"], "content": content, "base_revision": 0,
                    "base_hash": resume_hash(content), "target_token": fingerprint(job["draft"]),
                    "evidence": job["evidence"], "source_map": source_map, "job": job,
                    "source_text": job["input"].get("source_text", ""), "skill": job["skill"]}
        record = self.store.get(target.target_id)
        source_text = self.store.source_text(record.id)
        if record.ai:
            original = self.jobs.get(record.ai.job_id)
            evidence = original["evidence"]
            source_map = record.ai.source_map
            job = original
            skill = original["skill"]
        else:
            evidence = [row.model_dump() for row in build_evidence(source_text or "\n".join(_blocks(record.content).values()))]
            refs = [row["id"] for row in evidence]
            source_map = {item_id: refs for item_id in _blocks(record.content)}
            bundle = load_skill(record.content.target_role, role_direction="other")
            skill = {"role": bundle.role, "version": bundle.version, "instructions": bundle.instructions,
                     "resources": bundle.resources, "stage_resources": bundle.stage_resources,
                     "stage_instructions": bundle.stage_instructions}
            job = {"mode": "recheck", "input": {"source_text": source_text, "contact": record.content.contact,
                   "education": [row.model_dump() for row in record.content.education], "target_role": record.content.target_role,
                   "career_stage": "unspecified", "has_career_gap": False, "jd": ""}, "answer_context": []}
        return {"target_type": "resume", "target_id": record.id, "label": record.content.name or record.content.target_role or "未命名简历",
                "state": "ready", "content": record.content, "base_revision": record.revision,
                "base_hash": resume_hash(record.content), "target_token": resume_hash(record.content),
                "evidence": evidence, "source_map": source_map, "job": job, "source_text": source_text, "skill": skill}

    def _context(self, snapshot: dict, session: dict, request: str) -> dict:
        content = snapshot["content"].model_copy(deep=True)
        secrets = [content.name, content.contact, *[row.school for row in content.education]]
        content.name = ""
        content.contact = ""
        for row in content.education:
            row.school = ""

        def scrub(value: str) -> str:
            for secret in secrets:
                if secret:
                    value = value.replace(secret, " ")
            return " ".join(value.split())

        evidence = [{**row, "text": scrub(row["text"])} for row in snapshot["evidence"]]
        instructions = snapshot["skill"].get("stage_instructions", {}).get("revise", snapshot["skill"].get("instructions", ""))
        return {"instructions": instructions, "_budget_policy": DEFAULT_POLICY.model_dump(),
                "current_content": content.model_dump(), "evidence": evidence,
                "user_request": scrub(request),
                "recent_messages": [{**row, "text": scrub(row["text"])} for row in session.get("messages", [])[-6:-1]]}

    def _proposal(self, snapshot: dict, output: AgentEditOutput) -> dict:
        candidate = output.content.model_copy(deep=True)
        base = snapshot["content"]
        candidate.name, candidate.contact = base.name, base.contact
        schools = {row.id: row.school for row in base.education}
        for row in candidate.education:
            row.school = schools.get(row.id, "")
        highlights = {item.id: item.highlights for section in base.sections for item in section.items}
        for section in candidate.sections:
            for item in section.items:
                item.highlights = [value for value in highlights.get(item.id, []) if value in item.text]
        before, after = _blocks(base), _blocks(candidate)
        changed = [item_id for item_id in dict.fromkeys([*before, *after]) if before.get(item_id, "") != after.get(item_id, "")]
        reasons = {row.item_id: row for row in output.reasons}
        known = {row["id"] for row in snapshot["evidence"]}
        changes, source_map = [], copy.deepcopy(snapshot["source_map"])
        for item_id in changed:
            reason = reasons.get(item_id)
            refs = [ref for ref in (reason.evidence_ids if reason else source_map.get(item_id, [])) if ref in known]
            source_map[item_id] = refs
            changes.append({"item_id": item_id, "before": before.get(item_id, ""), "after": after.get(item_id, ""),
                            "reason": reason.reason if reason else "按你的要求调整", "evidence_ids": refs})
        candidate_draft = content_draft(candidate, snapshot["evidence"], source_map)
        base_draft = content_draft(base, snapshot["evidence"], snapshot["source_map"])
        candidate_issues = [*validate_draft(candidate_draft, [Evidence.model_validate(row) for row in snapshot["evidence"]]),
                            *blocking_gates(snapshot["job"], candidate_draft)]
        base_issue_keys = {_issue_key(issue) for issue in [
            *validate_draft(base_draft, [Evidence.model_validate(row) for row in snapshot["evidence"]]),
            *blocking_gates(snapshot["job"], base_draft),
        ]}
        issues = [issue.model_dump() for issue in candidate_issues
                  if _issue_key(issue) not in base_issue_keys and (issue.item_id in changed or issue.item_id == "document")]
        if any(change["after"] and not change["evidence_ids"] for change in changes):
            issues.append({"item_id": "document", "severity": "blocking", "code": "reference",
                           "message": "Agent 修改没有对应原文引用，不能应用。", "suggestion": "请缩小修改范围或补充真实材料。",
                           "repair_action": "need_input"})
        return {"id": uuid.uuid4().hex, "state": "blocked" if any(row["severity"] == "blocking" for row in issues) else "ready",
                "base_revision": snapshot["base_revision"], "base_hash": snapshot["base_hash"],
                "target_token": snapshot["target_token"],
                "content": candidate.model_dump(), "changes": changes, "issues": issues, "source_map": source_map,
                "created_at": timestamp()}

    def _record_agent_job(self, snapshot: dict, proposal: dict) -> dict:
        inputs = {"request_id": proposal["id"], "name": snapshot["content"].name,
                  "contact": snapshot["content"].contact, "target_role": snapshot["content"].target_role,
                  "source_text": snapshot["source_text"], "jd": snapshot["job"].get("input", {}).get("jd", ""),
                  "education": [row.model_dump() for row in snapshot["content"].education],
                  "career_stage": snapshot["job"].get("input", {}).get("career_stage", "unspecified"),
                  "has_career_gap": snapshot["job"].get("input", {}).get("has_career_gap", False),
                  "execution_mode": "langgraph", "allow_questions": False, "send_materials": True,
                  "edit_request": "none"}
        skill = SimpleSkill(snapshot["skill"])
        config = self.registry.get(self.registry.current)
        draft = content_draft(ResumeContent.model_validate(proposal["content"]), snapshot["evidence"], proposal["source_map"])
        return self.jobs.create(inputs, self.registry.current, self.registry.describe(config), skill, snapshot["evidence"],
                                mode="agent_edit", extra={"state": "ready", "stage": "done", "draft": draft.model_dump(),
                                "issues": proposal["issues"], "calls": 1, "review": None, "target_hash": proposal["base_hash"]})

    def _write(self, session: dict) -> None:
        payload = json.dumps(session, ensure_ascii=False)
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            exists = connection.execute(select(agent_sessions.c.id).where(agent_sessions.c.id == session["id"])).first()
            values = {"target_type": session["target_type"], "target_id": session["target_id"], "data": payload}
            if exists:
                connection.execute(update(agent_sessions).where(agent_sessions.c.id == session["id"]).values(**values))
            else:
                connection.execute(insert(agent_sessions).values(id=session["id"], **values))

    def _read(self, session_id: str) -> dict:
        with self.store.engine.connect() as connection:
            data = connection.execute(select(agent_sessions.c.data).where(agent_sessions.c.id == session_id)).scalar_one_or_none()
        if data is None:
            raise NotFound("Agent 对话不存在")
        return json.loads(data)


class SimpleSkill:
    def __init__(self, value: dict):
        self.role = value["role"]
        self.version = value["version"]
        self.instructions = value.get("instructions", "")
        self.resources = value.get("resources", [])
        self.stage_resources = value.get("stage_resources", {})
        self.stage_instructions = value.get("stage_instructions", {})
