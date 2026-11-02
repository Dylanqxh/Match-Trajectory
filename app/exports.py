import hashlib
import json
import os
import sys
import uuid
from pathlib import Path

from app.models import ExportRequest, ResumeRecord
from app.processes import run_worker
from app.store import Conflict, ResumeStore


class IncompleteResume(Exception):
    pass


def render_in_worker(payload: dict) -> bytes:
    command = [sys.executable, "--export-worker"] if getattr(sys, "frozen", False) else [sys.executable, "-m", "app.export_worker"]
    return run_worker(command, json.dumps(payload, ensure_ascii=False).encode("utf-8"))


def check_export(record: ResumeRecord, request: ExportRequest):
    if record.revision != request.expected_revision:
        raise Conflict("内容版本已变化，请重新核对并导出")
    if not request.draft:
        if record.confirmed_revision != record.revision:
            raise Conflict("请先核对并确认当前版本")
        if not record.content.name or not record.content.contact or not any(s.items for s in record.content.sections):
            raise IncompleteResume("请补充姓名、联系方式和至少一段真实内容；当前可先导出草稿")


def export_resume(store: ResumeStore, data_dir: Path, resume_id: str, request: ExportRequest) -> Path:
    snapshot = store.get(resume_id)
    check_export(snapshot, request)
    data = render_in_worker({"format": request.format, "content": snapshot.content.model_dump(),
                             "demo": snapshot.origin == "demo", "draft": request.draft})
    exports = data_dir / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    artifact_id = uuid.uuid4().hex
    name = f"resume-{resume_id[:8]}-r{snapshot.revision}-{'draft' if request.draft else 'confirmed'}-{artifact_id}.{request.format}"
    path = exports / name
    temporary = exports / (uuid.uuid4().hex + ".tmp")
    temporary.write_bytes(data)
    try:
        # Serialize the final validity check and publication against user edits.
        with store.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            check_export(store._read(connection, resume_id), request)
            os.replace(temporary, path)
            manifest = {"resume_id": resume_id, "revision": snapshot.revision, "format": request.format,
                        "draft": request.draft, "origin": snapshot.origin, "review": "manual_unreviewed",
                        "sha256": hashlib.sha256(data).hexdigest()}
            manifest_tmp = exports / (uuid.uuid4().hex + ".tmp")
            manifest_tmp.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
            os.replace(manifest_tmp, path.with_suffix(path.suffix + ".json"))
    finally:
        temporary.unlink(missing_ok=True)
    return path
