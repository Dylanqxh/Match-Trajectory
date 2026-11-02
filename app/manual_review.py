from app.generation_models import Evidence, ResolveIssueInput
from app.generation_service import content_draft
from app.jobs import fingerprint
from app.models import resume_hash
from app.skill import validate_draft
from app.store import Conflict


def resolve_issue(store, jobs, resume_id, payload):
    request = ResolveIssueInput.model_validate(payload)
    with store.engine.begin() as connection:
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        record = store._read(connection, resume_id)
        if record.revision != request.expected_revision or not record.ai or record.ai.review_job_id != request.review_job_id:
            raise Conflict("简历版本或审阅报告已变化，请刷新后核对")
        if request.issue_index >= len(record.ai.issues):
            raise Conflict("问题不存在，请刷新报告")
        issue = record.ai.issues[request.issue_index]
        if issue.get("severity") != "blocking":
            raise Conflict("这条是改进建议，无需解除阻断")
        original = jobs._get(connection, record.ai.job_id)
        sources = {e["id"]: e for e in original["evidence"]}
        if any(ref not in sources for ref in request.evidence_ids):
            raise ValueError("只能选择当前简历原材料中的证据，不能引用其他资料")
        selected = sorted(set(request.evidence_ids))
        content_hash = resume_hash(record.content)
        resolution_id = fingerprint({**request.model_dump(), "evidence_ids": selected, "content_hash": content_hash})
        existing = issue.get("resolution", {})
        if existing:
            if existing.get("id") == resolution_id:
                return record
            raise Conflict("该问题已处理，请刷新后查看")
        mapping = {key: list(refs) for key, refs in record.ai.source_map.items()}
        location = issue.get("item_id", "document")
        if location != "document":
            mapping[location] = sorted(set(mapping.get(location, []) + selected))
        draft = content_draft(record.content, original["evidence"], mapping)
        checks = validate_draft(draft, [Evidence.model_validate(e) for e in original["evidence"]])
        if any(check.severity == "blocking" and (location == "document" or check.item_id == location) for check in checks):
            raise Conflict("该段仍有无依据数字、技能或责任冲突，请先修正正文或补充材料后重新生成")
        resolution = {"id": resolution_id, "action": "source_reviewed", "revision": record.revision,
                      "review_job_id": request.review_job_id, "issue_index": request.issue_index,
                      "evidence_ids": selected, "evidence_hashes": {ref: fingerprint(sources[ref]["text"]) for ref in selected},
                      "explanation": request.explanation, "content_hash": content_hash, "actor": "local_user"}
        issues = [{**item} for item in record.ai.issues]
        issues[request.issue_index] = {**issue, "resolution": resolution}
        info = record.ai.model_copy(update={"issues": issues, "source_map": mapping, "content_hash": content_hash,
                                           "manual_takeover": False, "resolution_history": [*record.ai.resolution_history, resolution]})
        store.write_ai(connection, resume_id, record.revision, info)
        return store._read(connection, resume_id)
