from typing import Literal

from pydantic import Field, model_validator

from app.models import Item, ResumeContent, Section, StrictModel


class Evidence(StrictModel):
    id: str
    text: str = Field(min_length=1, max_length=2000)
    start: int = Field(ge=0)
    end: int = Field(gt=0)


class Question(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=300)


class Plan(StrictModel):
    decision: Literal["ask", "draft"]
    selected_fact_ids: list[str] = Field(default_factory=list, max_length=100)
    focus: list[str] = Field(default_factory=list, max_length=6)
    questions: list[Question] = Field(default_factory=list, max_length=3)
    gaps: list[str] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def check_questions(self):
        if (self.decision == "ask") != bool(self.questions):
            raise ValueError("ask 需要问题，draft 不能带问题")
        if len({q.id for q in self.questions}) != len(self.questions):
            raise ValueError("问题标识重复")
        return self


class Claim(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1, max_length=100)


class DraftSection(StrictModel):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    title: Literal["教育背景", "工作经历", "项目经历", "研究经历", "技能与实践", "作品与活动", "个人优势"]
    items: list[Claim] = Field(min_length=1, max_length=15)


class Draft(StrictModel):
    summary: Claim | None = None
    sections: list[DraftSection] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def check_ids(self):
        ids = [s.id for s in self.sections]
        claims = self.claims()
        if len(set(ids)) != len(ids) or len({c.id for c in claims}) != len(claims):
            raise ValueError("段落标识重复")
        if self.summary and self.summary.id != "__summary":
            raise ValueError("简介标识必须为 __summary")
        if sum(len(c.text) for c in claims) > 14000:
            raise ValueError("候选正文过长")
        return self

    def claims(self) -> list[Claim]:
        return ([self.summary] if self.summary else []) + [c for s in self.sections for c in s.items]

    def to_content(self, name: str, contact: str, target_role: str) -> ResumeContent:
        return ResumeContent(name=name, contact=contact, target_role=target_role,
                             summary=self.summary.text if self.summary else "",
                             sections=[Section(id=s.id, title=s.title, items=[Item(id=c.id, text=c.text) for c in s.items]) for s in self.sections])


class Issue(StrictModel):
    item_id: str = Field(default="document", max_length=80)
    severity: Literal["blocking", "warning"]
    code: Literal["reference", "unsupported", "attribution", "conflict", "quality", "fit"]
    message: str = Field(min_length=1, max_length=500)
    suggestion: str = Field(default="", max_length=500)


class Review(StrictModel):
    verdict: Literal["pass", "blocked"]
    issues: list[Issue] = Field(default_factory=list, max_length=40)
    strengths: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def check_verdict(self):
        blocked = any(i.severity == "blocking" for i in self.issues)
        if (self.verdict == "blocked") != blocked:
            raise ValueError("审阅结论与阻断问题不一致")
        return self


class GenerationInput(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")
    name: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    target_role: str = Field(min_length=1, max_length=80)
    source_text: str = Field(default="", max_length=20000)
    jd: str = Field(default="", max_length=8000)
    allow_questions: bool = True
    send_materials: bool = False


class AnswerInput(StrictModel):
    question_group: str = Field(min_length=1, max_length=80)
    answers: dict[str, str] = Field(default_factory=dict, max_length=3)
    skip: bool = False

    @model_validator(mode="after")
    def bound_answers(self):
        if sum(map(len, self.answers.values())) > 4000:
            raise ValueError("补充回答最多 4,000 字")
        if self.skip and self.answers:
            raise ValueError("跳过时不能提交回答")
        return self
