"""Deterministic checks for a fictional algorithm internship. No live model is called."""
from pathlib import Path

from app.generation_models import Draft

SOURCE = (Path(__file__).parent / "fixtures" / "synthetic_algorithm_intern.txt").read_text(encoding="utf-8")


def _draft(items):
    return Draft.model_validate({"sections": items})


def _kept():
    return _draft([
        {"id": "intern", "title": "北屿智算", "kind": "work", "organization": "北屿智算", "role": "算法实习生",
         "start_date": "2025-03", "end_date": "2025-08", "fact_ids": ["e1"], "items": [
             {"id": "task", "text": "离线推荐召回要在澄湾课程点击子集上对比负样本。现有双塔召回的点击 Recall@50 是 0.31，负样本只按随机抽取。", "fact_ids": ["e1"]},
             {"id": "change", "text": "把同会话未点击加入负样本，并保留随机负样本作对照。离线评测使用澄湾课程点击子集 8 万条，不是线上。Recall@50 从 0.31 到 0.36。", "fact_ids": ["e1"]},
             {"id": "parallel", "text": "并行用同一份点击日志单独训练排序模型，不使用这次新的负样本。离线 NDCG@10 从 0.42 到 0.45。这项不依赖召回改动。", "fact_ids": ["e1"]},
         ]},
        {"id": "skills", "title": "专业技能", "kind": "skills", "fact_ids": ["e1"], "items": [
            {"id": "stack", "text": "离线实验：Python 与 PyTorch，只用于上述召回对照。", "fact_ids": ["e1"]},
        ]},
        {"id": "honors", "title": "校园与荣誉", "kind": "campus", "fact_ids": ["e1"], "items": [
            {"id": "paper", "text": "第二作者，《澄湾课程点击子集上的负采样对照》，课程论文，未投稿期刊。", "fact_ids": ["e1"]},
            {"id": "contest", "text": "澄湾算法邀请赛，团队第 2 名，共 6 支队伍。本人负责离线评测脚本，不是个人排名。", "fact_ids": ["e1"]},
            {"id": "award", "text": "CET-6 548。澄湾大学硕士学业奖学金。", "fact_ids": ["e1"]},
        ]},
    ])


def test_substantive_internship_orders_work_before_projects_and_skills():
    from app.resume_layout import grouped_blocks, ordered_sections, work_is_substantive

    kept = _kept()
    assert work_is_substantive(kept.sections)
    labels = [label for label, _rows in grouped_blocks(kept.sections)]
    assert labels == ["工作 / 实习经历", "专业技能", "校园与荣誉"]
    assert [section.kind for section in ordered_sections(kept.sections)] == ["work", "skills", "campus"]
    stub = _draft([{"id": "thin", "title": "北屿智算", "kind": "work", "items": [{"id": "i", "text": "实习过", "fact_ids": ["e1"]}]},
                   {"id": "proj", "title": "课程实验", "kind": "project", "items": [{"id": "p", "text": "完成一次离线对照实验并保留评测脚本。", "fact_ids": ["e1"]}]}])
    assert [section.kind for section in ordered_sections(stub.sections)] == ["project", "work"]


