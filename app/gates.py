"""Program gates for the writing checklist. Filtering may drop a fact, never strengthen it."""
import re

from app.generation_models import Issue
from app.resume_layout import CANONICAL_KINDS, presentation_highlights, section_blob
from app.skill import TECHNOLOGIES

# Older tasks and hand-edited drafts used these labels with kind "other".
GENERIC_BLOCK_TITLES = {
    "项目", "项目经历", "专业技能", "技能", "技能与实践",
    "工作 / 实习经历", "工作／实习经历", "工作／实习", "实习",
    "校园与荣誉", "教育经历", "教育背景",
}
_BLOCK_TITLES = {"教育经历", "专业技能", "项目", "项目经历", "工作 / 实习经历", "工作／实习经历", "工作/实习经历", "校园与荣誉", "实习"}
SKILL_NAMES = ("Spring Boot", "MySQL Binlog", "OceanBase OMS", "分库分表", "配置对账", "告警治理") + tuple(sorted(TECHNOLOGIES, key=len, reverse=True))
LEVEL_RANK = {"了解": 1, "熟悉": 2, "掌握": 3, "熟练": 3, "精通": 4}

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
NEGATIVE_CLAUSE = re.compile(
    r"未正式推广|尚未推广|没有正式推广|没正式推广|未推广|"
    r"已下线|未上线|没有上线|并未上线|"
    r"试运行结束后|而停止|后停止|已停止|"
    r"其他组员|其他成员|由他人|"
    r"未获奖|没有获奖|只进初赛"
)
FAMILIAR_CLAIM = re.compile(r"(熟悉|精通|掌握|熟练使用|熟练)([^，。；;\n]{2,40})")
FAMILIAR_FILLER = {"基础", "常用", "相关", "以及", "能够", "可以", "一个", "我们", "进行", "使用", "开发", "编程", "方面", "能力"}
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


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def clause_is_negative_copy(clause: str, source: str) -> bool:
    """A negative or stop clause copied from the source, whatever the contact field says."""
    if not clause or not NEGATIVE_CLAUSE.search(clause):
        return False
    piece, hay = _compact(clause), _compact(source)
    if len(piece) >= 8 and any(piece[index:index + 8] in hay for index in range(len(piece) - 7)):
        return True
    return any(match.group(0) in (source or "") for match in NEGATIVE_CLAUSE.finditer(clause))


def copied_negative_clauses(text: str, source: str) -> list[str]:
    found = []
    for sentence in re.split(r"[。；;\n]+", text or ""):
        pieces = re.split(r"[，,]", sentence) if NEGATIVE_CLAUSE.search(sentence or "") else [sentence]
        for piece in pieces:
            piece = piece.strip()
            if clause_is_negative_copy(piece, source) and piece not in found:
                found.append(piece)
    return found


def _drop_negative_clauses(text: str, source: str) -> str:
    if not text or not copied_negative_clauses(text, source):
        return text
    kept = []
    for sentence in re.split(r"[。；;\n]+", text):
        sentence = sentence.strip()
        if not sentence:
            continue
        if NEGATIVE_CLAUSE.search(sentence):
            parts = [part.strip() for part in re.split(r"[，,]", sentence) if part.strip() and not clause_is_negative_copy(part, source)]
            sentence = "，".join(parts)
        if sentence:
            kept.append(sentence)
    return "。".join(kept) + ("。" if kept else "")


def _mentions_tech(text: str, tech: str) -> bool:
    return re.search(r"(?<![A-Za-z])" + re.escape(tech) + r"(?![A-Za-z])", text or "", re.IGNORECASE) is not None


def weak_techs(source: str, jd: str) -> list[str]:
    """Tools the source only touched lightly, and the JD does not ask for."""
    found = []
    for tech in TECHNOLOGIES:
        if _mentions_tech(jd or "", tech):
            continue
        pattern = re.compile(
            rf"(了解|接触|试用).{{0,16}}(?<![A-Za-z]){re.escape(tech)}(?![A-Za-z])|"
            rf"(?<![A-Za-z]){re.escape(tech)}(?![A-Za-z]).{{0,24}}(了解|课程实验|官方镜像|跑过)",
            re.IGNORECASE)
        if pattern.search(source or ""):
            found.append(tech)
    return found


