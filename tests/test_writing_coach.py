import json

import pytest


def quality(status="ready"):
    dimensions = [{"dimension": name, "score": 2, "reason": "可见材料与当前段落提供了具体支撑。", "item_ids": ["document"],
                   "evidence_ids": ["e1"], "action": "keep"} for name in ("fit", "contribution", "evidence", "readability")]
    if status == "revise":
        dimensions[0].update(score=0, reason="原文有预约校验实现，候选只写学习态度，请选入这段实现。", action="revise")
    elif status == "insufficient":
        dimensions[0].update(score=0, reason="原文没有目标能力的实践线索，请提示真实缺口。", action="need_input", evidence_ids=[])
    return {"status": status, "dimensions": dimensions, "interview_topics": []}


def test_runtime_has_phase_routes_and_freezes_selected_resources():
    from app.skill import load_skill

    bundle = load_skill("Java 后端", career_stage="transition", has_career_gap=True, role_direction="backend")
    assert "references/candidates/transition.md" in bundle.resources
    assert "references/candidates/returning.md" in bundle.resources
    assert "references/roles/backend.md" in bundle.resources
    assert "references/roles/operations.md" not in bundle.resources
    assert "references/questions.md" in bundle.stage_resources["plan"]
    assert "references/review-boundaries.md" not in bundle.stage_resources["draft"]
    assert "references/quality-rubric.md" in bundle.stage_resources["review"]
    assert "平庸" in bundle.stage_instructions["draft"]
    assert "个人事实" in bundle.stage_instructions["draft"]
    assert bundle.version != load_skill("Java 后端", role_direction="backend").version


def test_examples_cover_all_roles_without_publishing_evaluation_inputs_as_prompts():
    from pathlib import Path

    cases = json.loads(Path("skills/resume-writing/examples/writing-boundaries.json").read_text(encoding="utf-8"))
    assert {case["role"] for case in cases} == {"backend", "algorithm", "data-analysis", "product", "operations", "general"}
    assert all(case["facts"] and case["ordinary"] and case["improved"] and case["forbidden"] and case["why"] for case in cases)
    assert all("evaluation_reference" not in case for case in cases)


def test_quality_is_separate_from_factual_verdict_and_has_four_complete_dimensions():
    from app.generation_models import WritingReview

    report = WritingReview.model_validate({"verdict": "pass", "quality": quality("revise")})
    assert report.verdict == "pass" and report.quality.status == "revise"
    missing = quality(); missing["dimensions"].pop()
    with pytest.raises(ValueError):
        WritingReview.model_validate({"verdict": "pass", "quality": missing})
    with pytest.raises(ValueError):
        WritingReview.model_validate({"verdict": "pass"})


@pytest.mark.parametrize("change", [{"status": "ready"}, {"bad_action": True}, {"missing_references": True}])
def test_quality_cannot_claim_ready_or_request_rewrite_without_available_support(change):
    from app.generation_models import WritingReview

    payload = quality("revise")
    if "status" in change:
        payload["status"] = change["status"]
    elif "bad_action" in change:
        payload["dimensions"][0].update(score=None, action="revise")
    else:
        payload["dimensions"][0]["evidence_ids"] = []
    with pytest.raises(ValueError):
        WritingReview.model_validate({"verdict": "pass", "quality": payload})


def test_insufficient_material_is_visible_and_does_not_demand_unfounded_rewriting():
    from app.generation_models import WritingReview

    report = WritingReview.model_validate({"verdict": "pass", "quality": quality("insufficient")})
    assert report.quality.status == "insufficient"
    assert not any(row.action == "revise" for row in report.quality.dimensions)


def test_quality_high_scores_require_specific_current_content_and_source():
    from app.generation_models import WritingReview

    payload = quality()
    payload["dimensions"][0].update(item_ids=[], evidence_ids=[])
    with pytest.raises(ValueError):
        WritingReview.model_validate({"verdict": "pass", "quality": payload})
