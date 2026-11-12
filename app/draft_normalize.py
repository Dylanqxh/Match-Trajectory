"""Make a draft's shape valid without adding or strengthening any claim."""

import re

_ID = re.compile(r"^[A-Za-z0-9_-]{1,80}$")
_KINDS = {"project", "work", "research", "skills", "campus", "other"}


def normalize_draft_payload(payload: dict, evidence_ids: list[str]) -> dict:
    if not isinstance(payload, dict):
        return payload
    known = [item for item in evidence_ids if isinstance(item, str) and _ID.fullmatch(item)]
    used: set[str] = set()
    sections = payload.get("sections")
    if isinstance(sections, list):
        cleaned = []
        for index, section in enumerate(sections):
            normalized = _section(section, index, used, known)
            if normalized:
                cleaned.append(normalized)
        if cleaned:
            payload = {**payload, "sections": cleaned}
    summary = payload.get("summary")
    if isinstance(summary, dict):
        text = _text(summary.get("text"))
        fact_ids = _ids(summary.get("fact_ids"), known)
        if text and fact_ids:
            payload = {**payload, "summary": {
                "id": "__summary", "text": text, "fact_ids": fact_ids, "highlights": _highlights(text, summary.get("highlights")),
            }}
        else:
            payload = {**payload, "summary": None}
    elif "summary" in payload and summary is not None and not isinstance(summary, dict):
        payload = {**payload, "summary": None}
    return payload


def _section(section, index: int, used: set[str], known: list[str]) -> dict | None:
    if not isinstance(section, dict):
        return None
    title = section.get("title") if isinstance(section.get("title"), str) else ""
    title = title.strip()[:60] or "经历"
    kind = section.get("kind") if section.get("kind") in _KINDS else _kind(title)
    fact_ids = _ids(section.get("fact_ids"), known)
    raw_items = section.get("items")
    if isinstance(raw_items, (str, dict)):
        raw_items = [raw_items]
    if not isinstance(raw_items, list):
        raw_items = []
    section_id = _unique_id(section.get("id"), f"s{index + 1}", used)
    items = []
    for item_index, item in enumerate(raw_items):
        normalized = _item(item, f"{section_id}_i{item_index + 1}", used, fact_ids, known)
        if normalized:
            items.append(normalized)
    if not items:
        return None
    start, end = _period(section.get("start_date"), section.get("end_date"))
    return {
        "id": section_id,
        "title": title,
        "kind": kind,
        "organization": _short(section.get("organization"), 120),
        "role": _short(section.get("role"), 80),
        "start_date": start,
        "end_date": end,
        "fact_ids": fact_ids,
        "items": items,
    }


def _item(item, fallback: str, used: set[str], section_ids: list[str], known: list[str]) -> dict | None:
    if isinstance(item, str):
        item = {"text": item}
    if not isinstance(item, dict):
        return None
    text = _text(item.get("text") if "text" in item else item.get("content"))
    if not text:
        return None
    fact_ids = _ids(item.get("fact_ids"), known) or list(section_ids)
    if not fact_ids:
        return None
    return {
        "id": _unique_id(item.get("id"), fallback, used),
        "text": text[:2000],
        "fact_ids": fact_ids[:100],
        "highlights": _highlights(text, item.get("highlights")),
    }


def _text(value) -> str:
    if isinstance(value, list):
        value = "\n".join(part.strip() for part in value if isinstance(part, str) and part.strip())
    if not isinstance(value, str):
        return ""
    return value.strip()


def _ids(value, known: list[str]) -> list[str]:
    if isinstance(value, str):
        value = [part.strip() for part in re.split(r"[,，\s]+", value) if part.strip()]
    if not isinstance(value, list):
        return []
    found = []
    for item in value:
        if isinstance(item, str) and item in known and item not in found:
            found.append(item)
    return found


def _highlights(text: str, value) -> list[str]:
    if not isinstance(value, list):
        return []
    kept = []
    for item in value:
        if not isinstance(item, str):
            continue
        phrase = item.strip()
        if not phrase or len(phrase) > 30 or phrase not in text or phrase in kept:
            continue
        kept.append(phrase)
        if len(kept) == 2:
            break
    if sum(len(phrase) * text.count(phrase) for phrase in kept) > min(50, max(len(text), 1) * 0.6):
        return []
    return kept


def _unique_id(value, fallback: str, used: set[str]) -> str:
    if isinstance(value, str) and _ID.fullmatch(value) and value not in used and value != "__summary":
        used.add(value)
        return value
    candidate = fallback if _ID.fullmatch(fallback) else "item"
    number = 2
    while candidate in used:
        candidate = f"{fallback}_{number}"
        number += 1
    used.add(candidate)
    return candidate


def _kind(title: str) -> str:
    if "技能" in title:
        return "skills"
    if "项目" in title:
        return "project"
    if "实习" in title or "工作" in title:
        return "work"
    if "校园" in title or "荣誉" in title:
        return "campus"
    if "科研" in title:
        return "research"
    return "other"


def _short(value, limit: int) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


def _date(value) -> str:
    if not isinstance(value, str):
        return ""
    text = value.strip().replace(".", "-").replace("/", "-").replace("年", "-").replace("月", "")
    if text in {"", "至今"}:
        return text
    if re.fullmatch(r"(?:19|20|21)\d{2}", text):
        return text
    match = re.fullmatch(r"((?:19|20|21)\d{2})-(\d{1,2})", text)
    if match and 1 <= int(match.group(2)) <= 12:
        return f"{match.group(1)}-{int(match.group(2)):02d}"
    return ""


def _period(start, end) -> tuple[str, str]:
    start, end = _date(start), _date(end)
    if start and end and end != "至今":
        start_key = start + ("-01" if len(start) == 4 else "")
        end_key = end + ("-12" if len(end) == 4 else "")
        if start_key > end_key:
            return "", ""
    return start, end