def _without_weak_sentences(text: str, techs: list[str]) -> str:
    """Drop a skills line that is only about a weakly evidenced tool, or just that sentence."""
    sentences = [sentence.strip() for sentence in re.split(r"[。；;\n]+", text or "") if sentence.strip()]
    if not sentences or not any(_mentions_tech(text, tech) for tech in techs):
        return text
    if all(any(_mentions_tech(sentence, tech) for tech in techs) for sentence in sentences):
        return ""
    kept = [sentence for sentence in sentences if not any(_mentions_tech(sentence, tech) for tech in techs)]
    return "。".join(kept) + ("。" if kept else "")


def _content_tokens(text: str) -> set[str]:
    chars = re.findall(r"[\u4e00-\u9fff]", text or "")
    pieces = {"".join(chars[index:index + 2]) for index in range(len(chars) - 1)}
    pieces.update(re.findall(r"[A-Za-z][A-Za-z0-9+#.]{1,}", text or ""))
    return pieces


DETAIL_PROMPT = re.compile(r"多少|几人|几名|几位|什么时候|哪年|哪一年|起止|日期|时间|年份|个人赛|团队赛|人数|时长|篇数|名次")
COVERAGE_GAP = re.compile(
    r"没有.{0,24}(?:证据|经历|材料)|无.{0,16}(?:证据|经历)|缺材料|暂不写入|暂无可写|无可写|JD|优先项|不写入|"
    r"缺少.{0,20}(?:经验|经历)|缺乏.{0,12}(?:经验|经历)|生产环境|线上经验|线上/"
)
MARKER_TEXT = re.compile(r"【待补充：([^】]*)】")
PROMPT_STOPWORDS = {"什么", "是否", "可以", "这个", "一个", "我们", "还有", "关于", "相关", "材料", "证据", "经历", "没有", "暂不"}
MAX_MARKERS = 4


def _prompt_tokens(text: str) -> set[str]:
    return {token for token in _content_tokens(text) if token not in PROMPT_STOPWORDS}


def is_coverage_gap(text: str) -> bool:
    return bool(COVERAGE_GAP.search(text or ""))


_FILL_IN = (
    (re.compile(r"多少人|几名|人数|多少名"), "使用人数"),
    (re.compile(r"个人赛|团队赛|组队"), "个人赛还是团队赛"),
    (re.compile(r"负责|承担"), "个人负责的模块"),
    (re.compile(r"效果|结果数据|性能数据"), "效果数据"),
    (re.compile(r"单元测试"), "单元测试覆盖范围"),
    (re.compile(r"起止|哪年|哪一年|日期|年份"), "起止时间"),
    (re.compile(r"岗位|角色"), "岗位名称"),
    (re.compile(r"多少篇|篇数"), "大约多少篇"),
)


def marker_label(text: str) -> str | None:
    """A complete short fill-in, or nothing. Never a truncated question."""
    cleaned = re.sub(r"^待补充[:：]?", "", (text or "").strip().strip("【】")).strip()
    if not cleaned or is_coverage_gap(cleaned):
        return None
    for pattern, label in _FILL_IN:
        if pattern.search(cleaned):
            return label
    return None


def is_detail_prompt(text: str, sections: list[dict] | None = None) -> bool:
    """A fill-in for an existing sentence, not a missing capability."""
    del sections
    return marker_label(text) is not None


def _sentences(text: str) -> list[str]:
    return [part for part in re.split(r"(?<=[。；\n])", text or "") if part.strip()]


def _sentence_score(sentence: str, prompt: str) -> int:
    overlap = _prompt_tokens(sentence) & _prompt_tokens(prompt)
    return sum(len(token) for token in overlap)


