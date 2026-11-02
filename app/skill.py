import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from app.generation_models import Draft, Evidence, Issue

ROLE_WORDS = {
    "algorithm": ("算法", "nlp", "机器学习", "深度学习", "计算机视觉", "推荐", "大模型"),
    "data-analysis": ("数据分析", "商业分析", "bi分析", "数分"),
    "product": ("产品", "product manager"),
    "operations": ("运营", "增长", "社区", "内容"),
    "backend": ("后端", "后台", "java", "golang", "服务端", "研发", "开发"),
}


@dataclass(frozen=True)
class SkillBundle:
    role: str
    instructions: str
    version: str


def load_skill(target_role: str) -> SkillBundle:
    role = next((key for key, words in ROLE_WORDS.items() if any(word in target_role.lower() for word in words)), "general")
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "skills" / "resume-writing"
    texts = [(root / "SKILL.md").read_text(encoding="utf-8"),
             (root / "references" / "quality-rubric.md").read_text(encoding="utf-8"),
             (root / "references" / "roles" / (role + ".md")).read_text(encoding="utf-8")]
    instructions = "\n\n".join(texts)
    return SkillBundle(role, instructions, hashlib.sha256(instructions.encode()).hexdigest()[:16])


def build_evidence(text: str, prefix: str = "e") -> list[Evidence]:
    result = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + 1600, len(text))
        if end < len(text):
            newline = text.rfind("\n", cursor + 800, end)
            if newline >= 0:
                end = newline + 1
        raw = text[cursor:end]
        value = raw.strip()
        if value:
            start = cursor + len(raw) - len(raw.lstrip())
            result.append(Evidence(id=f"{prefix}{len(result) + 1}", text=value, start=start, end=start + len(value)))
        cursor = end
    return result


def validate_draft(draft: Draft, evidence: list[Evidence]) -> list[Issue]:
    sources = {e.id: e.text for e in evidence}
    issues = []
    numeric = re.compile(r"\d+(?:[.,]\d+)*(?:\s*(?:%|％|万|亿|年|个月|月|天|小时|人|次|条|倍|ms|秒|个|GB|MB|QPS))?", re.IGNORECASE)
    for claim in draft.claims():
        def add(code, message):
            issues.append(Issue(item_id=claim.id, severity="blocking", code=code, message=message))

        if any(ref not in sources for ref in claim.fact_ids):
            add("reference", "段落引用了不存在的材料，不能视为有事实依据。")
            continue
        source = "\n".join(sources[ref] for ref in claim.fact_ids)
        source_numbers = {re.sub(r"\s", "", n) for n in numeric.findall(source)}
        if any(re.sub(r"\s", "", n) not in source_numbers for n in numeric.findall(claim.text)):
            add("unsupported", "段落出现了引用原文中没有的数字或数量口径，请删除或补充依据。")
        if any(word in claim.text and word not in source for word in ("主导", "精通", "负责人", "独立负责", "从零搭建")):
            add("attribution", "责任或熟练程度比引用材料更强，需要核对个人范围。")
        boundaries = [(r"未上线|没有上线|仅离线", r"已上线|上线运行|生产部署"),
                      (r"在投|未发表|尚未发表", r"已发表|正式发表")]
        if any(re.search(negative, source) and re.search(positive, claim.text) for negative, positive in boundaries):
            add("conflict", "表达与原文的上线或发表状态限制冲突。")
    return issues
