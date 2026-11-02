from io import BytesIO

import pytest
from docx import Document

from app.generation_models import Draft
from app.models import ResumeContent


def structured():
    return {
        "name": "虚构测试用户", "contact": "fixture@example.com", "target_role": "Agent 应用实习",
        "education": [{"id": "edu1", "school": "虚构学院", "degree": "硕士（在读）", "major": "计算机",
                       "start_date": "2024-09", "end_date": "至今"}],
        "sections": [{"id": "p1", "kind": "project", "title": "查询助手", "organization": "个人项目",
                      "role": "开发", "start_date": "2025-02", "end_date": "2025-06", "items": [
                          {"id": "i1", "text": "使用 Python 完成查询接口，交付测试记录。", "highlights": ["查询接口", "测试记录"]}]}],
    }


def test_structured_content_renders_fixed_education_dates_and_safe_highlights():
    from app.rendering import expected_texts, render_docx, render_html

    content = ResumeContent.model_validate(structured())
    html = render_html(content)
    assert "教育经历" in html and "虚构学院" in html
    assert "2025-02" in html and "2025-06" in html
    assert "<strong>查询接口</strong>" in html
    doc = Document(BytesIO(render_docx(content, False, False)))
    text = "\n".join(p.text for p in doc.paragraphs)
    assert "虚构学院" in text and "2024-09" in text and "2025-06" in text
    assert any(r.bold and r.text == "查询接口" for p in doc.paragraphs for r in p.runs)
    assert any("虚构学院" in text for text in expected_texts(content))


def test_reverse_chronology_is_stable_with_unknown_dates_and_separate_categories():
    from app.models import Section
    from app.resume_layout import ordered_sections

    rows = [Section(id="old", title="旧项目", kind="project", end_date="2023"),
            Section(id="work", title="工作", kind="work", end_date="2021"),
            Section(id="unknown", title="未知时间", kind="project"),
            Section(id="now", title="当前项目", kind="project", end_date="至今"),
            Section(id="new", title="较新项目", kind="project", end_date="2025-06")]
    assert [s.id for s in ordered_sections(rows)] == ["now", "work", "new", "old", "unknown"]


@pytest.mark.parametrize("change", [{"start_date": "2025-13"}, {"start_date": "2025-09", "end_date": "2024-10"},
                                   {"start_date": "昨天"}])
def test_invalid_or_reversed_dates_are_rejected(change):
    payload = structured()
    payload["sections"][0].update(change)
    with pytest.raises(ValueError):
        ResumeContent.model_validate(payload)


def test_unknown_dates_are_allowed_and_highlights_cannot_introduce_new_words():
    payload = structured()
    payload["sections"][0].update(start_date="", end_date="")
    payload["sections"][0]["items"][0]["highlights"] = ["精通算法"]
    with pytest.raises(ValueError):
        ResumeContent.model_validate(payload)


def test_review_projection_keeps_every_structured_field_and_highlight():
    from app.generation_service import content_draft

    content = ResumeContent.model_validate(structured())
    draft = content_draft(content, [{"id": "e1"}], {})
    assert draft.education[0].school == "虚构学院"
    assert draft.sections[0].end_date == "2025-06"
    assert draft.sections[0].organization == "个人项目"
    assert draft.sections[0].items[0].highlights == ["查询接口", "测试记录"]


def test_program_checks_invented_experience_dates_and_education():
    from app.skill import build_evidence, validate_draft

    data = structured()
    data.pop("name"); data.pop("contact"); data.pop("target_role")
    data["education"][0]["fact_ids"] = ["e1"]
    data["sections"][0]["fact_ids"] = ["e1"]
    data["sections"][0]["items"][0]["fact_ids"] = ["e1"]
    issues = validate_draft(Draft.model_validate(data), build_evidence("使用 Python 完成查询接口，交付测试记录。"))
    assert any(i.item_id == "p1" and i.severity == "blocking" for i in issues)
    assert any(i.item_id == "edu1" and i.severity == "blocking" for i in issues)


