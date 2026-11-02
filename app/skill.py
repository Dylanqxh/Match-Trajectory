import hashlib
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from app.generation_models import Draft, Evidence, Issue

ROLE_WORDS = {
    "algorithm": ("算法", "nlp", "机器学习", "深度学习", "计算机视觉", "推荐", "大模型", "agent", "rag", "智能体", "llm"),
    "data-analysis": ("数据分析", "商业分析", "bi分析", "数分"),
    "product": ("产品", "product manager"),
    "operations": ("运营", "增长", "社区", "内容"),
    "backend": ("后端", "后台", "java", "golang", "服务端", "研发", "开发"),
}
TECHNOLOGIES = ("Java", "Python", "Redis", "MySQL", "PostgreSQL", "Kafka", "Spring", "PyTorch", "TensorFlow",
                "Kubernetes", "Docker", "SQL", "Spark", "Hadoop", "Excel", "Tableau", "Figma", "Axure", "C++", "C#")


@dataclass(frozen=True)
class SkillBundle:
    role: str
    instructions: str
    version: str


def load_skill(target_role: str) -> SkillBundle:
    order = ("product", "operations", "data-analysis", "algorithm", "backend")
    role = next((key for key in order if any(word in target_role.lower() for word in ROLE_WORDS[key])), "general")
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "skills" / "resume-writing"
    texts = [(root / "SKILL.md").read_text(encoding="utf-8"),
             (root / "references" / "quality-rubric.md").read_text(encoding="utf-8"),
             (root / "references" / "editorial.md").read_text(encoding="utf-8"),
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


def normalize_source_dates(text):
    text = re.sub(r"(?<!\d)((?:19|20|21)\d{2})[./年-](\d{1,2})月?", lambda m: f"{m[1]}-{int(m[2]):02d}", text)
    return re.sub(r"(?<!\d)((?:19|20|21)\d{2})年", r"\1", text)


def validate_draft(draft: Draft, evidence: list[Evidence]) -> list[Issue]:
    sources = {e.id: e.text for e in evidence}
    issues = []
    numeric = re.compile(r"\d+(?:[.,]\d+)*(?:\s*(?:%|％|万|亿|年|个月|月|天|小时|人|次|条|倍|ms|秒|个|GB|MB|QPS))?", re.IGNORECASE)
    claims = draft.claims() + draft.metadata_claims(list(sources)) if sources else draft.claims()
    for claim in claims:
        def add(code, message, item_id=claim.id):
            issues.append(Issue(item_id=item_id, severity="blocking", code=code, message=message))

        if any(ref not in sources for ref in claim.fact_ids):
            add("reference", "段落引用了不存在的材料，不能视为有事实依据。")
            continue
        source = "\n".join(sources[ref] for ref in claim.fact_ids)
        source_numbers = {re.sub(r"\s", "", n) for n in numeric.findall(normalize_source_dates(source))}
        if any(re.sub(r"\s", "", n) not in source_numbers for n in numeric.findall(normalize_source_dates(claim.text))):
            add("unsupported", "段落出现了引用原文中没有的数字或数量口径，请删除或补充依据。")
        for technology in TECHNOLOGIES:
            pattern = r"(?<![A-Za-z])" + re.escape(technology) + r"(?![A-Za-z])"
            if re.search(pattern, claim.text, re.IGNORECASE) and not re.search(pattern, source, re.IGNORECASE):
                add("unsupported", f"{technology} 未在引用材料中出现，不能从岗位要求推断为个人技能。")
        if any(word in claim.text and word not in source for word in ("主导", "精通", "负责人", "独立负责", "从零搭建")):
            add("attribution", "责任或熟练程度比引用材料更强，需要核对个人范围。")
        boundaries = [(r"未上线|没有上线|仅离线", r"已上线|上线运行|生产部署"),
                      (r"在投|未发表|尚未发表", r"已发表|正式发表")]
        if any(re.search(negative, source) and re.search(positive, claim.text) for negative, positive in boundaries):
            add("conflict", "表达与原文的上线或发表状态限制冲突。")
    for row in draft.education:
        source = "\n".join(sources.get(ref, "") for ref in row.fact_ids)
        if row.school and row.school not in source:
            issues.append(Issue(item_id=row.id, severity="blocking", code="unsupported", message="学校名称未在引用原文中出现，请核对，不得推断学校。"))
    for row in [*draft.education, *draft.sections]:
        refs = row.fact_ids or list(dict.fromkeys(ref for item in row.items for ref in item.fact_ids)) or list(sources)
        source = "\n".join(sources.get(ref, "") for ref in refs)
        source = normalize_source_dates(source)
        if any(value and value != "至今" and not re.search(r"(?<!\d)" + re.escape(value) + r"(?!\d)", source)
               for value in (row.start_date, row.end_date)):
            issues.append(Issue(item_id=row.id, severity="blocking", code="unsupported", message="经历时间未在引用原文中出现，请删除推测日期或补充依据。"))
    return issues


def validate_quality(draft: Draft) -> list[Issue]:
    """Editorial warnings; never use length alone as evidence of false facts."""
    issues = []

    def warn(item_id, message):
        issues.append(Issue(item_id=item_id, severity="warning", code="quality", message=message))

    if draft.summary and len(draft.summary.text) > 100:
        warn("__summary", "简介偏长，请压缩为1—2句，仅保留目标相关的背景与证据，删除求职意愿和自我评价。")
    for section in draft.sections:
        if section.kind in ("project", "work", "research"):
            if not section.start_date and not section.end_date:
                warn(section.id, "这段经历缺少时间；请在编辑器补充已知日期，未知时留空，不得推测。")
            if len(section.items) > 4:
                warn(section.id, "单段经历条目偏多，请合并重复内容，优先保留2—4项核心贡献。")
        seen = set()
        for item in section.items:
            if len(item.text) > 110:
                warn(item.id, "单条信息偏长，请压缩为一个主要贡献；保留动作、方法与交付，删除背景复述。")
            normalized = re.sub(r"\s|[，。；、]", "", item.text)
            if normalized in seen:
                warn(item.id, "内容重复，请删除重复条目或改为另一项有依据的贡献。")
            seen.add(normalized)
    return issues
