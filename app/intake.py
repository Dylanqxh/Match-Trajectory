"""Turn uploaded or pasted material into fields. Nothing is guessed beyond an explicit line."""

import re
from typing import Literal

from pydantic import Field

from app.generation_models import GenerationInput
from app.models import Education, StrictModel


class ParseRequest(StrictModel):
    text: str = Field(default="", max_length=20000)
    purpose: Literal["resume", "jd"] = "resume"

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
LABEL = re.compile(r"^(姓名|名字|联系方式|电话|邮箱|手机|目标岗位|求职意向|应聘岗位|意向岗位|学校|岗位|职位)[:：]\s*(.*)$")
SCHOOL = re.compile(r"[\u4e00-\u9fffA-Za-z0-9·]{2,30}?(?:大学|学院)")
DEGREE = re.compile(r"博士|硕士|本科|专科")
PERIOD = re.compile(
    r"((?:19|20|21)\d{2})(?:[.\-/年](\d{1,2})月?)?\s*[—–~到至\-]+\s*"
    r"((?:19|20|21)\d{2})(?:[.\-/年](\d{1,2})月?)?"
)
FALLBACK_ROLE = "未注明岗位"
RESUME_HEADINGS = {
    "个人简历", "简历", "教育背景", "教育经历", "专业技能", "技能特长", "项目经历", "项目经验",
    "工作经历", "实习经历", "工作/实习经历", "校园经历", "校园与荣誉", "科研成果", "自我评价",
}


def parse_material(text: str, *, purpose: str = "resume") -> dict:
    if purpose == "jd":
        return {"name": "", "contact": "", "target_role": _labeled_role(text), "education": [], "jd": (text or "").strip(), "source_text": ""}
    name = contact = role = ""
    education = []
    for raw in (text or "").splitlines():
        line = raw.strip()
        match = LABEL.match(line)
        if match:
            label, value = match.group(1), match.group(2).strip()
            if label in {"姓名", "名字"} and value and not name:
                name = value.split()[0][:80]
            elif label in {"联系方式", "电话", "邮箱", "手机"} and value and not contact:
                contact = value[:300]
            elif label in {"目标岗位", "求职意向", "应聘岗位", "意向岗位", "岗位", "职位"} and value and not role:
                role = value[:80]
            elif label == "学校" and value:
                row = _education_from_line(value) or {"school": value[:120], "degree": "", "major": ""}
                education.append(row)
            continue
        row = _education_from_line(line)
        if row and len(education) < 3:
            education.append(row)
    if not contact:
        found = EMAIL.findall(text or "") + PHONE.findall(text or "")
        contact = " ".join(dict.fromkeys(found))[:300]
    if not name:
        name = _standalone_name(text)
    rows = []
    for index, row in enumerate(education, start=1):
        if not (row.get("school") or row.get("degree") or row.get("major")):
            continue
        rows.append({"id": f"edu-file-{index}", "school": row.get("school") or "", "degree": row.get("degree") or "", "major": row.get("major") or "",
                     "start_date": row.get("start_date") or "", "end_date": row.get("end_date") or ""})
    return {"name": name, "contact": contact, "target_role": role, "education": rows, "jd": "", "source_text": (text or "").strip()}


def complete_intake(inputs: GenerationInput) -> GenerationInput:
    """Fill only fields the user left blank. A typed value always wins."""
    parsed = parse_material(inputs.source_text)
    from_jd = parse_material(inputs.jd, purpose="jd") if inputs.jd else {}
    education = inputs.education if _has_education(inputs.education) else [Education.model_validate(row) for row in parsed["education"]]
    role = inputs.target_role.strip() or parsed["target_role"] or from_jd.get("target_role") or FALLBACK_ROLE
    return inputs.model_copy(update={
        "name": inputs.name.strip() or parsed["name"],
        "contact": inputs.contact.strip() or parsed["contact"],
        "target_role": role[:80],
        "education": education,
        "source_text": inputs.source_text,
        "jd": inputs.jd,
    })


def _labeled_role(text: str) -> str:
    for raw in (text or "").splitlines():
        match = re.match(r"^(?:岗位|职位|招聘职位|目标岗位)[:：]\s*(.+)$", raw.strip())
        if match:
            return match.group(1).strip()[:80]
    return ""


def _standalone_name(text: str) -> str:
    """Read a plausible name near the top only when the surrounding text is resume-like."""
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    context = "\n".join(lines[:10])
    if not (EMAIL.search(context) or PHONE.search(context) or SCHOOL.search(context)
            or re.search(r"(?:求职意向|目标岗位|应聘岗位)[:：]", context)):
        return ""
    for line in lines[:5]:
        compact = re.sub(r"\s+", " ", line).strip()
        if compact in RESUME_HEADINGS or any(word in compact for word in ("求职", "教育", "技能", "项目", "经历", "荣誉", "实习", "工作", "联系方式")):
            continue
        if re.fullmatch(r"[\u4e00-\u9fff·]{2,8}", compact) or re.fullmatch(r"[A-Za-z][A-Za-z .'-]{1,39}", compact):
            return compact[:80]
    return ""


def _education_from_line(line: str) -> dict | None:
    school = SCHOOL.search(line or "")
    degree = DEGREE.search(line or "")
    if not school or not degree:
        return None
    period = PERIOD.search(line or "")
    rest = line.replace(school.group(0), " ", 1).replace(degree.group(0), " ", 1)
    rest = re.sub(r"(?:19|20|21)\d{2}(?:[.\-/年]\d{1,2}月?)?", " ", rest)
    tokens = [token for token in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", rest) if token not in {"教育", "背景", "经历", "学历", "专业", "在读"}]
    major = next((token for token in tokens if token not in school.group(0)), "")
    def normalized(year: str, month: str | None) -> str:
        return f"{year}-{int(month):02d}" if month else year

    return {"school": school.group(0)[:120], "degree": degree.group(0)[:40], "major": major[:80],
            "start_date": normalized(period.group(1), period.group(2)) if period else "",
            "end_date": normalized(period.group(3), period.group(4)) if period else ""}


def _has_education(rows: list[Education]) -> bool:
    return any(row.school.strip() or row.degree.strip() or row.major.strip() for row in rows)
