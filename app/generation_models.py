from typing import ClassVar, Literal

from pydantic import Field, model_validator

from app.models import Education, Highlighted, Item, ResumeContent, Section, StrictModel
from app.resume_layout import (
    education_text,
    ordered_sections,
    period_text,
    section_text,
)


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


class Claim(Highlighted):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,80}$")
    text: str = Field(min_length=1, max_length=2000)
    fact_ids: list[str] = Field(min_length=1, max_length=100)


class SummaryClaim(Claim):
    id: Literal["__summary"]


class DraftEducation(Education):
    fact_ids: list[str] = Field(min_length=1, max_length=100)


class DraftSection(Section):
    fact_ids: list[str] = Field(default_factory=list, max_length=100)
    items: list[Claim] = Field(min_length=1, max_length=15)


class Draft(StrictModel):
    body_limit: ClassVar[int] = 14000
    summary: SummaryClaim | None = None
    education: list[DraftEducation] = Field(default_factory=list, max_length=8)
    sections: list[DraftSection] = Field(min_length=1, max_length=8)

    @model_validator(mode="after")
    def check_ids(self):
        ids = [s.id for s in self.sections]
        claims = self.claims()
        if len(set(ids)) != len(ids) or len({c.id for c in claims}) != len(claims):
            raise ValueError("段落标识重复")
        education_ids = [e.id for e in self.education]
        if len(set(education_ids)) != len(education_ids) or set(education_ids) & {*ids, *[c.id for c in claims], "__summary"}:
            raise ValueError("段落标识重复")
        if self.summary and self.summary.id != "__summary":
            raise ValueError("简介标识必须为 __summary")
        if sum(len(c.text) for c in claims) > self.body_limit:
            raise ValueError("候选正文过长")
        return self

    def claims(self) -> list[Claim]:
        return ([self.summary] if self.summary else []) + [c for s in self.sections for c in s.items]

    def metadata_claims(self, refs) -> list[Claim]:
        return [Claim(id=e.id, text=" ".join(filter(None, (education_text(e), period_text(e)))), fact_ids=e.fact_ids)
                for e in self.education if education_text(e) or period_text(e)] + [
            Claim(id=s.id, text=" ".join(filter(None, (section_text(s), period_text(s)))),
                  fact_ids=s.fact_ids or list(dict.fromkeys(ref for i in s.items for ref in i.fact_ids)) or refs)
            for s in self.sections]

    def to_content(self, name: str, contact: str, target_role: str, education=None) -> ResumeContent:
        return ResumeContent(name=name, contact=contact, target_role=target_role,
                             education=education if education is not None else [Education.model_validate(e.model_dump(exclude={"fact_ids"})) for e in self.education],
                             summary=self.summary.text if self.summary else "",
                             sections=[Section(**s.model_dump(exclude={"fact_ids", "items"}), items=[Item(id=c.id, text=c.text, highlights=c.highlights) for c in s.items]) for s in ordered_sections(self.sections)])


class ReviewClaim(Claim):
    text: str = Field(min_length=1, max_length=4000)


class ReviewSummaryClaim(ReviewClaim):
    id: Literal["__summary"]


class ReviewSection(DraftSection):
    items: list[ReviewClaim] = Field(default_factory=list, max_length=30)


class ReviewDraft(Draft):
    """Lossless review projection of every field accepted by the editor."""

    body_limit: ClassVar[int] = 20000
    summary: ReviewSummaryClaim | None = None
    sections: list[ReviewSection] = Field(default_factory=list, max_length=12)


class Issue(StrictModel):
    item_id: str = Field(default="document", max_length=80)
    severity: Literal["blocking", "warning"]
    code: Literal["reference", "unsupported", "attribution", "conflict", "quality", "fit"]
    message: str = Field(min_length=1, max_length=500)
    suggestion: str = Field(default="", max_length=500)
    repair_action: Literal["revise", "need_input"] | None = None


class Review(StrictModel):
    verdict: Literal["pass", "blocked"]
    issues: list[Issue] = Field(default_factory=list, max_length=40)
    strengths: list[str] = Field(default_factory=list, max_length=5)
    quality: "QualityReview | None" = None

    @model_validator(mode="after")
    def check_verdict(self):
        blocked = any(i.severity == "blocking" for i in self.issues)
        if (self.verdict == "blocked") != blocked:
            raise ValueError("审阅结论与阻断问题不一致")
        return self


class QualityDimension(StrictModel):
    dimension: Literal["fit", "contribution", "evidence", "readability"]
    score: Literal[0, 1, 2] | None
    reason: str = Field(min_length=1, max_length=300)
    item_ids: list[str] = Field(default_factory=list, max_length=8)
    evidence_ids: list[str] = Field(default_factory=list, max_length=12)
    action: Literal["keep", "revise", "need_input", "not_applicable"]

    @model_validator(mode="after")
    def consistent_action(self):
        if (self.score is None) != (self.action == "not_applicable"):
            raise ValueError("质量不适用须与空分数一致")
        if self.action == "revise" and (not self.item_ids or not self.evidence_ids):
            raise ValueError("质量修正须定位当前内容和已有证据")
        if self.score == 2 and (not self.item_ids or not self.evidence_ids):
            raise ValueError("质量高分须定位当前内容和已有证据")
        if self.score == 0 and self.action == "keep":
            raise ValueError("质量零分须说明修正或材料缺口")
        return self


class InterviewTopic(StrictModel):
    item_id: str = Field(min_length=1, max_length=80)
    question: str = Field(min_length=1, max_length=180)
    evidence_ids: list[str] = Field(min_length=1, max_length=12)


class QualityReview(StrictModel):
    status: Literal["ready", "revise", "insufficient"]
    dimensions: list[QualityDimension] = Field(min_length=4, max_length=4)
    interview_topics: list[InterviewTopic] = Field(default_factory=list, max_length=3)

    @model_validator(mode="after")
    def consistent_status(self):
        if {row.dimension for row in self.dimensions} != {"fit", "contribution", "evidence", "readability"}:
            raise ValueError("质量报告必须包含四个不同维度")
        actions = {row.action for row in self.dimensions}
        expected = "revise" if "revise" in actions else "insufficient" if "need_input" in actions else "ready"
        if self.status != expected or actions == {"not_applicable"}:
            raise ValueError("质量结论与改进动作不一致")
        return self


class WritingReview(Review):
    quality: QualityReview


class GenerationInput(StrictModel):
    request_id: str = Field(pattern=r"^[A-Za-z0-9_-]{8,80}$")
    name: str = Field(default="", max_length=80)
    contact: str = Field(default="", max_length=300)
    target_role: str = Field(min_length=1, max_length=80)
    source_text: str = Field(default="", max_length=20000)
    jd: str = Field(default="", max_length=8000)
    allow_questions: bool = True
    send_materials: bool = False
    education: list[Education] = Field(default_factory=list, max_length=8)
    career_stage: Literal["unspecified", "entry", "experienced", "transition"] = "unspecified"
    has_career_gap: bool = False
    execution_mode: Literal["legacy", "langgraph", "supervisor"] = "langgraph"


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


class ResolveIssueInput(StrictModel):
    expected_revision: int = Field(ge=1)
    review_job_id: str = Field(min_length=1, max_length=80)
    issue_index: int = Field(ge=0)
    evidence_ids: list[str] = Field(min_length=1, max_length=20)
    explanation: str = Field(min_length=10, max_length=500)
    acknowledged: Literal[True]
