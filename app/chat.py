"""Chat intake for the existing plan → draft → review pipeline.

Messages stay in the local database. This module does not log them, and it does
not rewrite resume text. A user cannot push unsupported proficiency or coverage
gaps into the body: those lines are dropped before a task is created, and the
writing gates still run on every draft.
"""

import asyncio
import json
import re
import uuid

from pydantic import Field, ValidationError
from sqlalchemy import Column, MetaData, String, Table, Text, insert, select, update

from app.generation_models import GenerationInput
from app.models import StrictModel
from app.providers import ProviderError
from app.store import NotFound

GREETING = (
    "你好。对话只负责收集材料和转达修改要求，简历正文仍由原来的生成、审阅流程来写。\n"
    "你可以直接说目标岗位，粘贴或上传旧简历（DOCX，或可复制文字的 PDF），再贴上 JD。\n"
    "姓名、联系方式和学校请单独写在对应行里，它们不会进入正文提示。\n"
    "材料会发给你在「模型连接」里配置的模型，可能产生费用；不会发到本项目的服务器。\n"
    "若有追问，最多一轮、最多三个问题。回复「跳过」也会给出完整初稿。"
    "已有经历缺的细节会标在那一条上；岗位上有、材料里没有的差距只出现在旁边，不会写进正文。\n"
    "初稿出现在旁边，可以直接改、核对和导出。可以说「把这段缩短」或「补上人数」。"
    "我不会按聊天另写一版，也不会把原文没有的熟练度写进去。"
)

_LABELS = {
    "姓名": "name", "名字": "name", "联系方式": "contact", "电话": "contact", "邮箱": "contact",
    "目标岗位": "target_role", "岗位": "target_role", "方向": "direction",
    "JD": "jd", "岗位描述": "jd", "职位描述": "jd",
    "简历": "source", "材料": "source", "旧简历": "source", "学校": "school",
    "背景": "background", "求职背景": "background",
}
_LABEL_RE = re.compile(r"^(姓名|名字|联系方式|电话|邮箱|目标岗位|岗位|方向|JD|岗位描述|职位描述|简历|材料|旧简历|学校|背景|求职背景)[:：]\s*(.*)$")
_INJECTION_RE = re.compile(
    r"(写成|改成|写上|写进|写到|加上|补成).{0,40}(精通|熟练|掌握|熟悉|【待补充|【待确认)|"
    r"【待补充|【待确认|"
    r"(缺口|岗位差距|线上经验).{0,16}(写进|写到|放进).{0,8}正文|"
    r"正文.{0,16}(缺口|【待补充|精通|熟练)"
)
_SKIP_RE = re.compile(r"^(跳过|跳过追问|先看一版|直接生成|不用问了?|先出一版)[。！!\s]*$")
_SHORTEN_RE = re.compile(r"缩短|写短|精简一下|简洁一点")
_HEADCOUNT_RE = re.compile(r"补上人数|补人数|加上人数|写上人数|人数补")
_ROLE_RE = re.compile(r"^(?:我想投|我想应聘|目标是|应聘|投递)\s*(.{2,40})$")
_DEGREES = {"本科", "硕士", "博士", "专科", "高中"}

metadata = MetaData()
sessions = Table("chat_sessions", metadata, Column("id", String, primary_key=True), Column("data", Text, nullable=False))
uploads = Table("chat_uploads", metadata, Column("id", String, primary_key=True), Column("data", Text, nullable=False))


class ChatMessageInput(StrictModel):
    text: str = Field(default="", max_length=20000)
    upload_id: str = Field(default="", max_length=80)
    source_text: str | None = Field(default=None, max_length=20000)


def new_session() -> dict:
    return {"id": uuid.uuid4().hex, "messages": [{"role": "assistant", "text": GREETING}],
            "name": "", "contact": "", "target_role": "", "role_direction": "other",
            "source_text": "", "jd": "", "education": [], "career_stage": "unspecified",
            "has_career_gap": False, "job_id": None, "request_id": None, "edit_request": "none",
            "skip_followups": False, "noted": ""}


def _direction(explicit: str, role: str) -> str:
    if "产品" in explicit:
        return "product"
    if any(token in explicit for token in ("后端", "其他", "通用")):
        return "backend" if "后端" in explicit else "other"
    if "产品" in role:
        return "product"
    if any(token in role for token in ("后端", "Java", "java", "服务端", "Golang", "golang")):
        return "backend"
    return "other"