TOPIC_KEYWORDS = {
    "使用人数": ("试运行", "覆盖", "用户", "使用"),
    "个人负责的模块": ("负责", "模块", "接口"),
    "效果数据": ("结果", "响应", "压测"),
    "单元测试覆盖范围": ("单元测试",),
    "起止时间": ("起止", "期间"),
    "个人赛还是团队赛": ("铜奖", "省赛", "集训", "比赛"),
    "岗位名称": ("岗位", "角色"),
    "大约多少篇": ("排版", "篇"),
}
MARKER_SCORE_FLOOR = 2


def _topic_score(sentence: str, label: str) -> int:
    return sum(len(word) for word in TOPIC_KEYWORDS.get(label, ()) if word in sentence)


def _tighten_punctuation(text: str) -> str:
    """Drop the stray space in '， Spring Boot'."""
    return re.sub(r"([，。；：、！？])[ \t]+", r"\1", text or "")


def _insert_marker_after(text: str, sentence: str, marker: str) -> str:
    if marker in text:
        return text
    index = text.find(sentence)
    if index < 0:
        return text.rstrip() + "\n" + marker
    end = index + len(sentence)
    rest = text[end:]
    gap = "\n" if rest and not rest.startswith("\n") else ""
    return text[:end].rstrip() + "\n" + marker + gap + rest


def _detail_already_present(section: dict, item: dict, label: str) -> bool:
    """Skip a fill-in when the heading, dates, or sentence already answer it."""
    blob = " ".join(filter(None, (
        section.get("title"), section.get("organization"), section.get("role"),
        section.get("start_date"), section.get("end_date"), item.get("text"),
    )))
    if label == "个人负责的模块":
        return re.search(r"负责\s*\S", blob) is not None
    if label == "起止时间":
        if section.get("start_date") and section.get("end_date"):
            return True
        return re.search(r"\d{4}[.\-/]\d{1,2}\s*[\-—–~到至]+\s*\d{4}[.\-/]\d{1,2}", blob) is not None
    if label == "岗位名称":
        return bool(section.get("role"))
    if label == "使用人数":
        return re.search(r"\d+\s*(?:多)?\s*(?:名|位)", item.get("text") or "") is not None
    if label == "效果数据":
        return re.search(r"\d+", item.get("text") or "") is not None
    if label == "大约多少篇":
        return re.search(r"\d+\s*篇", item.get("text") or "") is not None
    if label == "个人赛还是团队赛":
        return re.search(r"个人赛|团队|组队|小组", blob) is not None
    return False


def _strip_body_markers(text: str) -> tuple[str, list[str]]:
    removed = []

    def replace(match):
        removed.append(match.group(1).strip())
        return ""

    cleaned = re.sub(r"[ \t]+\n", "\n", MARKER_TEXT.sub(replace, text or ""))
    cleaned = re.sub(r"\n{2,}", "\n", cleaned).strip()
    return cleaned, removed


def _is_skills_block(section: dict) -> bool:
    return section.get("kind") == "skills" or "技能" in (section.get("title") or "")


def _marker_already_written(sections: list[dict], label: str) -> bool:
    marker = f"【待补充：{label}】"
    return any(marker in (item.get("text") or "") for section in sections for item in section.get("items") or [])


def _inject_gap_markers(sections: list[dict], prompts: list[str]) -> list[str]:
    """One marker per label, never in skills, only on a sentence that clears the topic threshold."""
    notes, placed = [], 0
    best_for_label: dict[str, tuple] = {}
    for prompt in prompts:
        if not prompt:
            continue
        label = marker_label(prompt)
        if is_coverage_gap(prompt) or not label:
            if prompt not in notes:
                notes.append(prompt)
            continue
        choice = best_for_label.get(label)
        best_score, best_item, best_section, best_sentence = (choice[1:] if choice else (0, None, None, ""))
        for section in sections:
            if _is_skills_block(section):
                continue
            for item in section.get("items") or []:
                for sentence in _sentences(item.get("text") or ""):
                    score = _topic_score(sentence, label)
                    if score > best_score:
                        best_score, best_item, best_section, best_sentence = score, item, section, sentence
        best_for_label[label] = (prompt, best_score, best_item, best_section, best_sentence)
    for label, (prompt, score, item, section, sentence) in best_for_label.items():
        if (_marker_already_written(sections, label) or placed >= MAX_MARKERS or score < MARKER_SCORE_FLOOR
                or item is None or "【待补充" in (item.get("text") or "")):
            if prompt not in notes and not _marker_already_written(sections, label):
                notes.append(prompt)
            continue
        if _detail_already_present(section, item, label):
            continue
        item["text"] = _insert_marker_after(item.get("text") or "", sentence, f"【待补充：{label}】")
        item["highlights"] = [phrase for phrase in item.get("highlights") or [] if phrase and phrase in item["text"]]
        placed += 1
    return notes


