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
             {"id": "change", "text": "把同会话未点击加入负样本，并保留随机负样本作对照。特征流水线由同组同学维护，本人不负责特征平台。", "fact_ids": ["e1"]},
             {"id": "result", "text": "离线评测使用澄湾课程点击子集 8 万条，不是线上。Recall@50 从 0.31 到 0.36。没有全站收益。", "fact_ids": ["e1"]},
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
    assert "共青团员" not in "\n".join(item.text for section in kept.sections for item in section.items)
