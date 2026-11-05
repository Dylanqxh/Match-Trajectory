import hashlib
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

from app.generation_models import Draft, Evidence, Issue

STORED_ROLES = ("product", "backend", "algorithm", "data-analysis", "operations", "general")
TECHNOLOGIES = ("Java", "Python", "Redis", "MySQL", "PostgreSQL", "Kafka", "Spring", "PyTorch", "TensorFlow",
                "Kubernetes", "Docker", "SQL", "Spark", "Hadoop", "Excel", "Tableau", "Figma", "Axure", "C++", "C#")
PROJECT_LABEL = re.compile(r"项目(?:[0-9A-Za-z]+|[\u4e00-\u9fff]{1,8}(?=[：:，,。；;\s]|$))")
NUMERIC = re.compile(r"\d+(?:[.,]\d+)*(?:\s*(?:%|％|万|亿|年|个月|月|天|小时|人|次|条|倍|ms|秒|个|GB|MB|QPS))?", re.IGNORECASE)
ATTRIBUTION = ("主导", "精通", "负责人", "独立负责", "从零搭建", "牵头")


@dataclass(frozen=True)
class SkillBundle:
    role: str
    instructions: str
    version: str
    resources: list[str] = field(default_factory=list)
    stage_resources: dict[str, list[str]] = field(default_factory=dict)
    stage_instructions: dict[str, str] = field(default_factory=dict)


