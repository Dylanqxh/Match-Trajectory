"""Shared, deterministic presentation; missing dates remain missing."""
import re

CANONICAL_KINDS = ("skills", "project", "work", "campus")
BLOCK_LABELS = {
    "education": "教育经历",
    "skills": "专业技能",
    "project": "项目",
    "work": "工作 / 实习经历",
    "campus": "校园与荣誉",
}
# Legacy resumes still name these kinds. New drafts are normalized before review.
KIND_LABELS = {
    "project": BLOCK_LABELS["project"],
    "work": BLOCK_LABELS["work"],
    "research": BLOCK_LABELS["project"],
    "skills": BLOCK_LABELS["skills"],
    "campus": BLOCK_LABELS["campus"],
    "other": "",
}
_AWARD = re.compile(r"优秀|铜奖|银奖|金奖|一等奖|二等奖|三等奖|奖学金|获评")
_NUMERIC = re.compile(r"\d+(?:[.,]\d+)?")


def _field(row, name):
    return row.get(name) if isinstance(row, dict) else getattr(row, name, "")


def display_date(value: str) -> str:
    """Stored dates stay YYYY-MM. Resumes show YYYY.MM."""
    if not value or value == "至今":
        return value or ""
    return re.sub(r"^((?:19|20|21)\d{2})-(0[1-9]|1[0-2])$", r"\1.\2", value)


def display_text(text: str) -> str:
    return re.sub(r"(?<!\d)((?:19|20|21)\d{2})-(0[1-9]|1[0-2])(?!\d)", r"\1.\2", text or "")


def period_text(row):
    """Canonical stored period, used when the date itself is evidence."""
    return " — ".join(filter(None, (_field(row, "start_date"), _field(row, "end_date"))))


def display_period(row):
    return " — ".join(filter(None, (display_date(_field(row, "start_date")), display_date(_field(row, "end_date")))))


def education_text(row):
    return " · ".join(filter(None, (row.school, row.degree, row.major)))


def section_text(row):
    return " · ".join(filter(None, (row.title, row.organization, row.role)))


def date_key(row):
    end = row.end_date if not isinstance(row, dict) else row.get("end_date")
    start = row.start_date if not isinstance(row, dict) else row.get("start_date")
    if end == "至今":
        return "9999-99"
    return end or start or ""


def presentation_kind(section) -> str:
    """Map a stored section onto a skeleton block. Unknown titles stay readable."""
    kind = section.get("kind") if isinstance(section, dict) else section.kind
    title = (section.get("title") if isinstance(section, dict) else section.title) or ""
    if kind in CANONICAL_KINDS:
        return kind
    if "技能" in title:
        return "skills"
    if "实习" in title or "工作" in title:
        return "work"
    if any(token in title for token in ("荣誉", "竞赛", "奖学金", "集训")) or "ACM" in title.upper():
        return "campus"
    if "教育" in title:
        return "education"
    if kind == "research" or any(token in title for token in ("项目", "课题", "课程")):
        return "project"
    return "legacy"


def normalize_kind(kind: str, title: str) -> str:
    """Fold obvious headings into the skeleton. Leave genuine ad-hoc titles alone."""
    if kind in CANONICAL_KINDS:
        return kind
    folded = presentation_kind({"kind": kind or "other", "title": title or ""})
    return folded if folded in CANONICAL_KINDS else (kind or "other")


def section_blob(section) -> str:
    if isinstance(section, dict):
        parts = [section.get("title"), section.get("organization"), section.get("role")]
        parts.extend(item.get("text") if isinstance(item, dict) else item.text for item in section.get("items") or [])
    else:
        parts = [section.title, section.organization, section.role]
        parts.extend(item.text for item in section.items)
    return "\n".join(part for part in parts if part)


def evidence_strength(section, jd: str = "") -> int:
    """JD overlap and concrete results outrank a later end date."""
    blob = section_blob(section)
    score = 0
    if _AWARD.search(blob):
        score += 10
    score += min(len(_NUMERIC.findall(blob)), 6)
    for word in ("测试", "校验", "实现", "接口", "行锁"):
        if word in blob:
            score += 1
    if not jd:
        return score
    for word in ("MySQL", "SQL", "Java", "Python", "Redis", "Spring", "稳定", "竞赛", "获奖"):
        if word.lower() in jd.lower() and word.lower() in blob.lower():
            score += 3
    return score


def _strength_sort(rows, jd: str):
    indexed = list(enumerate(rows))
    indexed.sort(key=lambda pair: (date_key(pair[1]), -pair[0]), reverse=True)
    indexed.sort(key=lambda pair: evidence_strength(pair[1], jd), reverse=True)
    return [row for _, row in indexed]


def arrange_draft_sections(sections: list[dict], jd: str = "") -> list[dict]:
    """Normalize kinds and put stronger projects and jobs ahead of a later weak one."""
    normalized = []
    for row in sections:
        item = dict(row)
        item["kind"] = normalize_kind(item.get("kind") or "other", item.get("title") or "")
        normalized.append(item)
    grouped = {kind: [] for kind in (*CANONICAL_KINDS, "rest")}
    for row in normalized:
        grouped[row["kind"] if row["kind"] in CANONICAL_KINDS else "rest"].append(row)
    ordered = []
    for kind in CANONICAL_KINDS:
        rows = grouped[kind]
        if kind in ("project", "work"):
            rows = _strength_sort(rows, jd)
        ordered.extend(rows)
    ordered.extend(grouped["rest"])
    return ordered


def ordered_sections(sections):
    """Group into the skeleton, preserving the order already chosen within a block."""
    buckets = {kind: [] for kind in CANONICAL_KINDS}
    rest = []
    for section in sections:
        kind = presentation_kind(section)
        if kind in buckets:
            buckets[kind].append(section)
        else:
            rest.append(section)
    return [*buckets["skills"], *buckets["project"], *buckets["work"], *buckets["campus"], *rest]


def grouped_blocks(sections):
    """Visible blocks only. An empty block is omitted for every reader."""
    buckets = {kind: [] for kind in ("education", *CANONICAL_KINDS)}
    legacy = []
    for section in sections:
        if not section.items:
            continue
        kind = presentation_kind(section)
        if kind in buckets:
            buckets[kind].append(section)
        else:
            legacy.append(section)
    blocks = [(BLOCK_LABELS[kind], buckets[kind]) for kind in ("education", *CANONICAL_KINDS) if buckets[kind]]
    blocks.extend((section.title, [section]) for section in legacy)
    return blocks


def arrange_sections(sections, jd: str = ""):
    """Same order as generated drafts, for callers that still hold Section objects."""
    payloads = []
    by_id = {}
    for section in sections:
        payloads.append({"id": section.id, "kind": section.kind, "title": section.title,
                         "organization": section.organization, "role": section.role,
                         "start_date": section.start_date, "end_date": section.end_date,
                         "items": [{"text": item.text} for item in section.items]})
        by_id[section.id] = section
    return [by_id[row["id"]] for row in arrange_draft_sections(payloads, jd)]


def text_runs(text, highlights):
    if not highlights:
        return [(text, False)]
    pattern = re.compile("|".join(re.escape(h) for h in sorted(set(highlights), key=len, reverse=True) if h and h in text))
    if not pattern.pattern:
        return [(text, False)]
    result, cursor = [], 0
    for match in pattern.finditer(text):
        result.extend(((text[cursor:match.start()], False), (match.group(), True)))
        cursor = match.end()
    result.append((text[cursor:], False))
    return [(value, bold) for value, bold in result if value]