def _skipped_followups(job: dict) -> list[str]:
    if not job.get("answered") or job.get("answer_context"):
        return []
    plan = job.get("plan") or {}
    prompts = [question.get("text", "").strip() for question in plan.get("questions") or [] if isinstance(question, dict) and question.get("text")]
    prompts.extend(gap.strip() for gap in plan.get("gaps") or [] if isinstance(gap, str) and gap.strip())
    return prompts


def _skill_hits(text: str) -> list[str]:
    found, occupied = [], [False] * (len(text or "") + 1)
    for name in SKILL_NAMES:
        for match in re.finditer(r"(?<![A-Za-z])" + re.escape(name) + r"(?![A-Za-z])", text or "", re.IGNORECASE):
            if any(occupied[match.start():match.end()]):
                continue
            for index in range(match.start(), match.end()):
                occupied[index] = True
            found.append(name)
    return found


def _stated_level(source: str, skill: str) -> int:
    best = 0
    for match in re.finditer(re.escape(skill), source or "", re.IGNORECASE):
        left = max(source.rfind(mark, 0, match.start()) for mark in ("，", "。", "；", ";", "\n")) + 1
        stops = [source.find(mark, match.end()) for mark in ("，", "。", "；", ";", "\n")]
        stops = [stop for stop in stops if stop >= 0]
        right = min(stops) if stops else len(source)
        window = source[left:right]
        for word, rank in LEVEL_RANK.items():
            if word in window:
                best = max(best, rank)
    return best


def proficiency_violations(claim: str, source: str) -> list[str]:
    """Block 熟悉/掌握/精通/熟练 unless the source states that level for the skill."""
    violations = []
    for word in ("精通", "熟练使用", "熟练", "掌握", "熟悉"):
        rank = LEVEL_RANK["熟练" if word == "熟练使用" else word]
        for match in re.finditer(word, claim or ""):
            window = claim[max(0, match.start() - 20):match.end() + 24]
            skills = _skill_hits(window) or _skill_hits(claim)
            for skill in skills:
                if _stated_level(source, skill) < rank:
                    label = f"{word}{skill}"
                    if label not in violations:
                        violations.append(label)
    return violations


def proficiency_downgrades(claim: str, source: str) -> list[str]:
    """Flag an explicit weaker level when the cited source states a stronger one."""
    downgraded = []
    for skill in _skill_hits(claim):
        source_rank = _stated_level(source, skill)
        claim_rank = _stated_level(claim, skill)
        if source_rank and claim_rank and claim_rank < source_rank:
            source_word = next(word for word, rank in LEVEL_RANK.items() if rank == source_rank)
            label = f"{source_word}{skill}"
            if label not in downgraded:
                downgraded.append(label)
    return downgraded


def soften_proficiency(text: str, source: str) -> str:
    """Drop a proficiency word the source does not state. Keep the skill and its own qualifier."""
    def replace(match):
        word = match.group(0)
        rank = LEVEL_RANK["熟练" if word == "熟练使用" else word]
        window = text[max(0, match.start() - 20):match.end() + 24]
        skills = _skill_hits(window)
        if skills and any(_stated_level(source, skill) < rank for skill in skills):
            return ""
        if not skills and word not in (source or ""):
            return ""
        return word

    softened = re.sub(r"精通|熟练使用|熟练|掌握|熟悉", replace, text or "")
    return re.sub(r"[：:]{2,}", "：", re.sub(r"\s{2,}", " ", softened)).strip()


