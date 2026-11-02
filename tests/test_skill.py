import pytest


@pytest.mark.parametrize(("role", "expected"), [
    ("Java 开发", "backend"), ("推荐算法", "algorithm"), ("NLP 算法", "algorithm"),
    ("计算机视觉", "algorithm"), ("数据分析师", "data-analysis"), ("产品经理", "product"),
    ("用户运营", "operations"), ("法务", "general"),
])
def test_role_rules_are_selected_without_becoming_personal_facts(role, expected):
    from app.skill import load_skill

    skill = load_skill(role)
    assert skill.role == expected
    assert "不得" in skill.instructions
    assert "个人事实" in skill.instructions
    assert skill.version


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
