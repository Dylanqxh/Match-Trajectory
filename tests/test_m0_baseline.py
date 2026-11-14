"""M0 usable slice: fact checks, narrowed context, and explicit role direction."""
import pytest
from test_skill import make_draft
from test_workflow import DRAFT, request, setup


def test_number_moved_onto_another_project_is_blocked_even_inside_one_chunk():
    from app.skill import build_evidence, validate_draft

    source = "项目A提升20%；项目B节省3人天"
    evidence = build_evidence(source)
    issues = validate_draft(make_draft("项目B提升20%", [item.id for item in evidence]), evidence)
    assert any(issue.severity == "blocking" and issue.code == "unsupported" for issue in issues)


def test_equivalent_percent_year_and_same_project_numbers_are_not_new_false_positives():
    from app.skill import build_evidence, validate_draft

    same_project = build_evidence("项目A提升20%，并节省3人天。")
    assert not validate_draft(make_draft("项目A节省3人天。", [item.id for item in same_project]), same_project)
    percent = build_evidence("接口耗时降低30％。")
    assert not validate_draft(make_draft("接口耗时降低30%。"), percent)
    dated = build_evidence("24年9月入职，完成查询接口。")
    assert not validate_draft(make_draft("2024-09入职，完成查询接口。"), dated)
    stated = build_evidence("性能提升3倍。")
    assert not validate_draft(make_draft("性能提升3倍。"), stated)
    paraphrase = build_evidence("性能提升3倍。")
    assert not any(issue.code == "attribution" for issue in validate_draft(make_draft("性能提升数倍。"), paraphrase))


def test_qiantou_blocks_and_unstated_multiple_is_only_a_warning():
    from app.skill import build_evidence, validate_draft

    evidence = build_evidence("参与查询接口，性能有提升。")
    lead = validate_draft(make_draft("牵头查询接口。"), evidence)
    assert any(issue.code == "attribution" and issue.severity == "blocking" for issue in lead)
    owned = build_evidence("牵头完成查询接口。")
    assert not any(issue.code == "attribution" for issue in validate_draft(make_draft("牵头完成查询接口。"), owned))
    inflated = validate_draft(make_draft("性能提升数倍。"), evidence)
    assert any(issue.severity == "warning" and "数倍" in issue.message for issue in inflated)
    assert not any(issue.severity == "blocking" for issue in inflated)
    dramatic = validate_draft(make_draft("性能显著提升。"), evidence)
    assert any(issue.severity == "warning" for issue in dramatic)
    assert not any(issue.severity == "blocking" for issue in dramatic)


def test_empty_source_map_list_does_not_cite_every_evidence_id():
    from test_resume_structure import structured

    from app.generation_service import content_draft
    from app.models import ResumeContent

    content = ResumeContent.model_validate(structured())
    evidence = [{"id": "e1"}, {"id": "e2"}]
    explicit = content_draft(content, evidence, {"i1": [], "p1": []})
    assert explicit.sections[0].items[0].fact_ids == []
    assert explicit.sections[0].fact_ids == []
    missing = content_draft(content, evidence, {})
    assert missing.sections[0].items[0].fact_ids == ["e1", "e2"]


def test_draft_and_revise_use_selected_facts_and_empty_selection_is_not_everything(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [])
    source = "项目A提升20%。\n" + ("项目B节省3人天。补充说明。\n" * 200)
    job = runner.submit(request(source_text=source))
    stored = jobs.get(job["id"])
    assert len(stored["evidence"]) >= 2
    selected = [stored["evidence"][0]["id"]]
    plan = {"decision": "draft", "selected_fact_ids": selected, "focus": [], "questions": [], "gaps": []}
    jobs.mutate(job["id"], lambda current, _: current.update(plan=plan, stage="draft", draft=DRAFT, issues=[]))
    narrowed = runner._context(jobs.get(job["id"]), "draft")
    assert [item["id"] for item in narrowed["evidence"]] == selected
    revised = runner._context(jobs.get(job["id"]), "revise")
    assert [item["id"] for item in revised["evidence"]] == selected
    reviewed = runner._context(jobs.get(job["id"]), "review")
    assert len(reviewed["evidence"]) == len(stored["evidence"])
    jobs.mutate(job["id"], lambda current, _: current.update(plan={**plan, "selected_fact_ids": []}))
    empty = runner._context(jobs.get(job["id"]), "draft")
    assert empty["evidence"] == []


def test_followup_answers_and_profile_facts_stay_when_selection_is_narrow(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [])
    source = "项目A提升20%。\n" + ("项目B节省3人天。补充说明。\n" * 200)
    job = runner.submit(request(source_text=source, education=[{"id": "edu1", "school": "虚构学院", "degree": "本科", "major": "计算机"}]))
    stored = jobs.get(job["id"])
    selected = [stored["evidence"][0]["id"]]
    jobs.mutate(job["id"], lambda current, _: current.update(
        plan={"decision": "draft", "selected_fact_ids": selected, "focus": [], "questions": [], "gaps": []},
        answer_context=[{"question": "补充了什么？", "answer": "补充了压测记录", "fact_ids": ["a0-1"]}],
        evidence=[*current["evidence"], {"id": "a0-1", "text": "补充了压测记录", "start": 0, "end": 7}]))
    context = runner._context(jobs.get(job["id"]), "draft")
    visible = {item["id"] for item in context["evidence"]}
    assert selected[0] in visible and "a0-1" in visible
    assert any(item.startswith("profile-edu1-") for item in visible)
    assert not any("项目B" in item["text"] for item in context["evidence"])


def test_free_text_titles_do_not_infer_a_role_family():
    from app.skill import load_skill

    for title in ("前端开发工程师", "内容理解算法工程师", "用户增长分析师", "增长数据分析",
                  "数据开发工程师", "测试开发", "UI 设计师", "硬件工程师", "Java 开发", "大模型产品经理"):
        assert load_skill(title).role == "general"
        assert load_skill(title, role_direction="other").role == "general"
    assert load_skill("运营专员", role_direction="product").role == "product"
    assert load_skill("产品经理", role_direction="backend").role == "backend"
    assert load_skill("前端开发", pinned_role="algorithm").role == "algorithm"


def test_new_generation_accepts_only_the_direction_enum():
    from pydantic import ValidationError

    from app.generation_models import GenerationInput

    for index, direction in enumerate(("product", "backend", "data-engineering", "algorithm", "data-analysis", "operations", "frontend", "testing", "other"), start=1):
        row = GenerationInput(request_id=f"request-009{index}", target_role="目标岗位", role_direction=direction,
                              name="测试", contact="a@example.com", source_text="完成查询接口", send_materials=True)
        assert row.role_direction == direction
    with pytest.raises(ValidationError):
        GenerationInput(request_id="request-0099", target_role="设计", role_direction="design")


def test_saved_task_without_role_direction_keeps_its_skill_on_retry(tmp_path):
    from app.skill import build_evidence, load_skill

    runner, jobs, _, registry, _ = setup(tmp_path, [])
    inputs = request().model_dump(exclude={"role_direction"})
    old = jobs.create(inputs, registry.current, registry.describe(registry.get(registry.current)),
                      load_skill(inputs["target_role"], pinned_role="algorithm"),
                      [item.model_dump() for item in build_evidence(inputs["source_text"])])
    repeated = runner.submit(request())
    assert repeated["id"] == old["id"]
    assert repeated["skill"]["role"] == "algorithm"