def _clear_block_name(value: str) -> str:
    text = (value or "").strip()
    if text in _BLOCK_TITLES:
        return ""
    for label in sorted(_BLOCK_TITLES, key=len, reverse=True):
        text = text.replace(label, "")
    return text.strip(" ·")


def _restore_honor_heading(section: dict, source: str) -> None:
    if section.get("kind") != "campus":
        return
    for key in ("title", "organization", "role"):
        section[key] = _clear_block_name(section.get(key) or "")
    match = re.search(r"(校\s*ACM\s*集训队)\s*(队员|队长)", source or "")
    blob = " ".join(filter(None, (section.get("title"), section.get("organization"), section.get("role"),
                                   " ".join(item.get("text") or "" for item in section.get("items") or []))))
    generic = (section.get("title") or "") in {"", "荣誉", "校园经历"}
    about_team = any(token in blob for token in ("ACM", "集训", "铜奖", "省赛", "队员"))
    if match and (generic or about_team or not (section.get("title") or section.get("role"))):
        section["title"] = re.sub(r"\s+", " ", match.group(1)).strip()
        section["role"] = match.group(2)
        section["organization"] = ""
        return
    if not (section.get("title") or "").strip():
        section["title"] = section.get("organization") or section.get("role") or "荣誉"
        if section.get("organization") == section["title"]:
            section["organization"] = ""


def _project_teams(source: str) -> list[tuple[str, str]]:
    found = []
    for match in re.finditer(r"项目[^\n：:]{0,8}[：:]\s*([^（\n]+?)（([^）]*)）", source or ""):
        count = re.search(r"(\d+)\s*人", match.group(2))
        if count:
            found.append((match.group(1).strip(), count.group(1)))
    return found


def _project_overlap(blob: str, name: str) -> int:
    generic = {"项目", "后端", "课程", "设计", "开发"}
    return sum(1 for index in range(len(name) - 1) if name[index:index + 2] not in generic and name[index:index + 2] in blob)


def _restore_team_sizes(sections: list[dict], source: str) -> None:
    """Keep the source headcount on the role line, even when the role is only a job title."""
    for name, count in _project_teams(source):
        label = f"{count} 人小组"
        best, best_score = None, 0
        for section in sections:
            if section.get("kind") not in ("project", "other", "research"):
                continue
            blob = section_blob(section) + (section.get("title") or "") + (section.get("role") or "")
            score = _project_overlap(blob, name)
            if score > best_score:
                best, best_score = section, score
        if best is None or best_score < 1:
            continue
        blob = section_blob(best) + (best.get("title") or "") + (best.get("role") or "")
        if re.search(rf"{count}\s*人", blob):
            continue
        role = best.get("role") or ""
        best["role"] = f"{role}（{label}）" if role else label


def _merge_single_research_output(section: dict) -> None:
    """Keep two descriptions of one paper/model as one resume bullet."""
    items = section.get("items") or []
    title = section.get("title") or ""
    if len(items) != 2 or not (section.get("kind") == "research" or any(word in title for word in ("科研", "学术", "论文"))):
        return
    research_words = re.compile(r"论文|发表|期刊|模型|算法|方法|研究|实验")
    if not all(research_words.search(item.get("text") or "") for item in items):
        return
    left_ids, right_ids = set(items[0].get("fact_ids") or []), set(items[1].get("fact_ids") or [])
    texts = [item.get("text") or "" for item in items]
    same_output = any(re.search(r"论文|发表|期刊|作者|学生一作", text) for text in texts) and any(
        re.search(r"模型|算法|方法|机制|实验", text) for text in texts)
    if not left_ids.intersection(right_ids) and not same_output:
        return
    left = (items[0].get("text") or "").rstrip("。；; ")
    right = (items[1].get("text") or "").rstrip("。；; ")
    merged = dict(items[0])
    merged["text"] = f"{left}；{right}。"
    merged["fact_ids"] = list(dict.fromkeys([*(items[0].get("fact_ids") or []), *(items[1].get("fact_ids") or [])]))
    merged["highlights"] = [value for value in dict.fromkeys([*(items[0].get("highlights") or []), *(items[1].get("highlights") or [])]) if value in merged["text"]]
    section["items"] = [merged]


