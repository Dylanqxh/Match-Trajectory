"""Shared, deterministic presentation; missing dates remain missing."""
import re

KIND_LABELS = {"project": "项目经历", "work": "工作／实习经历", "research": "科研经历", "skills": "专业技能", "other": ""}


def period_text(row):
    return " — ".join(filter(None, (row.start_date, row.end_date)))


def education_text(row):
    return " · ".join(filter(None, (row.school, row.degree, row.major)))


def section_text(row):
    return " · ".join(filter(None, (row.title, row.organization, row.role)))


def date_key(row):
    end = row.end_date
    return "9999" if end == "至今" else end or row.start_date


def ordered_sections(sections):
    result = list(sections)
    for kind in dict.fromkeys(row.kind for row in sections):
        indices = [i for i, row in enumerate(sections) if row.kind == kind]
        ordered = sorted((sections[i] for i in indices), key=date_key, reverse=True)
        for index, row in zip(indices, ordered, strict=True):
            result[index] = row
    return result


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
