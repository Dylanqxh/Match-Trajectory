import asyncio
import json

import pytest

from app.generation_models import GenerationInput
from app.model_client import Completion, ModelRegistry
from app.providers import ProviderConfig, ProviderError
from app.store import Conflict, ResumeStore

MATERIAL = "使用 Java 完成课程预约查询接口，编写测试记录，未上线。"
DRAFT = {"sections": [{"id": "projects", "title": "项目经历", "items": [
    {"id": "item1", "text": "使用 Java 完成课程预约查询接口，并编写测试记录。", "fact_ids": ["e1"]},
]}]}
PLAN = {"decision": "draft", "selected_fact_ids": ["e1"], "focus": ["接口实现"], "gaps": ["缺少结果数据"]}
PASS = {"verdict": "pass", "issues": [], "strengths": ["个人动作明确"]}
BLOCK = {"verdict": "blocked", "issues": [{"item_id": "item1", "severity": "blocking", "code": "unsupported", "message": "缺少依据"}]}


class ScriptedModel:
    def __init__(self, outputs):
        self.outputs = list(outputs)
        self.calls = []

    async def complete(self, config, stage, context, schema):
        self.calls.append((stage, context, config.model))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        from app.generation_models import WritingReview
        from tests_support import fixture_quality

        if schema is WritingReview and "quality" not in output:
            output = {**output, "quality": fixture_quality()}
        return Completion(schema.model_validate(output), {"total_tokens": 10})


def setup(tmp_path, outputs):
    from app.jobs import JobStore
    from app.workflow import Workflow

    store = ResumeStore(tmp_path / "resumes.sqlite3")
    jobs = JobStore(store)
    registry = ModelRegistry()
    registry.register(ProviderConfig(provider="custom", base_url="http://127.0.0.1:12345/v1", model="original-model", api_key="private-key-not-on-disk"))
    model = ScriptedModel(outputs)
    return Workflow(store, jobs, registry, model), jobs, store, registry, model


def request(**kwargs):
    return GenerationInput(request_id="request-0001", target_role="Java 后端", name="测试用户", contact="me@example.com",
                           source_text=kwargs.pop("source_text", MATERIAL), send_materials=True, **kwargs)


def test_generation_is_idempotent_and_candidate_must_be_adopted(tmp_path):
    runner, jobs, store, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    assert runner.submit(request())["id"] == job["id"]
    with pytest.raises(Conflict):
        runner.submit(request(source_text="不同材料"))
    asyncio.run(runner.run_one())
    finished = jobs.get(job["id"])
    assert finished["state"] == "ready" and finished["review"]["verdict"] == "pass"
    assert finished["calls"] == 3
    assert store.list() == []
    review_context = model.calls[-1][1]
    assert "plan" not in review_context and "focus" not in review_context
    assert MATERIAL in json.dumps(review_context, ensure_ascii=False)
    assert "me@example.com" not in json.dumps(model.calls, ensure_ascii=False)
    resume = runner.adopt(job["id"])
    assert runner.adopt(job["id"]).id == resume.id
    assert resume.origin == "ai" and resume.ai.review_status == "passed"
    assert len(store.list()) == 1
    assert "private-key-not-on-disk" not in json.dumps(finished)


