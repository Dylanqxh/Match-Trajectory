from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Item(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=4000)


class Section(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    title: str = Field(min_length=1, max_length=60)
    items: list[Item] = Field(default_factory=list, max_length=30)


class ResumeContent(StrictModel):
    name: str = Field(default="", max_length=80)
    target_role: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    summary: str = Field(default="", max_length=2000)
    sections: list[Section] = Field(default_factory=list, max_length=12)

    @model_validator(mode="after")
    def validate_document(self):
        ids = [section.id for section in self.sections]
        item_ids = [item.id for section in self.sections for item in section.items]
        if len(set(ids)) != len(ids) or len(set(item_ids)) != len(item_ids):
            raise ValueError("段落标识不能重复")
        if sum(len(item.text) for section in self.sections for item in section.items) + len(self.summary) > 20000:
            raise ValueError("简历正文不能超过 20,000 字")
        return self


class Fact(StrictModel):
    id: str
    block_id: str
    text: str
    source: Literal["user_statement", "fictional_demo"]


class ResumeRecord(StrictModel):
    id: str
    revision: int
    confirmed_revision: int | None = None
    origin: Literal["manual", "demo"]
    content: ResumeContent
    facts: list[Fact]
    created_at: str
    updated_at: str


class CreateResume(StrictModel):
    name: str = Field(default="", max_length=80)
    target_role: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    source_text: str = Field(default="", max_length=20000)


class SaveResume(StrictModel):
    expected_revision: int = Field(ge=1)
    content: ResumeContent


class RevisionRequest(StrictModel):
    expected_revision: int = Field(ge=1)


class ExportRequest(RevisionRequest):
    format: Literal["pdf", "docx"]
    draft: bool = False