def test_skipped_followups_do_not_excuse_dropping_strong_signals_or_filling_placeholders():
    from app.gates import gate_warnings
    from app.skill import build_evidence, validate_draft

    evidence = build_evidence(SOURCE)
    kept = _kept()
    kept.sections[0].items[0].fact_ids = [evidence[0].id]
    for section in kept.sections:
        section.fact_ids = [evidence[0].id]
        for item in section.items:
            item.fact_ids = [evidence[0].id]
    assert not validate_draft(kept, evidence)
    job = {"input": {"source_text": SOURCE, "education": [{"school": "澄湾大学", "degree": "硕士", "major": "计算机技术"}],
                      "career_stage": "entry"}, "answered": True, "answer_context": []}
    assert not any(issue.severity == "warning" and "第二作者" in issue.message for issue in gate_warnings(job, kept))
    thin = _draft([{"id": "intern", "title": "北屿智算", "kind": "work", "role": "算法工程师", "fact_ids": [evidence[0].id], "items": [
        {"id": "i", "text": "参与推荐相关实习，使用深度学习。", "fact_ids": [evidence[0].id]}]}])
    warnings = gate_warnings(job, thin)
    assert any("第二作者" in issue.message for issue in warnings)
    assert any("团队名次" in issue.message for issue in warnings)
    assert any("奖学金" in issue.message for issue in warnings)
    assert any("不要把岗位名称升级" in issue.message for issue in warnings)
    invented = _draft([{"id": "bad", "title": "项目", "kind": "project", "fact_ids": [evidence[0].id], "items": [
        {"id": "i", "text": "985 高校算法项目使用 xxxx 将全站点击率提升 20%。", "fact_ids": [evidence[0].id]}]}])
    blocking = gate_warnings(job, invented)
    assert any(issue.severity == "blocking" and "985" in issue.message for issue in blocking)
    assert any(issue.severity == "blocking" and "占位符" in issue.message for issue in blocking)
    body = "\n".join(item.text for section in kept.sections for item in section.items)
    assert "共青团员" not in body
    assert "他人" not in body and "不负责" not in body
    assert "Recall@50" in body and "NDCG@10" in body and "不依赖召回改动" in body
    guide = Path(__file__).resolve().parents[1].joinpath("skills/resume-writing/references/roles")
    improved = guide.joinpath("algorithm.md").read_text(encoding="utf-8").split("改进写法", 1)[1]
    assert "由他人维护" not in improved and "Recall@50" in improved and "NDCG@10" in improved
    product = guide.joinpath("product.md").read_text(encoding="utf-8").split("改进写法", 1)[1]
    assert "研发排期" not in product and "18 条" in product
    operations = guide.joinpath("operations.md").read_text(encoding="utf-8").split("改进写法", 1)[1]
    assert "3 场" in operations and "复购" in operations and "策略闭环" in operations
    editorial = Path(__file__).resolve().parents[1].joinpath("skills/resume-writing/references/editorial.md").read_text(encoding="utf-8")
    assert "不查学校" in editorial and "百分点差值" in editorial and "最多 2 个" in editorial
    assert "负责业务" in editorial and "不是必填标签" in editorial


def test_optional_header_fields_survive_only_when_the_user_fills_them(tmp_path):
    from io import BytesIO

    from docx import Document

    from app.models import Item, ResumeContent, Section
    from app.rendering import render_docx, render_html
    from app.store import ResumeStore

    content = ResumeContent(name="周衡", target_role="算法实习生", contact="zhouheng-demo@example.invalid",
                            location="澄湾", profile_note="共青团员",
                            sections=[Section(id="work", title="北屿智算", kind="work", items=[Item(id="a", text="完成离线召回对照。")])])
    html = render_html(content)
    document = "\n".join(paragraph.text for paragraph in Document(BytesIO(render_docx(content, False, False))).paragraphs)
    assert "澄湾" in html and "共青团员" in html
    assert "澄湾" in document and "共青团员" in document
    omitted = content.model_copy(update={"location": "", "profile_note": ""})
    quiet = render_html(omitted)
    assert "共青团员" not in quiet and "澄湾" not in quiet
    store = ResumeStore(tmp_path / "resume.sqlite")
    loaded = store.get(store.create(content, "manual").id)
    assert loaded.content.location == "澄湾" and loaded.content.profile_note == "共青团员"
    from app.generation_models import GenerationInput
    from app.intake import complete_intake

    kept_fields = complete_intake(GenerationInput(request_id="header001", source_text=SOURCE, location="澄湾", profile_note="共青团员", send_materials=True))
    assert kept_fields.location == "澄湾" and kept_fields.profile_note == "共青团员"
    blank_fields = complete_intake(GenerationInput(request_id="header002", source_text=SOURCE, send_materials=True))
    assert blank_fields.location == "" and blank_fields.profile_note == ""
    assert "共青团员" in SOURCE