def test_questions_can_be_skipped_once_and_do_not_reset_budget(tmp_path):
    ask = {"decision": "ask", "selected_fact_ids": ["e1"], "questions": [{"id": "q1", "text": "本人交付了什么？"}]}
    runner, jobs, _, _, model = setup(tmp_path, [ask, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    waiting = jobs.get(job["id"])
    assert waiting["state"] == "waiting_input" and waiting["calls"] == 1
    payload = {"question_group": waiting["question_group"], "skip": True, "answers": {}}
    runner.answer(job["id"], payload)
    runner.answer(job["id"], payload)
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["calls"] == 3
    assert model.calls[1][0] == "draft"


def test_no_personal_material_produces_framework_without_model_call(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [])
    job = runner.submit(request(source_text=""))
    assert jobs.get(job["id"])["state"] == "ready"
    assert jobs.get(job["id"])["framework"] is True
    assert model.calls == []


def test_blocked_review_is_not_passed_and_only_two_revisions_are_allowed(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, BLOCK, DRAFT, BLOCK, DRAFT, BLOCK])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready" and result["review"]["verdict"] == "blocked"
    assert result["revisions"] == 2 and result["calls"] == 7
    assert len(model.calls) == 7
    assert runner.adopt(job["id"]).ai.review_status == "blocked"


def test_cancel_discards_late_response(tmp_path):
    runner, jobs, store, _, _ = setup(tmp_path, [])
    entered = asyncio.Event()
    release = asyncio.Event()

    class SlowModel:
        async def complete(self, config, stage, context, schema):
            entered.set()
            await release.wait()
            return Completion(schema.model_validate(PLAN), {})

    runner.client = SlowModel()
    job = runner.submit(request())

    async def run():
        task = asyncio.create_task(runner.run_one())
        await entered.wait()
        runner.cancel(job["id"])
        release.set()
        await task

    asyncio.run(run())
    assert jobs.get(job["id"])["state"] == "cancelled"
    assert jobs.get(job["id"])["plan"] is None
    assert store.list() == []


def test_model_failure_resume_keeps_completed_steps_and_pinned_config(tmp_path):
    runner, jobs, _, registry, model = setup(tmp_path, [PLAN, ProviderError("模型限流"), DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["state"] == "failed"
    registry.register(ProviderConfig(provider="custom", base_url="http://127.0.0.1:54321/v1", model="different-model", api_key="new-secret"))
    with pytest.raises(Conflict):
        runner.resume(job["id"])
    registry.register(ProviderConfig(provider="custom", base_url="http://127.0.0.1:12345/v1", model="original-model", api_key="new-secret"))
    runner.resume(job["id"])
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["calls"] == 4
    assert [c[0] for c in model.calls] == ["plan", "draft", "draft", "review"]


def test_restart_marks_unfinished_jobs_interrupted_without_spending_calls(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [])
    job = runner.submit(request())
    jobs.recover_unfinished()
    assert jobs.get(job["id"])["state"] == "interrupted"
    assert jobs.get(job["id"])["calls"] == 0 and model.calls == []


def test_program_check_blocks_invented_metric_before_semantic_review(tmp_path):
    wrong = {"sections": [{"id": "p", "title": "项目经历", "items": [
        {"id": "item1", "text": "性能提升 99%", "fact_ids": ["e1"]},
    ]}]}
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, wrong, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    assert [c[0] for c in model.calls] == ["plan", "draft", "revise", "review"]
    assert jobs.get(job["id"])["review"]["verdict"] == "pass"


def test_ai_edit_invalidates_review_and_confirmation_cannot_bypass_export_gate(tmp_path):
    from app.exports import check_export
    from app.models import ExportRequest

    runner, _, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    resume = runner.adopt(job["id"])
    store.confirm(resume.id, 1)
    check_export(store.get(resume.id), ExportRequest(format="docx", expected_revision=1))
    changed = store.save(resume.id, 1, resume.content.model_copy(update={"summary": "自己修改的介绍"}))
    assert changed.ai.review_status == "unreviewed"
    store.confirm(resume.id, 2)
    with pytest.raises(Conflict):
        check_export(store.get(resume.id), ExportRequest(format="docx", expected_revision=2))


def test_recheck_modified_resume_then_formal_export_is_allowed(tmp_path):
    from app.exports import check_export
    from app.models import ExportRequest

    runner, jobs, store, _, model = setup(tmp_path, [PLAN, DRAFT, PASS, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    resume = runner.adopt(job["id"])
    content = resume.content.model_copy(update={"name": "新姓名"})
    store.save(resume.id, 1, content)
    review = runner.recheck(resume.id, 2, "recheck-0001")
    asyncio.run(runner.run_one())
    assert jobs.get(review["id"])["state"] == "ready"
    current = store.get(resume.id)
    assert current.ai.review_status == "passed" and current.content.name == "新姓名"
    store.confirm(resume.id, 2)
    check_export(store.get(resume.id), ExportRequest(format="docx", expected_revision=2))
    assert model.calls[-1][0] == "review"


def test_known_blocking_issues_cannot_be_cleared_by_manual_takeover(tmp_path):
    runner, _, _, _, _ = setup(tmp_path, [PLAN, DRAFT, BLOCK, DRAFT, BLOCK, DRAFT, BLOCK])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    resume = runner.adopt(job["id"])
    with pytest.raises(Conflict):
        runner.takeover(resume.id, 1)


def test_review_failure_still_allows_adopting_a_clearly_unreviewed_draft(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, ProviderError("模型暂时不可用")])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["state"] == "failed"
    resume = runner.adopt(job["id"])
    assert resume.ai.review_status == "unreviewed"


def test_missing_credential_does_not_charge_a_model_call(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [])
    job = runner.submit(request())
    runner.registry = ModelRegistry()
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["calls"] == 0
    assert model.calls == []


def test_structural_retry_is_bounded_and_charged(tmp_path):
    from app.model_client import ModelOutputError

    runner, jobs, _, _, model = setup(tmp_path, [ModelOutputError("结构错误"), ModelOutputError("结构错误")])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["state"] == "failed"
    assert jobs.get(job["id"])["calls"] == 2 and len(model.calls) == 2
    with pytest.raises(Conflict):
        runner.resume(job["id"])


def test_budget_is_preserved_and_never_spends_ninth_call(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN])
    job = runner.submit(request())
    jobs.mutate(job["id"], lambda j, _: j.update(calls=7))
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["calls"] == 8 and len(model.calls) == 1
    assert jobs.get(job["id"])["plan"] is not None
    with pytest.raises(Conflict):
        runner.resume(job["id"])


def test_config_switch_does_not_change_an_inflight_tasks_provider(tmp_path):
    runner, jobs, _, registry, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    registry.register(ProviderConfig(provider="custom", base_url="http://127.0.0.1:54321", model="different", api_key="another-key"))
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["state"] == "ready"
    assert {call[2] for call in model.calls} == {"original-model"}


def test_edit_during_recheck_cannot_attach_stale_pass(tmp_path):
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job["id"])
    recheck = runner.recheck(record.id, 1, "recheck-race-001")

    class EditingReviewer:
        async def complete(self, config, stage, context, schema):
            store.save(record.id, 1, record.content.model_copy(update={"name": "并发修改"}))
            return Completion(schema.model_validate(PASS), {})

    runner.client = EditingReviewer()
    asyncio.run(runner.run_one())
    assert jobs.get(recheck["id"])["state"] == "failed"
    assert store.get(record.id).ai.review_status == "unreviewed"


def test_shutdown_interrupts_inflight_call_and_keeps_consumed_budget(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [])
    entered = asyncio.Event()

    class SlowModel:
        async def complete(self, config, stage, context, schema):
            entered.set()
            await asyncio.sleep(30)

    runner.client = SlowModel()

    async def run():
        await runner.start()
        job = runner.submit(request())
        await entered.wait()
        await runner.close()
        current = jobs.get(job["id"])
        assert current["state"] == "interrupted"
        assert current["calls"] == 1 and current["request_started"] is None

    asyncio.run(run())


def test_answer_keeps_original_restrictions_and_adds_new_evidence(tmp_path):
    ask = {"decision": "ask", "selected_fact_ids": ["e1"], "questions": [{"id": "q1", "text": "测试交付是什么？"}]}
    runner, jobs, _, _, model = setup(tmp_path, [ask, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    waiting = jobs.get(job["id"])
    runner.answer(job["id"], {"question_group": waiting["question_group"], "answers": {"q1": "整理测试记录"}})
    asyncio.run(runner.run_one())
    sources = model.calls[1][1]["evidence"]
    assert any(e["id"] == "e1" and "未上线" in e["text"] for e in sources)
    assert any(e["id"].startswith("a") and e["text"] == "整理测试记录" for e in sources)


def test_storage_failure_does_not_silently_kill_worker_or_replay_paid_work(tmp_path, monkeypatch):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    original = jobs.claim_next
    broken = True
    seen = asyncio.Event()

    def failing_claim():
        if broken:
            seen.set()
            raise OSError("simulated disk unavailable")
        return original()

    monkeypatch.setattr(jobs, "claim_next", failing_claim)

    async def run():
        nonlocal broken
        await runner.start()
        job = runner.submit(request())
        await asyncio.wait_for(seen.wait(), 1)
        await asyncio.sleep(0)
        assert runner.service_warning
        broken = False
        for _ in range(100):
            if jobs.get(job["id"])["state"] == "interrupted":
                break
            await asyncio.sleep(0.02)
        assert jobs.get(job["id"])["state"] == "interrupted"
        assert model.calls == []
        runner.resume(job["id"])
        for _ in range(100):
            if jobs.get(job["id"])["state"] == "ready":
                break
            await asyncio.sleep(0.02)
        assert jobs.get(job["id"])["state"] == "ready"
        await runner.close()

    asyncio.run(run())


@pytest.mark.parametrize("action", ["recheck", "takeover"])
def test_empty_section_heading_cannot_escape_fact_checks(tmp_path, action):
    from app.models import Section

    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job["id"])
    content = record.content.model_copy(update={"sections": [*record.content.sections,
                                        Section(id="unreviewed-heading", title="Redis 精通，性能提升 99%", items=[])]})
    store.save(record.id, 1, content)
    if action == "takeover":
        with pytest.raises(Conflict):
            runner.takeover(record.id, 2)
    else:
        recheck = runner.recheck(record.id, 2, "heading-check-001")
        asyncio.run(runner.run_one())
        result = jobs.get(recheck["id"])
        assert any(issue["item_id"] == "unreviewed-heading" for issue in result["issues"])
        assert store.get(record.id).ai.review_status == "blocked"


@pytest.mark.parametrize("case", ["long_item", "many_items", "many_sections", "long_document"])
def test_all_editor_limits_are_supported_by_recheck_and_manual_takeover(tmp_path, case):
    from app.models import Item, Section

    runner, jobs, store, _, model = setup(tmp_path, [PLAN, DRAFT, PASS, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job["id"])
    if case == "long_item":
        sections = [Section(id="s", title="项目经历", items=[Item(id="long", text="一" * 2001)])]
    elif case == "many_items":
        sections = [Section(id="s", title="项目经历", items=[Item(id=f"i{index}", text="编写测试记录") for index in range(16)])]
    elif case == "many_sections":
        sections = [Section(id=f"s{index}", title="项目经历", items=[Item(id=f"i{index}", text="编写测试记录")]) for index in range(9)]
    else:
        sections = [Section(id=f"s{index}", title="项目经历", items=[Item(id=f"i{index}", text="一" * 1900)]) for index in range(8)]
    store.save(record.id, 1, record.content.model_copy(update={"sections": sections}))
    takeover = runner.takeover(record.id, 2)
    assert takeover.ai.manual_takeover
    recheck = runner.recheck(record.id, 2, f"limit-check-{case}")
    asyncio.run(runner.run_one())
    assert jobs.get(recheck["id"])["state"] == "ready"
    sent = model.calls[-1][1]["candidate"]["sections"]
    assert sum(len(i["text"]) for s in sent for i in s["items"]) == sum(len(i.text) for s in sections for i in s.items)


@pytest.mark.parametrize("reinsert_id", ["item1", "renamed-item"])
def test_removed_problem_item_can_be_manually_resolved_without_model(tmp_path, reinsert_id):
    from app.exports import check_export
    from app.models import ExportRequest, Item

    draft = json.loads(json.dumps(DRAFT))
    draft["sections"][0]["items"].append({"id": "item2", "text": "编写测试记录。", "fact_ids": ["e1"]})
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, draft, BLOCK, draft, BLOCK, draft, BLOCK])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job["id"])
    content = record.content.model_copy(deep=True)
    content.sections[0].items = [item for item in content.sections[0].items if item.id != "item1"]
    store.save(record.id, 1, content)
    runner.registry = ModelRegistry()
    adopted = runner.takeover(record.id, 2)
    assert adopted.ai.manual_takeover
    assert adopted.ai.issues[0]["resolution"]["action"] == "deleted"
    assert "resolution" not in jobs.get(job["id"])["issues"][0]
    store.confirm(record.id, 2)
    check_export(store.get(record.id), ExportRequest(format="docx", expected_revision=2))
    content.sections[0].items.append(Item(id=reinsert_id, text=DRAFT["sections"][0]["items"][0]["text"]))
    store.save(record.id, 2, content)
    with pytest.raises(Conflict):
        runner.takeover(record.id, 3)


def test_legitimate_empty_heading_is_sent_to_reviewer_without_omission(tmp_path):
    from app.models import Section

    runner, _, store, _, model = setup(tmp_path, [PLAN, DRAFT, PASS, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job["id"])
    content = record.content.model_copy(update={"sections": [*record.content.sections, Section(id="empty", title="教育背景", items=[])]})
    store.save(record.id, 1, content)
    runner.recheck(record.id, 2, "empty-heading-full")
    asyncio.run(runner.run_one())
    heading = model.calls[-1][1]["candidate"]["sections"][-1]
    assert {key: heading[key] for key in ("id", "title", "items")} == {"id": "empty", "title": "教育背景", "items": []}


def test_structural_retry_receives_safe_feedback_and_persists_reason(tmp_path):
    from app.model_client import ModelOutputError

    error = ModelOutputError("结构不匹配", diagnostic={"category": "schema", "fields": [{"path": "/summary/id", "type": "literal_error"}]})
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, error, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready"
    assert model.calls[2][1]["validation_feedback"]["fields"][0]["path"] == "/summary/id"
    assert "validation_feedback" not in model.calls[3][1]
    assert result["call_log"][1]["diagnostic"]["category"] == "schema"


def test_contract_upgrade_allows_explicit_resume_without_resetting_global_budget(tmp_path):
    from app.model_client import OUTPUT_CONTRACT_VERSION

    runner, jobs, _, _, model = setup(tmp_path, [DRAFT, PASS])
    job = runner.submit(request())
    jobs.mutate(job["id"], lambda j, _: j.update(state="failed", stage="draft", plan=PLAN, calls=3,
                elapsed_ms=15000, invalid_outputs={"draft:0": 2}, output_contract_version="legacy"))
    resumed = runner.resume(job["id"])
    assert resumed["calls"] == 3 and resumed["elapsed_ms"] == 15000
    assert resumed["output_contract_version"] == OUTPUT_CONTRACT_VERSION
    assert resumed["validation_history"][0]["invalid_outputs"] == {"draft:0": 2}
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["calls"] == 5
    assert [call[0] for call in model.calls] == ["draft", "review"]


def test_reviewer_receives_trusted_reference_date(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    jobs.mutate(job["id"], lambda j, _: j.update(created_at="2026-11-04T18:20:00+00:00"))
    asyncio.run(runner.run_one())
    assert model.calls[-1][1]["reference_date"] == "2026-11-05"
    assert model.calls[-1][1]["reference_timezone"] == "Asia/Shanghai"


def blocked_resume(tmp_path):
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, BLOCK, DRAFT, BLOCK, DRAFT, BLOCK])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    return runner, jobs, store, job, runner.adopt(job["id"])


def manual_resolution(record, **changes):
    return {"expected_revision": record.revision, "review_job_id": record.ai.review_job_id, "issue_index": 0,
            "evidence_ids": ["e1"], "explanation": "原文明确说明本人完成接口实现，与当前表述一致。", "acknowledged": True, **changes}


def test_source_backed_manual_resolution_preserves_ai_verdict_and_allows_explicit_takeover(tmp_path):
    from app.exports import check_export
    from app.models import ExportRequest

    runner, jobs, store, job, record = blocked_resume(tmp_path)
    original_issues = jobs.get(job["id"])["issues"]
    runner.registry = ModelRegistry()
    resolved = runner.resolve_issue(record.id, manual_resolution(record))
    assert resolved.ai.review_status == "blocked" and not resolved.ai.manual_takeover
    assert resolved.ai.issues[0]["resolution"]["action"] == "source_reviewed"
    assert len(resolved.ai.resolution_history) == 1
    assert runner.resolve_issue(record.id, manual_resolution(record)).ai.resolution_history == resolved.ai.resolution_history
    assert jobs.get(job["id"])["issues"] == original_issues
    store.confirm(record.id, 1)
    with pytest.raises(Conflict):
        check_export(store.get(record.id), ExportRequest(format="docx", expected_revision=1))
    runner.takeover(record.id, 1)
    store.confirm(record.id, 1)
    check_export(store.get(record.id), ExportRequest(format="docx", expected_revision=1))


@pytest.mark.parametrize("changes", [{"evidence_ids": ["not-owned"]}, {"expected_revision": 2}, {"review_job_id": "wrong-report"}, {"acknowledged": False}])
def test_manual_resolution_requires_current_report_owned_evidence_and_acknowledgment(tmp_path, changes):
    runner, _, _, _, record = blocked_resume(tmp_path)
    with pytest.raises((Conflict, ValueError)):
        runner.resolve_issue(record.id, manual_resolution(record, **changes))


def test_manual_resolution_cannot_bypass_missing_numeric_evidence_and_edits_invalidate_resolution(tmp_path):
    from app.models import Item

    runner, _, store, _, record = blocked_resume(tmp_path)
    runner.resolve_issue(record.id, manual_resolution(record))
    content = record.content.model_copy(deep=True)
    content.sections[0].items = [Item(id="item1", text="性能提升 99%")]
    changed = store.save(record.id, 1, content)
    assert changed.ai.has_blockers()
    with pytest.raises(Conflict):
        runner.resolve_issue(record.id, manual_resolution(changed))


def test_manual_resolution_accepts_program_reports_larger_than_model_issue_limit(tmp_path):
    runner, _, store, _, record = blocked_resume(tmp_path)
    issues = [dict(record.ai.issues[0]) for _ in range(41)]
    with store.engine.begin() as connection:
        store.write_ai(connection, record.id, record.revision, record.ai.model_copy(update={"issues": issues}))
    resolved = runner.resolve_issue(record.id, manual_resolution(record, issue_index=40))
    assert resolved.ai.issues[40]["resolution"]["action"] == "source_reviewed"
    assert resolved.ai.has_blockers()
    with pytest.raises(Conflict):
        runner.takeover(record.id, record.revision)
    with pytest.raises(Conflict, match="问题不存在"):
        runner.resolve_issue(record.id, manual_resolution(record, issue_index=41))


def test_fixed_education_is_used_verbatim_instead_of_model_rewriting(tmp_path):
    from app.models import Education

    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    fixed = Education(id="edu1", school="虚构测试学院", major="计算机", degree="硕士", start_date="2024-09", end_date="至今")
    job = runner.submit(request(education=[fixed]))
    asyncio.run(runner.run_one())
    adopted = runner.adopt(job["id"])
    assert adopted.content.education == [fixed]
    assert jobs.get(job["id"])["draft"]["education"][0]["school"] == fixed.school
    assert "profile-edu1-1" in adopted.ai.source_map["edu1"]
    assert "me@example.com" not in json.dumps(model.calls, ensure_ascii=False)


def test_long_draft_triggers_bounded_editorial_revision_even_if_model_review_passes(tmp_path):
    long_draft = json.loads(json.dumps(DRAFT))
    long_draft["sections"][0]["items"][0]["text"] = "使用 Java 完成课程预约查询接口，并编写测试记录。" * 7
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, long_draft, PASS, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["state"] == "ready"
    assert [call[0] for call in model.calls] == ["plan", "draft", "review", "revise", "review"]
    assert any(i["code"] == "quality" for i in model.calls[3][1]["issues_to_fix"])


def test_generation_requires_basic_identity_before_paid_calls(tmp_path):
    runner, _, _, _, model = setup(tmp_path, [])
    payload = request().model_copy(update={"name": "", "contact": ""})
    with pytest.raises(ValueError, match="姓名"):
        runner.submit(payload)
    assert model.calls == []


def test_reviewer_can_report_education_issues_without_structure_retry(tmp_path):
    from app.models import Education

    warning = {"verdict": "pass", "issues": [{"item_id": "edu1", "severity": "warning", "code": "quality", "message": "教育时间需要用户补充"}]}
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, warning])
    job = runner.submit(request(education=[Education(id="edu1", school="虚构学校", degree="本科")]))
    asyncio.run(runner.run_one())
    finished = jobs.get(job["id"])
    assert finished["state"] == "ready"
    assert finished["calls"] == 3
    assert finished["issues"][0]["item_id"] == "edu1"


