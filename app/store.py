from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    create_engine,
    delete,
    event,
    insert,
    select,
    update,
)

from app.models import AIInfo, Fact, ResumeContent, ResumeRecord
from app.resume_layout import education_text, period_text, section_text


class Conflict(Exception):
    pass


class NotFound(Exception):
    pass


metadata = MetaData()
resumes = Table(
    "resumes", metadata,
    Column("id", String, primary_key=True),
    Column("revision", Integer, nullable=False),
    Column("confirmed_revision", Integer),
    Column("origin", String, nullable=False),
    Column("content", Text, nullable=False),
    Column("facts", Text, nullable=False),
    Column("source_text", Text, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
)
versions = Table(
    "resume_versions", metadata,
    Column("resume_id", String, primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("snapshot", Text, nullable=False),
)
annotations = Table(
    "resume_ai_versions", metadata,
    Column("resume_id", String, primary_key=True),
    Column("revision", Integer, primary_key=True),
    Column("info", Text, nullable=False),
)


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def make_facts(content: ResumeContent, origin: str, previous: list[Fact]) -> list[Fact]:
    existing = {(fact.block_id, fact.text): fact.id for fact in previous}
    blocks = [(item.id, item.text) for section in content.sections for item in section.items]
    blocks += [(e.id, education_text(e) + " " + period_text(e)) for e in content.education]
    blocks += [(s.id, section_text(s) + " " + period_text(s)) for s in content.sections]
    if content.summary:
        blocks.append(("__summary", content.summary))
    return [Fact(id=existing.get((block, text), uuid.uuid4().hex), block_id=block, text=text,
                 source={"demo": "fictional_demo", "ai": "ai_candidate"}.get(origin, "user_statement"))
            for block, text in blocks]


def resolve_deleted_issues(current: ResumeRecord, content: ResumeContent, revision: int) -> list[dict]:
    def blocks(value):
        return {**{s.id: section_text(s) + " " + period_text(s) for s in value.sections},
                **{e.id: education_text(e) + " " + period_text(e) for e in value.education},
                **{i.id: i.text for s in value.sections for i in s.items},
                **({"__summary": value.summary} if value.summary else {})}

    previous = blocks(current.content)
    present = blocks(content)
    texts = ["".join(text.split()) for text in present.values()]
    issues = []
    for original in current.ai.issues:
        issue = {key: value for key, value in original.items() if key != "resolution"}
        location = issue.get("item_id", "document")
        observed = issue.get("observed_text") or previous.get(location, "")
        if observed:
            issue["observed_text"] = observed
        if (issue.get("severity") == "blocking" and location != "document" and location not in present and observed
                and not any("".join(observed.split()) in text for text in texts)):
            issue["resolution"] = {"action": "deleted", "revision": revision, "review_job_id": current.ai.review_job_id}
        issues.append(issue)
    return issues


class ResumeStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine("sqlite:///" + path.as_posix(), connect_args={"check_same_thread": False})

        @event.listens_for(self.engine, "connect")
        def configure(connection, _):
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute("PRAGMA busy_timeout=5000")

        metadata.create_all(self.engine)

    def _decode(self, row) -> ResumeRecord:
        return ResumeRecord(
            **{key: row[key] for key in ("id", "revision", "confirmed_revision", "origin", "created_at", "updated_at")},
            content=ResumeContent.model_validate_json(row["content"]),
            facts=[Fact.model_validate(value) for value in json.loads(row["facts"])],
        )

    def _read(self, connection, resume_id: str) -> ResumeRecord:
        row = connection.execute(select(resumes).where(resumes.c.id == resume_id)).mappings().first()
        if row is None:
            raise NotFound("简历不存在")
        record = self._decode(row)
        info = connection.execute(select(annotations.c.info).where(
            annotations.c.resume_id == resume_id, annotations.c.revision == record.revision)).scalar_one_or_none()
        if info:
            record.ai = AIInfo.model_validate_json(info)
        return record

    def create(self, content: ResumeContent, origin: Literal["manual", "demo", "ai"], source_text: str = "", *,
               ai: AIInfo | None = None, connection=None) -> ResumeRecord:
        if origin not in ("manual", "demo", "ai") or (origin == "ai") != (ai is not None):
            raise ValueError("不支持的内容来源")
        record = ResumeRecord(id=uuid.uuid4().hex, revision=1, origin=origin, content=content,
                              facts=make_facts(content, origin, []), created_at=timestamp(), updated_at=timestamp(), ai=ai)

        def write(conn):
            conn.execute(insert(resumes).values(
                **record.model_dump(exclude={"content", "facts", "ai"}), content=content.model_dump_json(),
                facts=json.dumps([fact.model_dump() for fact in record.facts], ensure_ascii=False), source_text=source_text,
            ))
            conn.execute(insert(versions).values(resume_id=record.id, revision=1, snapshot=record.model_dump_json()))
            if ai:
                self.write_ai(conn, record.id, 1, ai)

        if connection is None:
            with self.engine.begin() as conn:
                write(conn)
        else:
            write(connection)
        return record

    def write_ai(self, connection, resume_id: str, revision: int, info: AIInfo):
        connection.execute(delete(annotations).where(annotations.c.resume_id == resume_id, annotations.c.revision == revision))
        connection.execute(insert(annotations).values(resume_id=resume_id, revision=revision, info=info.model_dump_json()))
        connection.execute(update(resumes).where(resumes.c.id == resume_id, resumes.c.revision == revision).values(confirmed_revision=None))

    def get(self, resume_id: str) -> ResumeRecord:
        with self.engine.connect() as connection:
            return self._read(connection, resume_id)

    def list(self) -> list[dict]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(resumes).order_by(resumes.c.updated_at.desc())).mappings().all()
            return [{"id": row["id"], "revision": row["revision"], "origin": row["origin"],
                     "name": json.loads(row["content"])["name"], "target_role": json.loads(row["content"])["target_role"]}
                    for row in rows]

    def save(self, resume_id: str, expected_revision: int, content: ResumeContent) -> ResumeRecord:
        with self.engine.begin() as connection:
            current = self._read(connection, resume_id)
            facts = make_facts(content, current.origin, current.facts)
            changed = current.model_copy(update={"revision": expected_revision + 1, "confirmed_revision": None,
                                                  "content": content, "facts": facts, "updated_at": timestamp()})
            if current.ai:
                changed.ai = current.ai.model_copy(update={"review_status": "unreviewed", "manual_takeover": False, "quality": None,
                                                           "issues": resolve_deleted_issues(current, content, changed.revision)})
            result = connection.execute(update(resumes).where(
                resumes.c.id == resume_id, resumes.c.revision == expected_revision,
            ).values(revision=changed.revision, confirmed_revision=None, content=content.model_dump_json(),
                     facts=json.dumps([fact.model_dump() for fact in facts], ensure_ascii=False), updated_at=changed.updated_at))
            if result.rowcount != 1:
                raise Conflict("简历已在其他页面修改，请重新载入后再保存")
            connection.execute(insert(versions).values(resume_id=resume_id, revision=changed.revision, snapshot=changed.model_dump_json()))
            if changed.ai:
                self.write_ai(connection, resume_id, changed.revision, changed.ai)
        return changed

    def confirm(self, resume_id: str, expected_revision: int) -> ResumeRecord:
        with self.engine.begin() as connection:
            self._read(connection, resume_id)
            result = connection.execute(update(resumes).where(
                resumes.c.id == resume_id, resumes.c.revision == expected_revision,
            ).values(confirmed_revision=expected_revision))
            if result.rowcount != 1:
                raise Conflict("版本已变化，请核对最新内容")
            return self._read(connection, resume_id)

    def history(self, resume_id: str) -> list[ResumeRecord]:
        with self.engine.connect() as connection:
            self._read(connection, resume_id)
            rows = connection.execute(select(versions.c.snapshot).where(
                versions.c.resume_id == resume_id).order_by(versions.c.revision)).scalars().all()
            return [ResumeRecord.model_validate_json(row) for row in rows]
