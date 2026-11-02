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
    event,
    insert,
    select,
    update,
)

from app.models import Fact, ResumeContent, ResumeRecord


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


def timestamp() -> str:
    return datetime.now(UTC).isoformat()


def make_facts(content: ResumeContent, origin: str, previous: list[Fact]) -> list[Fact]:
    existing = {(fact.block_id, fact.text): fact.id for fact in previous}
    blocks = [(item.id, item.text) for section in content.sections for item in section.items]
    if content.summary:
        blocks.append(("__summary", content.summary))
    return [Fact(id=existing.get((block, text), uuid.uuid4().hex), block_id=block, text=text,
                 source="fictional_demo" if origin == "demo" else "user_statement")
            for block, text in blocks]


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
        return self._decode(row)

    def create(self, content: ResumeContent, origin: Literal["manual", "demo"], source_text: str = "") -> ResumeRecord:
        if origin not in ("manual", "demo"):
            raise ValueError("不支持的内容来源")
        record = ResumeRecord(id=uuid.uuid4().hex, revision=1, origin=origin, content=content,
                              facts=make_facts(content, origin, []), created_at=timestamp(), updated_at=timestamp())
        with self.engine.begin() as connection:
            connection.execute(insert(resumes).values(
                **record.model_dump(exclude={"content", "facts"}), content=content.model_dump_json(),
                facts=json.dumps([fact.model_dump() for fact in record.facts], ensure_ascii=False), source_text=source_text,
            ))
            connection.execute(insert(versions).values(resume_id=record.id, revision=1, snapshot=record.model_dump_json()))
        return record

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
            result = connection.execute(update(resumes).where(
                resumes.c.id == resume_id, resumes.c.revision == expected_revision,
            ).values(revision=changed.revision, confirmed_revision=None, content=content.model_dump_json(),
                     facts=json.dumps([fact.model_dump() for fact in facts], ensure_ascii=False), updated_at=changed.updated_at))
            if result.rowcount != 1:
                raise Conflict("简历已在其他页面修改，请重新载入后再保存")
            connection.execute(insert(versions).values(resume_id=resume_id, revision=changed.revision, snapshot=changed.model_dump_json()))
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