def test_semantic_quality_requests_revision_even_for_short_factually_correct_draft(tmp_path):
    from tests.test_writing_coach import quality

    review = {**PASS, "quality": quality("revise")}
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, review, DRAFT, {**PASS, "quality": quality()}])
    job = runner.submit(request(career_stage="transition", has_career_gap=True))
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready"
    assert [call[0] for call in model.calls] == ["plan", "draft", "review", "revise", "review"]
    assert any(i["code"] == "fit" for i in model.calls[3][1]["issues_to_fix"])
    assert runner.adopt(job["id"]).ai.quality["status"] == "ready"
    assert model.calls[0][1]["candidate_context"] == {"career_stage": "transition", "has_career_gap": True}
    assert "references/questions.md" in model.calls[0][1]["loaded_resources"]
    assert "references/questions.md" not in model.calls[1][1]["loaded_resources"]


def test_quality_gap_is_not_infinite_rewrite_or_fact_block(tmp_path):
    from tests.test_writing_coach import quality

    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, {**PASS, "quality": quality("insufficient")}])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready" and len(model.calls) == 3
    row = runner.adopt(job["id"])
    assert row.ai.review_status == "passed" and row.ai.quality["status"] == "insufficient"
    assert not row.ai.has_blockers()


def test_quality_references_are_checked_and_original_budget_is_preserved(tmp_path):
    from tests.test_writing_coach import quality

    bad = quality()
    bad["dimensions"][0]["evidence_ids"] = ["not-owned"]
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, {**PASS, "quality": bad}, {**PASS, "quality": quality()}])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    result = jobs.get(job["id"])
    assert result["state"] == "ready" and result["calls"] == 4
    assert result["call_log"][2]["outcome"] == "invalid_output"


def test_legacy_skill_snapshot_remains_readable_and_has_no_implied_quality_score(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())

    def legacy(current, _):
        for key in ("stage_instructions", "stage_resources", "resources"):
            current["skill"].pop(key)

    jobs.mutate(job["id"], legacy)
    asyncio.run(runner.run_one())
    assert jobs.get(job["id"])["state"] == "ready"
    record = runner.adopt(job["id"])
    assert record.ai.review_status == "passed" and record.ai.quality is None


def test_editing_invalidates_quality_without_overwriting_original_job_report(tmp_path):
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job["id"])
    assert record.ai.quality["status"] == "ready"
    content = record.content.model_copy(deep=True)
    content.sections[0].items[0].text = "使用 Java 完成课程预约查询接口。"
    changed = store.save(record.id, record.revision, content)
    assert changed.ai.quality is None and changed.ai.review_status == "unreviewed"
    assert jobs.get(job["id"])["review"]["quality"]["status"] == "ready"