def _strip_injection(text: str) -> tuple[str, bool]:
    kept, dropped = [], False
    for line in (text or "").splitlines():
        if line.strip() and _INJECTION_RE.search(line):
            dropped = True
            prefix = re.split(r"请|帮我|麻烦", line, maxsplit=1)[0].strip(" ，,。")
            if len(prefix) >= 8 and not _INJECTION_RE.search(prefix):
                kept.append(prefix)
            continue
        kept.append(line)
    return "\n".join(kept).strip(), dropped


def _parse_blocks(text: str) -> tuple[list[tuple[str, str]], str]:
    blocks, unlabeled, key, lines = [], [], None, []

    def flush():
        nonlocal key, lines
        if key:
            blocks.append((key, "\n".join(lines).strip()))
        elif lines:
            unlabeled.extend(lines)
        key, lines = None, []

    for raw in text.splitlines():
        match = _LABEL_RE.match(raw.strip())
        if match:
            flush()
            key = _LABELS[match.group(1)]
            lines = [match.group(2)] if match.group(2) else []
        else:
            lines.append(raw)
    flush()
    return blocks, "\n".join(unlabeled).strip()


def _school_fields(text: str) -> dict:
    parts = [part for part in re.split(r"[\s,，/]+", text) if part]
    school = parts[0] if parts else text.strip()
    degree = next((part for part in parts[1:] if part in _DEGREES), "")
    major = next((part for part in parts[1:] if part not in _DEGREES), "")
    return {"id": "edu1", "school": school[:120], "degree": degree[:40], "major": major[:80]}


def _background(value: str) -> str | None:
    if "转岗" in value:
        return "transition"
    if "社招" in value:
        return "experienced"
    if "校招" in value or "初次" in value:
        return "entry"
    return None


