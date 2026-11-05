"""Program gates for the writing checklist. Filtering may drop a fact, never strengthen it."""
import re

from app.generation_models import Issue
from app.resume_layout import CANONICAL_KINDS, section_blob

# Older tasks and hand-edited drafts used these labels with kind "other".
GENERIC_BLOCK_TITLES = {
    "项目", "项目经历", "专业技能", "技能", "技能与实践",
    "工作 / 实习经历", "工作／实习经历", "工作／实习", "实习",
    "校园与荣誉", "教育经历", "教育背景",
}
from app.skill import TECHNOLOGIES

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
PHONE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_SCHOOL_SUFFIX = re.compile(r"大学|学院|学校")
EXPLICIT_MONTHS = re.compile(r"([一二两三四五六七八九十]|\d+)\s*个月")
MONTH_RANGE = re.compile(
    r"((?:19|20|21)\d{2})[.\-/年](\d{1,2})\s*[—\-~到至]+\s*((?:19|20|21)\d{2})[.\-/年](\d{1,2})")
ITEM_PERIOD = re.compile(
    r"((?:19|20|21)\d{2})[.\-/](\d{1,2})\s*[—\-~到至]+\s*((?:19|20|21)\d{2})[.\-/](\d{1,2})")
AWARD_WORD = re.compile(r"铜奖|银奖|金奖|一等奖|二等奖|三等奖|奖学金|ACM")
STRONG_MARKERS = ("优秀", "铜奖", "银奖", "金奖", "一等奖", "二等奖", "三等奖", "奖学金")
NEGATIVE_PHRASES = ("已下线", "未正式推广", "未推广", "其他组员", "试运行结束后", "没有上线", "未上线", "而停止")
PROJECT_HEADING = re.compile(r"项目[^\n：:]{0,8}[：:]\s*([^\n（(，,]{2,30})")
FICTIONAL_ORG = re.compile(r"（虚构：([^）]{2,20})）")
MONTH_VALUES = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}
GAP_MARKERS = ("【待补充", "【待确认")
_PAGE_CHARS = 1800


def header_contact(user_contact: str, source: str = "") -> str:
    """Return the contact line exactly as the user submitted it.

    A verbatim email in the source may be quoted inside experience text, but it
    does not fill an empty header. The header is an explicit field: inventing a
    phone or promoting an address the user left blank would look like a fact.
    """
    del source
    return user_contact or ""


def draft_text(draft) -> str:
    parts = []
    if draft.summary:
        parts.append(draft.summary.text)
    for row in draft.education:
        parts.extend((row.school, row.degree, row.major))
    for section in draft.sections:
        parts.append(section_blob(section))
    return "\n".join(part for part in parts if part)


def has_gap_marker(content) -> bool:
    blob = content if isinstance(content, str) else "\n".join(filter(None, (
        content.summary,
        *(item.text for section in content.sections for item in section.items),
        *(section.title for section in content.sections),
    )))
    return any(marker in blob for marker in GAP_MARKERS)


def gaps_need_resolution(content, manual_takeover: bool = False) -> bool:
    return has_gap_marker(content) and not manual_takeover


def _explicit_months(text: str) -> set[int]:
    found = set()
    for match in EXPLICIT_MONTHS.finditer(text or ""):
        token = match.group(1)
        value = int(token) if token.isdigit() else MONTH_VALUES.get(token, 0)
        if value:
            found.add(value)
    return found


def _range_months(text: str) -> set[int]:
    found = set()
    for match in MONTH_RANGE.finditer(text or ""):
        months = (int(match.group(3)) - int(match.group(1))) * 12 + int(match.group(4)) - int(match.group(2)) + 1
        if 1 <= months <= 36:
            found.add(months)
    return found


def durations_conflict(source: str, answers: str) -> bool:
    """True when the source and a follow-up name different lengths for one stint."""
    left = _explicit_months(source)
    right = _explicit_months(answers) | (_range_months(answers) if answers else set())
    return bool(left and right and left.isdisjoint(right))