def test_readability_warnings_are_actionable_and_do_not_claim_factual_errors():
    from app.skill import validate_quality

    draft = Draft.model_validate({"summary": {"id": "__summary", "text": "持续学习。" * 30, "fact_ids": ["e1"]},
        "sections": [{"id": "p1", "title": "个人项目", "kind": "project", "items": [
            {"id": "i1", "text": "负责整理数据并开展实验。" * 15, "fact_ids": ["e1"]}]}]})
    issues = validate_quality(draft)
    assert any(i.item_id == "i1" and "压缩" in i.message for i in issues)
    assert any(i.item_id == "__summary" for i in issues)
    assert all(i.severity == "warning" and i.code == "quality" for i in issues)


def test_dates_cannot_be_recombined_from_separate_source_periods():
    from app.skill import build_evidence, validate_draft

    draft = Draft.model_validate({"sections": [{"id": "p1", "kind": "project", "title": "查询项目", "start_date": "2025-09",
        "items": [{"id": "i1", "text": "完成查询接口。", "fact_ids": ["e1"]}], "fact_ids": ["e1"]}]})
    issues = validate_draft(draft, build_evidence("查询项目：2024.09—2025.06，完成查询接口。"))
    assert any(i.item_id == "p1" and i.code == "unsupported" for i in issues)


@pytest.mark.parametrize("target,expected", [("Agent 应用开发实习", "algorithm"), ("RAG 工程师", "algorithm"),
                                            ("大模型产品经理", "product")])
def test_specialized_role_routing_is_about_the_job_not_only_technology_words(target, expected):
    from app.skill import load_skill

    assert load_skill(target).role == expected


def test_empty_education_is_rejected_and_legacy_content_still_loads():
    with pytest.raises(ValueError):
        ResumeContent.model_validate({"education": [{"id": "empty"}]})
    assert ResumeContent.model_validate({"sections": [{"id": "old", "title": "旧简历", "items": [{"id": "i", "text": "保留原文"}]}]}).education == []


def test_structured_headings_cannot_be_hidden_by_reusing_ids():
    payload = structured()
    payload["education"][0]["id"] = "i1"
    with pytest.raises(ValueError):
        ResumeContent.model_validate(payload)


def test_legacy_content_hash_stays_valid_until_new_fields_are_added():
    import hashlib
    import json

    from app.models import resume_hash

    original = {"name": "测试", "target_role": "开发", "contact": "fixture@example.com", "summary": "",
                "sections": [{"id": "p1", "title": "项目", "items": [{"id": "i1", "text": "完成查询接口"}]}]}
    legacy_hash = hashlib.sha256(json.dumps(original, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
    content = ResumeContent.model_validate(original)
    assert resume_hash(content) == legacy_hash
    content.sections[0].start_date = "2025"
    assert resume_hash(content) != legacy_hash


@pytest.mark.parametrize("legacy_id", ["p1", "__summary"])
def test_legacy_section_item_names_remain_readable(legacy_id):
    content = ResumeContent.model_validate({"sections": [{"id": legacy_id, "title": "旧经历", "items": [
        {"id": legacy_id, "text": "保留原文"}]}]})
    assert content.sections[0].items[0].text == "保留原文"


def test_adjacent_projects_share_one_category_heading():
    from app.rendering import render_docx, render_html

    data = structured()
    second = {**data["sections"][0], "id": "p2", "title": "另一个项目", "items": [{"id": "i2", "text": "整理测试记录"}]}
    data["sections"].append(second)
    content = ResumeContent.model_validate(data)
    assert render_html(content).count("<h2>项目经历</h2>") == 1
    assert sum(p.text == "项目经历" for p in Document(BytesIO(render_docx(content, False, False))).paragraphs) == 1