class ChatService:
    def __init__(self, engine, workflow):
        self.engine, self.workflow = engine, workflow
        metadata.create_all(engine)

    def create(self) -> dict:
        session = new_session()
        self._write_session(session)
        return self.view(session, None)

    def get(self, session_id: str) -> dict:
        session = self._read_session(session_id)
        job = self._sync(session)
        self._write_session(session)
        return self.view(session, job)

    async def post(self, session_id: str, message: ChatMessageInput) -> dict:
        session = self._read_session(session_id)
        job = self.workflow.jobs.get(session["job_id"]) if session.get("job_id") else None
        text = message.text.strip()
        attachment = self._read_upload(message.upload_id) if message.upload_id else None
        if attachment and not attachment["reliable"] and message.source_text is None:
            session["messages"].append({"role": "user", "text": text or "（上传了一份文件）"})
            session["messages"].append({"role": "assistant", "text": attachment["reason"] + " 可以在输入框里直接粘贴文字。"})
            self._write_session(session)
            return self.view(session, job)
        source_update = message.source_text if message.source_text is not None else (attachment["text"] if attachment else None)
        reply = self._consume(session, text, source_update, job)
        shown = text or ("（上传了一份材料）" if attachment or message.source_text is not None else "")
        if shown:
            session["messages"].append({"role": "user", "text": shown})
        if reply:
            session["messages"].append({"role": "assistant", "text": reply})
        self._write_session(session)
        if session.get("job_id"):
            job = await self._settle(session)
            self._write_session(session)
        return self.view(session, job)

    def save_upload(self, extracted: dict) -> dict:
        row = {"id": uuid.uuid4().hex, **extracted}
        payload = json.dumps({key: row.get(key) for key in ("id", "text", "reliable", "reason", "warnings", "pages", "kind", "name")}, ensure_ascii=False)
        with self.engine.begin() as connection:
            connection.execute(insert(uploads).values(id=row["id"], data=payload))
        return {"id": row["id"], "text": row["text"], "reliable": row["reliable"], "reason": row["reason"],
                "warnings": row["warnings"], "pages": row["pages"], "kind": row["kind"], "name": row.get("name") or ""}

    def _consume(self, session: dict, text: str, source_update: str | None, job: dict | None) -> str:
        state = job["state"] if job else ""
        cleaned, injected = _strip_injection(text)
        if state == "waiting_input":
            if _SKIP_RE.match(cleaned) or cleaned in {"跳过", "跳过追问"}:
                self._skip(job)
                session["skip_followups"] = False
                return "已跳过追问，正在按已有材料生成完整初稿。"
            if injected and not cleaned:
                return "这种改写不会进入正文。熟练度只有原文写过才会保留；岗位差距只留在旁边，不会变成正文里的待补充。"
            if cleaned and (_SHORTEN_RE.search(cleaned) or _HEADCOUNT_RE.search(cleaned)) and len(cleaned) < 40:
                return "先回答这一轮，或回复「跳过」。生成完成后再说缩短或补人数。"
            answer = cleaned or "没有更多补充"
            self.workflow.answer(job["id"], {"question_group": job["question_group"], "answers": {
                question["id"]: answer for question in job["plan"]["questions"]}, "skip": False})
            return "补充已交给原来的生成流程。" + (" 其中要求改写熟练度或把缺口写进正文的部分已忽略。" if injected else "")
        if _SKIP_RE.match(cleaned):
            session["skip_followups"] = True
        explicit_direction = False
        edit = "shorten" if _SHORTEN_RE.search(cleaned) and not injected else "restore_headcount" if _HEADCOUNT_RE.search(cleaned) and not injected else ""
        if source_update is not None:
            source_text, source_injected = _strip_injection(source_update)
            injected = injected or source_injected
            if source_text:
                session["source_text"] = source_text[:20000]
        blocks, unlabeled = _parse_blocks(cleaned)
        for key, value in blocks:
            value, block_injected = _strip_injection(value)
            injected = injected or block_injected
            if not value:
                continue
            if key == "name":
                session["name"] = value.splitlines()[0][:80]
            elif key == "contact":
                session["contact"] = value.splitlines()[0][:300]
            elif key == "target_role":
                session["target_role"] = value.splitlines()[0][:80]
            elif key == "direction":
                session["role_direction"] = _direction(value, session["target_role"])
                explicit_direction = True
            elif key == "jd":
                session["jd"] = value[:8000]
            elif key == "source":
                session["source_text"] = value[:20000]
            elif key == "school":
                session["education"] = [_school_fields(value)]
            elif key == "background":
                stage = _background(value)
                if stage:
                    session["career_stage"] = stage
                if "空窗" in value:
                    session["has_career_gap"] = True
        unlabeled, loose_injected = _strip_injection(unlabeled)
        injected = injected or loose_injected
        if unlabeled and not blocks:
            role_match = _ROLE_RE.match(unlabeled)
            if role_match and not session["target_role"]:
                session["target_role"] = role_match.group(1).strip()[:80]
            elif source_update is None and len(unlabeled) > 40 and not _SKIP_RE.match(unlabeled):
                session["source_text"] = unlabeled[:20000]
            elif source_update is None and not session["target_role"] and 1 < len(unlabeled) <= 40 and not edit and not _SKIP_RE.match(unlabeled):
                session["target_role"] = unlabeled[:80]
        if not explicit_direction:
            session["role_direction"] = _direction("", session["target_role"])
        if edit:
            session["edit_request"] = edit
        notice = "已忽略要求把熟练度或岗位缺口写进正文的说法。正文只依据材料，并由原来的审阅流程处理。" if injected else ""
        if state in {"queued", "running"}:
            return (notice + " " if notice else "") + "上一份还在生成。完成后可以在旁边查看，也可以再说「把这段缩短」或「补上人数」。"
        if edit and session["source_text"] and state in {"ready", "failed", "interrupted", "cancelled", ""}:
            if state == "" and not session["job_id"]:
                pass
            elif state:
                return self._start(session, notice)
        missing = [] if session["source_text"] else ["一段经历或旧简历"]
        if missing:
            prefix = (notice + "\n") if notice else ""
            if session["skip_followups"] and not missing:
                pass
            extra = "回复「跳过」会在生成时跳过追问。" if session["skip_followups"] else "材料齐了就会开始生成；追问最多一轮，也可以说「跳过」。"
            if not text and source_update is None:
                return prefix + "可以说目标岗位，或粘贴、上传旧简历。"
            return prefix + "还需要：" + "、".join(missing) + "。" + extra
        if not self.workflow.registry.current:
            return (notice + "\n" if notice else "") + "还没有可用的模型连接。请先在「模型连接」里选择供应商、粘贴 Key 并测试通过。"
        if state == "ready" and not edit and session["job_id"]:
            current = self.workflow.jobs.get(session["job_id"])
            same = current and current["input"].get("source_text") == session["source_text"] and current["input"].get("jd") == session["jd"] and current["input"].get("edit_request", "none") == session.get("edit_request", "none")
            if same:
                return notice or "初稿已经在旁边。可以直接修改、核对和导出；要缩短或补人数，直接说即可。"
        return self._start(session, notice)

    def _start(self, session: dict, notice: str = "") -> str:
        session["request_id"] = uuid.uuid4().hex
        try:
            job = self.workflow.submit(GenerationInput(
                request_id=session["request_id"], name=session["name"], contact=session["contact"],
                target_role=session["target_role"], role_direction=session["role_direction"],
                source_text=session["source_text"], jd=session["jd"], allow_questions=True,
                send_materials=True, education=session["education"], career_stage=session["career_stage"],
                has_career_gap=session["has_career_gap"], execution_mode="langgraph",
                edit_request=session.get("edit_request") or "none"))
        except ProviderError as exc:
            return str(exc)
        except (ValidationError, ValueError):
            return "有一项内容不符合要求。请检查姓名、联系方式、岗位和材料长度后再发。"
        session["job_id"] = job["id"]
        session["edit_request"] = "none"
        lead = (notice + "\n") if notice else ""
        return lead + "材料已交给原来的生成流程。追问最多三个，也可以回复「跳过」。初稿会显示在旁边。"

    def _skip(self, job: dict) -> None:
        self.workflow.answer(job["id"], {"question_group": job["question_group"], "answers": {}, "skip": True})

    def _sync(self, session: dict) -> dict | None:
        if not session.get("job_id"):
            return None
        job = self.workflow.jobs.get(session["job_id"])
        if job["state"] == "waiting_input" and session.get("skip_followups"):
            self._skip(job)
            session["skip_followups"] = False
            job = self.workflow.jobs.get(session["job_id"])
        self._note(session, job)
        return job

    async def _settle(self, session: dict) -> dict | None:
        job = None
        for _ in range(160):
            job = self.workflow.jobs.get(session["job_id"])
            if job["state"] not in {"queued", "running"}:
                break
            await asyncio.sleep(0.05)
        if job and job["state"] == "waiting_input" and session.get("skip_followups"):
            self._skip(job)
            session["skip_followups"] = False
            for _ in range(160):
                job = self.workflow.jobs.get(session["job_id"])
                if job["state"] not in {"queued", "running"}:
                    break
                await asyncio.sleep(0.05)
        if job:
            self._note(session, job)
        return job

    def _note(self, session: dict, job: dict) -> None:
        marker = f"{job['id']}:{job['state']}:{job.get('question_group', '')}:{len(job.get('coverage_notes') or [])}"
        if session.get("noted") == marker:
            return
        session["noted"] = marker
        if job["state"] == "waiting_input":
            lines = "\n".join(f"{index}. {question['text']}" for index, question in enumerate(job["plan"]["questions"], start=1))
            text = f"需要补充一点信息（这一轮最多三个问题，可以跳过）：\n{lines}\n直接回复，或者说「跳过」。"
        elif job["state"] == "ready":
            notes = [note for note in (job.get("coverage_notes") or []) if note]
            text = "初稿已经生成，在旁边可以预览、修改和导出。请对照你的材料核对事实。"
            if notes:
                text += "\n这些岗位差距不写进正文：\n" + "\n".join(f"- {note}" for note in notes[:8])
        elif job["state"] == "failed":
            text = job.get("error") or "这次没有完成。材料还在，连接模型后可以继续。"
        elif job["state"] in {"queued", "running"}:
            text = "正在按原来的流程整理、起草和审阅。"
        elif job["state"] == "cancelled":
            text = "这次生成已取消。材料还在，可以继续说。"
        else:
            return
        session["messages"].append({"role": "assistant", "text": text})

    def view(self, session: dict, job: dict | None) -> dict:
        return {"id": session["id"], "messages": session["messages"][-40:],
                "collected": {"name": session["name"], "contact": session["contact"], "target_role": session["target_role"],
                              "role_direction": session["role_direction"], "source_text": session["source_text"], "jd": session["jd"],
                              "career_stage": session["career_stage"]},
                "job_id": session.get("job_id"), "job_state": job["state"] if job else None,
                "questions": (job or {}).get("plan", {}).get("questions", []) if job and job["state"] == "waiting_input" else [],
                "coverage_notes": (job or {}).get("coverage_notes") or []}

    def _write_session(self, session: dict) -> None:
        payload = json.dumps(session, ensure_ascii=False)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            exists = connection.execute(select(sessions.c.id).where(sessions.c.id == session["id"])).first()
            if exists:
                connection.execute(update(sessions).where(sessions.c.id == session["id"]).values(data=payload))
            else:
                connection.execute(insert(sessions).values(id=session["id"], data=payload))

    def _read_session(self, session_id: str) -> dict:
        with self.engine.connect() as connection:
            data = connection.execute(select(sessions.c.data).where(sessions.c.id == session_id)).scalar_one_or_none()
        if data is None:
            raise NotFound("对话不存在")
        return json.loads(data)

    def _read_upload(self, upload_id: str) -> dict:
        with self.engine.connect() as connection:
            data = connection.execute(select(uploads.c.data).where(uploads.c.id == upload_id)).scalar_one_or_none()
        if data is None:
            raise NotFound("上传不存在或已失效")
        return json.loads(data)