def load_skill(target_role: str, career_stage="unspecified", has_career_gap=False, role_direction=None, *, pinned_role=None) -> SkillBundle:
    """Load rules for an explicit direction. Job-title text is not classified.

    ``pinned_role`` keeps the snapshot already stored on an older task, including
    directions that new tasks can no longer select.
    """
    del target_role
    if pinned_role in STORED_ROLES:
        role = pinned_role
    elif role_direction == "product":
        role = "product"
    elif role_direction == "backend":
        role = "backend"
    else:
        role = "general"
    root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent)) / "skills" / "resume-writing"
    base = ["SKILL.md", "references/contract.md", "references/evidence/common.md", f"references/roles/{role}.md", "references/candidates/common.md"]
    candidate = {"entry": "entry", "experienced": "experienced", "transition": "transition"}.get(career_stage)
    if candidate:
        base.append(f"references/candidates/{candidate}.md")
    if has_career_gap:
        base.append("references/candidates/returning.md")
    extras = {"plan": ["references/questions.md"], "draft": ["references/editorial.md"],
              "review": ["references/quality-rubric.md", "references/review-boundaries.md"],
              "revise": ["references/editorial.md", "references/quality-rubric.md"]}
    example_path = "examples/writing-boundaries.json"
    examples = json.loads((root / example_path).read_text(encoding="utf-8"))
    selected = [row for row in examples if row["role"] == role]
    example_text = "合成写法演示（平庸／改进／越界）：只学习方法，所有案例事实均不属于用户，不可引用或复制。\n" + json.dumps(selected, ensure_ascii=False)
    stage_resources = {stage: [*base, *paths, example_path] for stage, paths in extras.items()}
    stage_instructions = {stage: "\n\n".join([*[(root / path).read_text(encoding="utf-8") for path in paths if path != example_path], example_text])
                          for stage, paths in stage_resources.items()}
    resources = list(dict.fromkeys(path for paths in stage_resources.values() for path in paths))
    version = hashlib.sha256(json.dumps(stage_instructions, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:16]
    return SkillBundle(role, stage_instructions["draft"], version, resources, stage_resources, stage_instructions)


def _project_boundary(window: str) -> int | None:
    labels = list(PROJECT_LABEL.finditer(window))
    if len(labels) < 2 or labels[1].start() <= 0:
        return None
    second = labels[1].start()
    separator = max(window.rfind("\n", 0, second), window.rfind("；", 0, second), window.rfind(";", 0, second), window.rfind("。", 0, second))
    return separator + 1 if separator > 0 else second


def build_evidence(text: str, prefix: str = "e") -> list[Evidence]:
    result = []
    cursor = 0
    while cursor < len(text):
        end = min(cursor + 1600, len(text))
        boundary = _project_boundary(text[cursor:end])
        if boundary and cursor + boundary < len(text):
            end = cursor + boundary
        elif end < len(text):
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
    def two_digit_year(match):
        year, month = int(match.group(1)), int(match.group(2))
        if not 1 <= month <= 12:
            return match.group(0)
        full = 2000 + year if year <= 39 else 1900 + year
        return f"{full}-{month:02d}"

    text = re.sub(r"(?<!\d)(\d{2})\s*年\s*(\d{1,2})\s*月", two_digit_year, text)
    text = re.sub(r"(?<!\d)((?:19|20|21)\d{2})\s*[./年-]\s*(\d{1,2})\s*月?", lambda m: f"{m[1]}-{int(m[2]):02d}", text)
    return re.sub(r"(?<!\d)((?:19|20|21)\d{2})\s*年", r"\1", text)


def canonical_quantity(text):
    """Normalize spelling, preserving exact digits, magnitude and units."""
    value = re.sub(r"\s", "", text).replace("％", "%")
    match = re.fullmatch(r"([\d.,]+)(.*)", value)
    number, unit = match.groups()
    if ',' in number:
        if not re.fullmatch(r"\d{1,3}(?:,\d{3})+(?:\.\d+)?", number):
            return value
        number = number.replace(',', '')
    if not re.fullmatch(r"\d+(?:\.\d+)?", number):
        return value
    whole, dot, fraction = number.partition('.')
    number = whole.lstrip('0') or '0'
    fraction = fraction.rstrip('0')
    return number + ('.' + fraction if dot and fraction else '') + unit


def _clauses(text):
    pieces = re.split(r"[。；;\n]+", text)
    result = []
    for piece in pieces:
        if len(set(PROJECT_LABEL.findall(piece))) >= 2:
            result.extend(re.split(r"(?<!\d),(?!\d)|，", piece))
        else:
            result.append(piece)
    return [piece.strip() for piece in result if piece.strip()]


def _quantities(text):
    return {canonical_quantity(token) for token in NUMERIC.findall(normalize_source_dates(text))}


def _moved_across_projects(claim, source):
    """A number that exists only beside a different named project is unsupported."""
    source_clauses = _clauses(source)
    for clause in _clauses(claim):
        labels = set(PROJECT_LABEL.findall(clause))
        if not labels:
            continue
        for number in _quantities(clause):
            owners = [set(PROJECT_LABEL.findall(row)) for row in source_clauses if number in _quantities(row)]
            if not owners or any(labels & owner for owner in owners):
                continue
            if set().union(*owners).isdisjoint(labels):
                return True
    return False


def validate_draft(draft: Draft, evidence: list[Evidence]) -> list[Issue]:
    from app.gates import proficiency_violations, ungrounded_familiarity

    sources = {e.id: e.text for e in evidence}
    issues = []
    claims = draft.claims() + draft.metadata_claims(list(sources)) if sources else draft.claims()
    for claim in claims:
        def add(code, message, item_id=claim.id):
            issues.append(Issue(item_id=item_id, severity="blocking", code=code, message=message))

        if any(ref not in sources for ref in claim.fact_ids):
            add("reference", "段落引用了不存在的材料，不能视为有事实依据。")
            continue
        source = "\n".join(sources[ref] for ref in claim.fact_ids)
        source_numbers = _quantities(source)
        if any(canonical_quantity(n) not in source_numbers for n in NUMERIC.findall(normalize_source_dates(claim.text))):
            add("unsupported", "段落出现了引用原文中没有的数字或数量口径，请删除或补充依据。")
        elif _moved_across_projects(claim.text, source):
            add("unsupported", "数字被挪到了另一个项目上，请改回原文所属项目或删除。")
        for technology in TECHNOLOGIES:
            pattern = r"(?<![A-Za-z])" + re.escape(technology) + r"(?![A-Za-z])"
            if re.search(pattern, claim.text, re.IGNORECASE) and not re.search(pattern, source, re.IGNORECASE):
                add("unsupported", f"{technology} 未在引用材料中出现，不能从岗位要求推断为个人技能。")
        if re.search(r"(?<![A-Za-z])Spring Boot(?![A-Za-z])", claim.text, re.IGNORECASE) and not re.search(
                r"(?<![A-Za-z])Spring Boot(?![A-Za-z])", source, re.IGNORECASE):
            add("unsupported", "不能把 Spring 写成 Spring Boot。引用材料没有出现 Spring Boot。")
        for phrase in ("两个项目", "全部项目", "所有项目"):
            if phrase in claim.text and phrase not in source:
                add("unsupported", f"「{phrase}」扩大了原文范围。材料没这样写，就不能把一项实践说成多项。")
                break
        if any(word in claim.text and word not in source for word in ATTRIBUTION):
            add("attribution", "责任或熟练程度比引用材料更强，需要核对个人范围。")
        missing_skill = ungrounded_familiarity(claim.text, source)
        if missing_skill:
            add("unsupported", f"「{missing_skill}」没有出现在引用材料里，不能写成已熟悉或已掌握的技能。")
        overstated = proficiency_violations(claim.text, source)
        if overstated:
            add("attribution", f"熟练度超过原文（{'、'.join(overstated[:4])}）。原文没有写这个程度时，只保留技能名称或原文里的说法。")
        if "数倍" in claim.text and "数倍" not in source and not re.search(r"\d+(?:\.\d+)?\s*倍", source):
            issues.append(Issue(item_id=claim.id, severity="warning", code="attribution", message="“数倍”这类定性夸大未在引用材料中出现，请改回原文口径。"))
        if "显著提升" in claim.text and "显著提升" not in source:
            issues.append(Issue(item_id=claim.id, severity="warning", code="attribution", message="“显著提升”未在引用材料中出现，请改回原文口径。"))
        boundaries = [(r"未上线|没有上线|仅离线|未部署", r"已上线|上线运行|生产部署|正式上线"),
                      (r"试运行|未正式推广|未推广|试运行结束后", r"已上线|正式上线|正式推广|服务全校|全校学生|生产环境"),
                      (r"已下线|课程结束后已下线", r"在线运行|持续服务|仍在运行"),
                      (r"本机", r"线上性能|生产环境"),
                      (r"未获奖|没有获奖|只进初赛", r"(?<!未)(?<!没有)获奖|一等奖|晋级决赛"),
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

    def warn(item_id, message, action="revise"):
        issues.append(Issue(item_id=item_id, severity="warning", code="quality", message=message, repair_action=action))

    if draft.summary and len(draft.summary.text) > 100:
        warn("__summary", "简介偏长，请压缩为1—2句，仅保留目标相关的背景与证据，删除求职意愿和自我评价。")
    block_titles = {"项目", "项目经历", "专业技能", "技能", "技能与实践", "工作 / 实习经历", "工作／实习经历", "工作／实习", "实习", "校园与荣誉"}
    for section in draft.sections:
        if section.kind in ("project", "work", "research") and section.title not in block_titles:
            if not section.start_date and not section.end_date:
                warn(section.id, "这段经历缺少时间；请在编辑器补充已知日期，未知时留空，不得推测。", "need_input")
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