def _ensure_presentation_highlights(section: dict) -> None:
    """Add literal, bounded scan anchors without changing the resume wording."""
    for item in section.get("items") or []:
        text = item.get("text") or ""
        item["highlights"] = presentation_highlights(text, item.get("highlights"))


def missing_team_sizes(text: str, source: str) -> list[str]:
    missing = []
    for match in re.finditer(r"项目[^\n：:]{0,8}[：:]\s*([^（\n]+?)（[^）]*?(\d+)\s*人", source or ""):
        name, count = match.group(1).strip(), match.group(2)
        if (name[:4] in text or name[-4:] in text) and not re.search(rf"{count}\s*人", text):
            missing.append(f"{name[:8]}{count}人")
    return missing


def polish_draft(payload: dict, job: dict) -> dict:
    """Drop copied negative clauses and weak skill lines, then mark skipped gaps.

    Contact and school fields are intentionally unused: the same source produces
    the same body whether or not the user filled them in.
    """
    source = (job.get("input") or {}).get("source_text") or ""
    jd = (job.get("input") or {}).get("jd") or ""
    weak = weak_techs(source, jd)
    summary = payload.get("summary")
    if isinstance(summary, dict):
        summary["text"] = _drop_negative_clauses(summary.get("text") or "", source).strip()
        summary["highlights"] = [phrase for phrase in summary.get("highlights") or [] if phrase and phrase in summary["text"]]
        if not summary["text"]:
            payload["summary"] = None
    kept, removed_markers = [], []
    for section in payload.get("sections") or []:
        items = []
        skill_block = section.get("kind") == "skills" or "技能" in (section.get("title") or "")
        for item in section.get("items") or []:
            text = _tighten_punctuation(soften_proficiency(_drop_negative_clauses(item.get("text") or "", source), source)).strip()
            if skill_block and weak:
                text = _without_weak_sentences(text, weak).strip()
            text, removed = _strip_body_markers(text)
            removed_markers.extend(inner for inner in removed if inner)
            if not text:
                continue
            updated = dict(item)
            updated["text"] = text
            updated["highlights"] = [phrase for phrase in item.get("highlights") or [] if phrase and phrase in text]
            items.append(updated)
        if not items:
            continue
        updated_section = dict(section)
        updated_section["items"] = items
        _restore_honor_heading(updated_section, source)
        _merge_single_research_output(updated_section)
        _ensure_presentation_highlights(updated_section)
        kept.append(updated_section)
    _restore_team_sizes(kept, source)
    detail, coverage = [], []
    for prompt in [*removed_markers, *_skipped_followups(job)]:
        bucket = detail if is_detail_prompt(prompt, kept) else coverage
        if prompt not in bucket and prompt not in detail:
            bucket.append(prompt)
    # Missing details belong beside the candidate as follow-up notes. Putting
    # placeholders in the resume body makes a draft look broken and pollutes exports.
    notes = []
    for note in [*detail, *coverage]:
        if note not in notes:
            notes.append(note)
    job["coverage_notes"] = notes
    payload["sections"] = kept
    return payload


def ungrounded_familiarity(claim: str, source: str) -> str:
    """Familiarity claims whose object is absent from the cited source."""
    missing = []
    for match in FAMILIAR_CLAIM.finditer(claim or ""):
        tokens = [token for token in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z+#.]{2,}", match.group(2)) if token not in FAMILIAR_FILLER]
        missing.extend(token for token in tokens if token.lower() not in (source or "").lower() and token not in missing)
    return "、".join(missing[:4])


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
    if job.get("mode", "generate") == "generate":
        copied = copied_negative_clauses(seen, source)
        if copied:
            shown = "；".join(copied[:2])[:80]
            issues.append(_issue("document", "blocking", "conflict",
                                  f"负面或结束状态被照搬进正文：「{shown}」。删掉这一句，不要改成更强的状态。"))
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
