from app.generation_models import Issue, QualityReview

LABELS = {"fit": "岗位适配", "contribution": "个人贡献", "evidence": "亮点证据", "readability": "易读性"}


def editorial_quality(report, warnings, evidence):
    """Mechanical readability findings must not be hidden behind a model's ready."""
    actionable = [i for i in warnings if any(word in i.message for word in ("压缩", "合并", "重复"))]
    if not report or not actionable:
        return report
    dimensions = [row.model_dump() for row in report.dimensions]
    for row in dimensions:
        if row["dimension"] == "readability" and row["action"] != "revise":
            row.update(score=1, reason=actionable[0].message, action="revise",
                       item_ids=list(dict.fromkeys(i.item_id for i in actionable))[:8],
                       evidence_ids=[e["id"] for e in evidence][:12])
    return QualityReview.model_validate({**report.model_dump(), "dimensions": dimensions, "status": "revise"})


def quality_issues(report):
    if not report:
        return []
    return [Issue(item_id=row.item_ids[0] if row.item_ids else "document", severity="warning",
                  code="fit" if row.dimension == "fit" else "quality",
                  message=f"{LABELS[row.dimension]}：{row.reason}",
                  suggestion="依据已有原文修正表达" if row.action == "revise" else "材料缺口可后续补充，不能补造个人事实")
            for row in report.dimensions if row.action in ("revise", "need_input")]