def _issue(item_id, severity, code, message, repair_action=None) -> Issue:
    return Issue(item_id=item_id or "document", severity=severity, code=code, message=message, repair_action=repair_action)


def _schools(text: str) -> list[str]:
    """School names only. A leading verb such as 就读 must not become part of the name."""
    found = []
    for match in _SCHOOL_SUFFIX.finditer(text or ""):
        index = match.start() - 1
        chars = []
        while index >= 0 and len(chars) < 12 and "\u4e00" <= text[index] <= "\u9fff":
            chars.append(text[index])
            index -= 1
        name = "".join(reversed(chars)) + match.group()
        for lead in ("就读于", "毕业于", "就读", "毕业", "来自"):
            if name.startswith(lead) and len(name) - len(lead) >= 4:
                name = name[len(lead):]
                break
        if len(name) >= 4 and name not in found:
            found.append(name)
    return found


def _identity_tokens(*blobs: str) -> set[str]:
    text = "\n".join(blobs)
    return set(EMAIL.findall(text)) | set(PHONE.findall(text))


def blocking_gates(job: dict, draft) -> list[Issue]:
    """Hard stops before the writing review. Warnings are added after it."""
    source = (job.get("input") or {}).get("source_text") or ""
    contact = (job.get("input") or {}).get("contact") or ""
    user_schools = [row.get("school", "") for row in (job.get("input") or {}).get("education") or [] if row.get("school")]
    answers = "\n".join(row.get("answer") or "" for row in job.get("answer_context") or [])
    issues = []
    if job.get("mode", "generate") == "generate":
        for section in draft.sections:
            if section.items and section.kind not in CANONICAL_KINDS and section.title not in GENERIC_BLOCK_TITLES:
                issues.append(_issue(section.id, "blocking", "structure",
                                      f"一级板块只能是专业技能、项目、工作 / 实习经历、校园与荣誉。请把「{section.title}」并入对应板块，不要自建一级标题。"))
    allowed = _identity_tokens(contact, source)
    seen = draft_text(draft)
    invented = [token for token in EMAIL.findall(seen) + PHONE.findall(seen) if token not in allowed]
    if invented:
        issues.append(_issue("document", "blocking", "unsupported",
                              f"联系方式「{'、'.join(invented)}」不在你填写的联系方式里，原文也没有这串字符。不能编造电话或邮箱。"))
    for found in _schools(seen):
        if found in user_schools or found in source:
            continue
        fuller = next((item for item in _schools(source) if item.startswith(found[:2]) and found not in item and len(found) < len(item)), "")
        if fuller:
            message = f"学校名「{found}」不是原文全称「{fuller}」。用户没有填写这个简称时，必须逐字使用全称，不能缩写。"
        else:
            message = f"学校名「{found}」不在你填写的教育经历里，原文也没有这所学校。不能编造或改写学校。"
        issues.append(_issue("document", "blocking", "unsupported", message))
        break
    if durations_conflict(source, answers):
        stated = _explicit_months(draft_text(draft)) or _range_months(draft_text(draft)) or any(
            section.start_date or section.end_date for section in draft.sections if section.kind == "work")
        if stated and "【待确认" not in draft_text(draft):
            issues.append(_issue("document", "blocking", "fact_card_conflict",
                                  "实习或任职时长在材料和补充回答里不一致。不要自行选定一个月或两个月，请在该条写上【待确认：…】。"))
    for section in draft.sections:
        if not section.start_date or not section.end_date or section.end_date == "至今":
            continue
        for item in section.items:
            for match in ITEM_PERIOD.finditer(item.text):
                start = f"{match.group(1)}-{int(match.group(2)):02d}"
                end = f"{match.group(3)}-{int(match.group(4)):02d}"
                if start != section.start_date or end != section.end_date:
                    issues.append(_issue(section.id, "blocking", "conflict",
                                          "同一项目里的起止时间不一致。排序不能改日期，请改回这段经历原文中的时间。"))
                    break
            else:
                continue
            break
    return issues


