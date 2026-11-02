import hashlib
import json
import time
import uuid

from sqlalchemy import Column, MetaData, String, Table, Text, insert, select, update

from app.model_client import OUTPUT_CONTRACT_VERSION
from app.store import Conflict, NotFound, ResumeStore, timestamp

metadata = MetaData()
job_rows = Table("generation_jobs", metadata,
                 Column("id", String, primary_key=True), Column("request_id", String, unique=True, nullable=False),
                 Column("input_hash", String, nullable=False), Column("state", String, nullable=False),
                 Column("created_at", String, nullable=False),
                 Column("data", Text, nullable=False))


def fingerprint(value) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class JobStore:
    def __init__(self, store: ResumeStore):
        self.store = store
        metadata.create_all(store.engine)

    def _get(self, connection, job_id):
        data = connection.execute(select(job_rows.c.data).where(job_rows.c.id == job_id)).scalar_one_or_none()
        if data is None:
            raise NotFound("任务不存在")
        return json.loads(data)

    def _write(self, connection, job):
        job["updated_at"] = timestamp()
        connection.execute(update(job_rows).where(job_rows.c.id == job["id"]).values(
            state=job["state"], data=json.dumps(job, ensure_ascii=False)))

    def create(self, inputs: dict, config_revision: str, provider: dict, skill, evidence: list, *, mode="generate", extra=None):
        digest = fingerprint(inputs)
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            existing = connection.execute(select(job_rows).where(job_rows.c.request_id == inputs["request_id"])).mappings().first()
            if existing:
                if existing["input_hash"] != digest:
                    raise Conflict("相同请求标识对应不同内容，请重新发起任务")
                return json.loads(existing["data"])
            job = {"id": uuid.uuid4().hex, "input": inputs, "config_revision": config_revision, "provider": provider,
                   "skill": {"role": skill.role, "version": skill.version, "instructions": skill.instructions,
                             "resources": skill.resources, "stage_resources": skill.stage_resources, "stage_instructions": skill.stage_instructions},
                   "evidence": evidence, "state": "queued", "stage": "plan", "mode": mode,
                   "calls": 0, "revisions": 0, "elapsed_ms": 0, "attempts": {}, "call_log": [],
                   "plan": None, "draft": None, "review": None, "issues": [], "error": "",
                   "question_group": "", "answered": False, "answer_submission": None,
                   "framework": False, "adopted_resume_id": None, "run_token": "", "request_started": None,
                   "output_contract_version": OUTPUT_CONTRACT_VERSION,
                   "created_at": timestamp(), "updated_at": timestamp()}
            if extra:
                job.update(extra)
            connection.execute(insert(job_rows).values(id=job["id"], request_id=inputs["request_id"],
                                                       input_hash=digest, state=job["state"], created_at=job["created_at"],
                                                       data=json.dumps(job, ensure_ascii=False)))
            return job

    def get(self, job_id):
        with self.store.engine.connect() as connection:
            return self._get(connection, job_id)

    def list(self):
        keys = ("id", "state", "stage", "created_at", "updated_at", "adopted_resume_id", "mode")
        with self.store.engine.connect() as connection:
            rows = connection.execute(select(job_rows.c.data).order_by(job_rows.c.id)).scalars().all()
        jobs = sorted((json.loads(data) for data in rows), key=lambda job: job["created_at"], reverse=True)
        return [{**{key: job[key] for key in keys}, "target_role": job["input"]["target_role"]} for job in jobs[:50]]

    def mutate(self, job_id, callback):
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            job = self._get(connection, job_id)
            callback(job, connection)
            self._write(connection, job)
            return job

    def claim_next(self):
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            data = connection.execute(select(job_rows.c.data).where(job_rows.c.state == "queued").order_by(job_rows.c.created_at)).scalars().first()
            if not data:
                return None
            job = json.loads(data)
            job.update(state="running", run_token=uuid.uuid4().hex, error="")
            self._write(connection, job)
            return job

    def recover_unfinished(self):
        with self.store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            rows = connection.execute(select(job_rows.c.data).where(job_rows.c.state.in_(["queued", "running"]))).scalars().all()
            for data in rows:
                job = json.loads(data)
                if job["request_started"]:
                    job["elapsed_ms"] += min(45000, max(0, (time.time() - job["request_started"]) * 1000))
                job.update(state="interrupted", run_token="", request_started=None,
                           error="服务已重启或停止；未完成调用可能计费。连接原模型后可明确继续，预算保留。")
                self._write(connection, job)
