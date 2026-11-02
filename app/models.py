import hashlib
import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Period(StrictModel):
    start_date: str = Field(default="", max_length=7)
    end_date: str = Field(default="", max_length=7)

    @field_validator("start_date", "end_date", mode="before")
    @classmethod
    def valid_date(cls, value, info):
        if not isinstance(value, str):
            raise ValueError("时间须为年份或年月，未知留空")  # noqa: TRY004 -- API validation must remain a safe 422
        value = value.strip().replace(".", "-").replace("/", "-")
        if value == "" or (info.field_name == "end_date" and value == "至今"):
            return value
        if not re.fullmatch(r"(?:19|20|21)\d{2}(?:-(?:0[1-9]|1[0-2]))?", value):
            raise ValueError("时间格式应为 YYYY 或 YYYY-MM，未知留空")
        return value

    @model_validator(mode="after")
    def valid_period(self):
        if (self.start_date and self.end_date and self.end_date != "至今"
                and self.start_date + ("-01" if len(self.start_date) == 4 else "") > self.end_date + ("-12" if len(self.end_date) == 4 else "")):
            raise ValueError("结束时间不能早于开始时间")
        return self


class Education(Period):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    school: str = Field(default="", max_length=120)
    degree: str = Field(default="", max_length=40)
    major: str = Field(default="", max_length=80)

    @model_validator(mode="after")
    def meaningful_education(self):
        if not (self.school or self.degree or self.major):
            raise ValueError("教育经历请至少填写学校、学历或专业之一")
        return self


class Highlighted(StrictModel):
    highlights: list[str] = Field(default_factory=list, max_length=2)

    @model_validator(mode="after")
    def valid_highlights(self):
        if any(not h.strip() or h not in self.text or len(h) > 30 for h in self.highlights):
            raise ValueError("重点必须是当前正文中的短语，每处不超过30字")
        if (len(set(self.highlights)) != len(self.highlights)
                or sum(len(h) * self.text.count(h) for h in self.highlights) > min(50, len(self.text) * 0.6)):
            raise ValueError("重点不能重复或覆盖大部分正文")
        return self


class Item(Highlighted):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=4000)


class Section(Period):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=60)
    kind: Literal["project", "work", "research", "skills", "other"] = "other"
    organization: str = Field(default="", max_length=120)
    role: str = Field(default="", max_length=80)
    items: list[Item] = Field(default_factory=list, max_length=30)


class ResumeContent(StrictModel):
    name: str = Field(default="", max_length=80)
    target_role: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    summary: str = Field(default="", max_length=2000)
    education: list[Education] = Field(default_factory=list, max_length=8)
    sections: list[Section] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_document(self):
        ids = [section.id for section in self.sections]
        item_ids = [item.id for section in self.sections for item in section.items]
        if len(set(ids)) != len(ids) or len(set(item_ids)) != len(item_ids):
            raise ValueError("段落标识不能重复")
        education_ids = [e.id for e in self.education]
        if len(set(education_ids)) != len(education_ids) or set(education_ids) & {*ids, *item_ids, "__summary"}:
            raise ValueError("教育、经历和正文标识不能重复或占用简介标识")
        if sum(len(item.text) for section in self.sections for item in section.items) + len(self.summary) > 20000:
            raise ValueError("简历正文不能超过 20,000 字")
        return self


class Fact(StrictModel):
    id: str
    block_id: str
    text: str
    source: Literal["user_statement", "fictional_demo", "ai_candidate"]


class AIInfo(StrictModel):
    job_id: str
    review_job_id: str
    review_status: Literal["passed", "blocked", "unreviewed"]
    content_hash: str
    skill_version: str
    source_map: dict[str, list[str]] = Field(default_factory=dict)
    issues: list[dict] = Field(default_factory=list)
    manual_takeover: bool = False
    resolution_history: list[dict] = Field(default_factory=list)
    quality: dict | None = None

    def has_blockers(self) -> bool:
        return any(i.get("severity") == "blocking" and i.get("resolution", {}).get("action") not in ("deleted", "source_reviewed") for i in self.issues)


def resume_hash(content: ResumeContent) -> str:
    value = content.model_dump()
    if not value["education"]:
        value.pop("education")
    for section in value["sections"]:
        for key, default in (("kind", "other"), ("organization", ""), ("role", ""), ("start_date", ""), ("end_date", "")):
            if section[key] == default:
                section.pop(key)
        for item in section["items"]:
            if not item["highlights"]:
                item.pop("highlights")
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


class ResumeRecord(StrictModel):
    id: str
    revision: int
    confirmed_revision: int | None = None
    origin: Literal["manual", "demo", "ai"]
    content: ResumeContent
    facts: list[Fact]
    created_at: str
    updated_at: str
    ai: AIInfo | None = None


class CreateResume(StrictModel):
    name: str = Field(default="", max_length=80)
    target_role: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    source_text: str = Field(default="", max_length=20000)
    education: list[Education] = Field(default_factory=list, max_length=8)


class SaveResume(StrictModel):
    expected_revision: int = Field(ge=1)
    content: ResumeContent


class RevisionRequest(StrictModel):
    expected_revision: int = Field(ge=1)


class ExportRequest(RevisionRequest):
    format: Literal["pdf", "docx"]
    draft: bool = False
