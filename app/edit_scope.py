"""Deterministic edit locks for a few explicit requests.

Anything that is not one clear lock stays on the existing fact-gate path.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from app.gates import metric_tokens

_BOLD = re.compile(r"(?:只|仅)(?:改|修改|调整)?加粗")
_NUMBERS = re.compile(r"(?:只|仅)(?:改|修改)(?:数字相关|数字|百分比|指标)")
_KEEP_NUMBERS = re.compile(r"保留数字|数字不变|别改数字|不要改数字")
_PARAGRAPH = re.compile(r"只改第\d+段|只改这一段|只改该段|只改本段|指定某一段")
_QUOTE = re.compile(r"只改[「\"“](.+?)[」\"”]")
_INDEX = re.compile(r"只改第(\d+)段")


@dataclass(frozen=True)
class EditScope:
    kind: str = "general"
    item_ids: tuple[str, ...] = ()
    unresolved: str = ""


def classify_edit_scope(request: str, content=None) -> EditScope:
    compact = re.sub(r"\s+", "", request or "")
    intents = []
    if _BOLD.search(compact):
        intents.append("bold")
    if _NUMBERS.search(compact):
        intents.append("numbers")
    if "润色" in compact and _KEEP_NUMBERS.search(compact):
        intents.append("polish")
    if _PARAGRAPH.search(compact) or _QUOTE.search(request or ""):
        intents.append("paragraph")
    if len(set(intents)) != 1:
        return EditScope()
    kind = intents[0]
    if kind != "paragraph":
        return EditScope(kind)
    return _paragraph_scope(request or "", compact, content)


def _paragraph_scope(request: str, compact: str, content) -> EditScope:
    missing = "没有定位到唯一的一段，因此没有保存。"
    if content is None:
        return EditScope("paragraph", unresolved=missing)
    items = [item for section in content.sections for item in section.items]
    index = _INDEX.search(compact)
    if index:
        number = int(index.group(1))
        if 1 <= number <= len(items):
            return EditScope("paragraph", (items[number - 1].id,))
        return EditScope("paragraph", unresolved=missing)
    quote = _QUOTE.search(request)
    if quote:
        needle = quote.group(1).strip()
        hits = [item.id for section in content.sections for item in section.items
                if needle and (needle in item.text or needle in (section.title or ""))]
        if len(set(hits)) == 1:
            return EditScope("paragraph", (hits[0],))
        return EditScope("paragraph", unresolved=missing)
    return EditScope("paragraph", unresolved=missing)


def scope_rejection(scope: EditScope, base, candidate, evidence=None) -> str:
    if scope.kind == "general":
        return ""
    if (base.location or "") != (candidate.location or "") or (base.profile_note or "") != (candidate.profile_note or ""):
        return _header_message(scope.kind)
    from app.resume_agent import _blocks, _presentations, _structure

    if scope.kind == "bold":
        if _structure(base) != _structure(candidate) or _blocks(base) != _blocks(candidate):
            return "只改加粗不能改正文、数字、字段或顺序，因此没有保存。"
        return ""
    if scope.kind == "numbers":
        return _number_rejection(base, candidate, evidence or [], _blocks, _presentations, _structure)
    if scope.kind == "polish":
        if _structure(base) != _structure(candidate):
            return "润色但保留数字不能调整顺序或字段，因此没有保存。"
        if _number_multiset(base, _blocks) != _number_multiset(candidate, _blocks):
            return "润色但保留数字要求原有数字都还在，因此没有保存。"
        return ""
    if scope.unresolved or not scope.item_ids:
        return scope.unresolved or "没有定位到唯一的一段，因此没有保存。"
    if _structure(base) != _structure(candidate):
        return "指定段落以外的正文和加粗保持不变，因此没有保存。"
    target = set(scope.item_ids)
    before, after = _blocks(base), _blocks(candidate)
    for item_id in dict.fromkeys([*before, *after]):
        if item_id not in target and before.get(item_id, "") != after.get(item_id, ""):
            return "指定段落以外的正文和加粗保持不变，因此没有保存。"
    before_marks, after_marks = _presentations(base), _presentations(candidate)
    for item_id in dict.fromkeys([*before_marks, *after_marks]):
        if item_id not in target and before_marks.get(item_id, []) != after_marks.get(item_id, []):
            return "指定段落以外的正文和加粗保持不变，因此没有保存。"
    return ""


def _header_message(kind: str) -> str:
    if kind == "bold":
        return "只改加粗不能改正文、数字、字段或顺序，因此没有保存。"
    if kind == "numbers":
        return "只改数字相关不能修改没有数字的句子、角色或日期，因此没有保存。"
    if kind == "polish":
        return "润色但保留数字要求原有数字都还在，因此没有保存。"
    return "指定段落以外的正文和加粗保持不变，因此没有保存。"


def _number_rejection(base, candidate, evidence, blocks, presentations, structure) -> str:
    if structure(base) != structure(candidate):
        return "只改数字相关不能调整顺序或字段，因此没有保存。"
    before, after = blocks(base), blocks(candidate)
    for item_id in dict.fromkeys([*before, *after]):
        if before.get(item_id, "") != after.get(item_id, "") and not re.search(r"\d", before.get(item_id, "")):
            return "只改数字相关不能修改没有数字的句子、角色或日期，因此没有保存。"
    before_marks, after_marks = presentations(base), presentations(candidate)
    for item_id in dict.fromkeys([*before_marks, *after_marks]):
        if before_marks.get(item_id, []) != after_marks.get(item_id, []) and not re.search(r"\d", before.get(item_id, "")):
            return "只改数字相关不能修改没有数字的句子、角色或日期，因此没有保存。"
    allowed = set(metric_tokens("\n".join(before.values())))
    for row in evidence:
        if isinstance(row, dict):
            allowed.update(metric_tokens(row.get("text") or ""))
    if not set(metric_tokens("\n".join(after.values()))) <= allowed:
        return "只改数字相关不能写入材料里没有的数字，因此没有保存。"
    return ""


def _number_multiset(content, blocks) -> list[str]:
    return sorted(re.findall(r"\d+(?:\.\d+)?", "\n".join(blocks(content).values())))
