import pytest


@pytest.mark.parametrize(("direction", "expected"), [
    ("product", "product"),
    ("backend", "backend"),
    ("data-engineering", "data-engineering"),
    ("algorithm", "algorithm"),
    ("data-analysis", "data-analysis"),
    ("operations", "operations"),
    ("frontend", "frontend"),
    ("testing", "testing"),
    ("other", "general"),
    (None, "general"),
])
def test_role_rules_are_selected_without_becoming_personal_facts(direction, expected):
    from app.skill import load_skill

    skill = load_skill("任意岗位标题", role_direction=direction)
    assert skill.role == expected
    assert "不得" in skill.instructions
    assert "个人事实" in skill.instructions
    assert skill.version


def test_pinned_role_keeps_the_frozen_skill_when_direction_changes():
    from app.skill import load_skill

    skill = load_skill("算法工程师", role_direction="product", pinned_role="algorithm")
    assert skill.role == "algorithm"
    assert "references/roles/algorithm.md" in skill.resources


def test_stage_load_keeps_editorial_and_role_files_without_rejected_rules():
    from app.skill import load_skill

    bundle = load_skill("算法工程师", role_direction="algorithm")
    assert "references/editorial.md" in bundle.stage_resources["draft"]
    assert "references/editorial.md" in bundle.stage_resources["revise"]
    assert "references/editorial.md" not in bundle.stage_resources["plan"]
    assert "references/editorial.md" not in bundle.stage_resources["review"]
    for stage, paths in bundle.stage_resources.items():
        assert f"references/roles/{bundle.role}.md" in paths
        assert "references/writing-sources.md" not in paths
        assert "writing-sources" not in bundle.stage_instructions[stage]
        assert "Paramchoudhary/ResumeSkills" not in bundle.stage_instructions[stage]
    draft = bundle.stage_instructions["draft"]
    assert "不查学校官网" in draft
    assert "不要推算出材料没写的百分点差值" in draft
    assert "不要加「负责业务」「工作职责」" in draft
    assert "也不能从正文自动抽出来" in draft


def test_quantity_and_date_gates_share_safe_normalization():
    from app.generation_models import Draft
    from app.skill import build_evidence, repair_period_citations, validate_draft

    evidence = build_evidence("覆盖 10名 用户。接口耗时降低百分之30。第1项完成查询接口。")
    ordinal = Draft.model_validate({"sections": [{"id": "projects", "title": "项目经历", "items": [
        {"id": "item1", "text": "第1项完成查询接口，覆盖 10人，耗时降低 30%。", "fact_ids": ["e1"]},
    ]}]})
    assert not any(issue.code == "unsupported" and "数字" in issue.message for issue in validate_draft(ordinal, evidence))
    invented = Draft.model_validate({"sections": [{"id": "projects", "title": "项目经历", "items": [
        {"id": "item1", "text": "完成查询接口，另用 3个月。", "fact_ids": ["e1"]},
    ]}]})
    assert any(issue.code == "unsupported" and "数字" in issue.message for issue in validate_draft(invented, evidence))

    dated = build_evidence("澄湾实习\n2024.09 到 2025-03 完成查询接口。")
    missing_cite = Draft.model_validate({"sections": [{"id": "work", "title": "实习", "organization": "澄湾实习", "start_date": "2024-09", "items": [
        {"id": "item1", "text": "完成查询接口。", "fact_ids": ["e1"]},
    ]}]})
    # The period lives in the only chunk, which is already cited.
    assert not any("经历时间" in issue.message for issue in validate_draft(missing_cite, dated))
    inferred = Draft.model_validate({"sections": [{"id": "work", "title": "实习", "organization": "澄湾实习", "start_date": "2024-07", "items": [
        {"id": "item1", "text": "2024年暑假参加澄湾实习。", "fact_ids": ["e1"]},
    ]}]})
    summer = build_evidence("2024年暑假参加澄湾实习。")
    assert any("经历时间" in issue.message for issue in validate_draft(inferred, summer))

    split = build_evidence("完成查询接口。") + build_evidence("澄湾实习 2024-09 开始。", prefix="p")
    draft = {"sections": [{"id": "work", "title": "实习", "organization": "澄湾实习", "start_date": "2024-09", "items": [
        {"id": "item1", "text": "完成查询接口。", "fact_ids": [split[0].id]},
    ]}]}
    repaired = repair_period_citations(draft, [row.model_dump() for row in split])
    assert split[1].id in repaired["sections"][0]["fact_ids"]
    unrelated = build_evidence("完成查询接口。") + build_evidence("另一段 2024-09 的课程。", prefix="p")
    foreign = {"sections": [{"id": "work", "title": "实习", "organization": "澄湾实习", "start_date": "2024-09", "items": [
        {"id": "item1", "text": "完成查询接口。", "fact_ids": [unrelated[0].id]},
    ]}]}
    assert any("经历时间" in issue.message for issue in validate_draft(
        Draft.model_validate(foreign), unrelated))


def test_source_ranges_preserve_original_text_and_restrictions():
    from app.skill import build_evidence

    text = "团队做推荐实验。\n本人只负责离线复现，没有上线。\n" + "一" * 1900
    evidence = build_evidence(text)
    assert len({item.id for item in evidence}) == len(evidence)
    assert all(text[item.start:item.end] == item.text for item in evidence)
    assert "没有上线" in "".join(item.text for item in evidence)


def make_draft(text, fact_ids=None):
    from app.generation_models import Draft

    return Draft.model_validate({"sections": [{"id": "projects", "title": "项目经历", "items": [
        {"id": "item1", "text": text, "fact_ids": fact_ids or ["e1"]},
    ]}]})


def test_unknown_references_and_invented_numbers_block_draft():
    from app.skill import build_evidence, validate_draft

    evidence = build_evidence("使用 Java 完成查询接口，未提供性能收益。")
    assert any(i.code == "reference" for i in validate_draft(make_draft("完成查询接口", ["missing"]), evidence))
    issues = validate_draft(make_draft("使用 Java 完成查询接口，性能提升 50%"), evidence)
    assert any(i.severity == "blocking" and i.code == "unsupported" for i in issues)


def test_existing_test_numbers_are_allowed_but_team_role_is_not_inflated():
    from app.skill import build_evidence, validate_draft

    evidence = build_evidence("团队完成项目；本人编写 100 条测试，未上线。")
    assert not validate_draft(make_draft("本人编写 100 条测试。"), evidence)
    assert any(i.code == "attribution" for i in validate_draft(make_draft("主导团队完成项目。"), evidence))
    assert any(i.code == "conflict" for i in validate_draft(make_draft("项目已上线。"), evidence))


def test_review_cannot_claim_pass_with_blocking_issues():
    from app.generation_models import Review

    with pytest.raises(ValueError):
        Review.model_validate({"verdict": "pass", "issues": [
            {"item_id": "item1", "severity": "blocking", "code": "unsupported", "message": "没有依据"},
        ]})


def test_job_requirement_cannot_supply_an_unstated_technology():
    from app.skill import build_evidence, validate_draft

    evidence = build_evidence("使用 Java 完成查询接口。")
    issues = validate_draft(make_draft("使用 Java 和 Redis 实现查询缓存。"), evidence)
    assert any(issue.code == "unsupported" for issue in issues)