def _anchors(source: str) -> list[str]:
    names = [match.group(1).strip() for match in PROJECT_HEADING.finditer(source)]
    names.extend(match.group(1).strip() for match in FICTIONAL_ORG.finditer(source))
    if "集训队" in source:
        names.append("集训队")
    if "学生会" in source:
        names.append("学生会")
    return names


def _covered(name: str, blob: str) -> bool:
    if name and name in blob:
        return True
    cjk = re.sub(r"[^\u4e00-\u9fff]", "", name)
    if len(cjk) <= 3:
        return cjk in blob
    return any(cjk[i:i + 4] in blob for i in range(len(cjk) - 3))


def _warn(issues, item_id, message):
    issues.append(_issue(item_id, "warning", "quality", message, "revise"))


def gate_warnings(job: dict, draft) -> list[Issue]:
    """Writing gates that send the draft back once. They do not block export by themselves."""
    source = (job.get("input") or {}).get("source_text") or ""
    user_schools = [row.get("school", "") for row in (job.get("input") or {}).get("education") or [] if row.get("school")]
    stage = (job.get("input") or {}).get("career_stage") or "unspecified"
    blob = draft_text(draft)
    issues = []
    source_schools = _schools(source)
    if user_schools and source_schools and not any(
            user == src or user in src or src in user for user in user_schools for src in source_schools):
        issues.append(_issue(draft.education[0].id if draft.education else "document", "warning", "quality",
                              f"你填写的学校「{user_schools[0]}」与材料中的「{source_schools[0]}」不一致，已按你填写的呈现。请确认用哪一个。"))
    missing_markers = [marker for marker in STRONG_MARKERS if marker in source and marker not in blob]
    if missing_markers:
        _warn(issues, "document", f"原文有强结果（{'、'.join(missing_markers)}），正文必须保留，不能因为压缩或跳过追问删掉。")
    group = re.search(r"(\d+)\s*组中\s*(\d+)\s*组", source)
    if group and (group.group(1) not in blob or group.group(2) not in blob):
        _warn(issues, "document", "原文有「几组中几组」这类结果，正文要用同样的数字写上。")
    missing = [name for name in _anchors(source) if not _covered(name, blob)]
    if missing:
        _warn(issues, "document", f"原文中的经历「{missing[0]}」没有进入正文。跳过追问也不能把已有材料写掉。")
    for section in draft.sections:
        if section.kind == "campus":
            continue
        if AWARD_WORD.search(section_blob(section)):
            _warn(issues, section.id, "竞赛、奖项和集训队写入「校园与荣誉」，不要单独成块，也不要放进项目或技能。")
            break
    if draft.summary and AWARD_WORD.search(draft.summary.text):
        _warn(issues, "__summary", "竞赛和奖项不要写进简介，放到「校园与荣誉」。")
    for phrase in NEGATIVE_PHRASES:
        if phrase in blob and phrase in source:
            _warn(issues, "document", "对求职不利或无关的句子（下线、未推广、他人完成、试运行后停止）默认省略，不要照搬。不能改成更强的状态。")
            break
    if stage == "entry" and draft.summary:
        _warn(issues, "__summary", "校招默认不写个人总结。请删除简介，避免把技能和项目再复述一遍。")
    elif draft.summary:
        skills = "\n".join(section_blob(section) for section in draft.sections if section.kind == "skills")
        named = [tech for tech in TECHNOLOGIES if re.search(r"(?<![A-Za-z])" + re.escape(tech) + r"(?![A-Za-z])", draft.summary.text, re.IGNORECASE)]
        if len(named) >= 3 and skills and all(tech.lower() in skills.lower() for tech in named) and not re.search(r"实现|负责|完成|编写|交付", draft.summary.text):
            _warn(issues, "__summary", "简介不要复述技能清单。有多年经验时只保留一句有依据的方向说明。")
    if stage == "entry" and sum(len(part) for part in (blob,)) > _PAGE_CHARS:
        issues.append(_issue("document", "warning", "quality", "校招简历尽量一页。请压缩重复背景，保留动作、方法和原文结果。"))
    return issues
