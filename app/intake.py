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
FALLBACK_ROLE = "未注明岗位"


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
    rows = []
    for index, row in enumerate(education, start=1):
        if not (row.get("school") or row.get("degree") or row.get("major")):
            continue
        rows.append({"id": f"edu-file-{index}", "school": row.get("school") or "", "degree": row.get("degree") or "", "major": row.get("major") or ""})
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


def _education_from_line(line: str) -> dict | None:
    school = SCHOOL.search(line or "")
    degree = DEGREE.search(line or "")
    if not school or not degree:
        return None
    rest = line.replace(school.group(0), " ", 1).replace(degree.group(0), " ", 1)
    rest = re.sub(r"(?:19|20|21)\d{2}(?:[.\-/年]\d{1,2}月?)?", " ", rest)
    tokens = [token for token in re.findall(r"[\u4e00-\u9fffA-Za-z]{2,}", rest) if token not in {"教育", "背景", "经历", "学历", "专业", "在读"}]
    major = next((token for token in tokens if token not in school.group(0)), "")
    return {"school": school.group(0)[:120], "degree": degree.group(0)[:40], "major": major[:80]}


def _has_education(rows: list[Education]) -> bool:
    return any(row.school.strip() or row.degree.strip() or row.major.strip() for row in rows)
