"""Versioned, immutable task budgets; persisted ledgers are never reset here.

All durations are milliseconds. Policy snapshots may reduce the release's hard
ceilings, but cannot widen them or silently fall back after validation fails.
"""

import math
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.providers import ProviderError

_STAGES = frozenset({"plan", "draft", "review", "revise", "supervise"})


class BudgetPolicy(BaseModel):
    model_config = ConfigDict(frozen=True, strict=True, extra="forbid")

    version: Literal["budget-v1"] = "budget-v1"
    max_calls: int = Field(default=8, ge=3, le=8)
    max_revisions: int = Field(default=2, ge=0, le=2)
    max_invalid_outputs: int = Field(default=2, ge=1, le=2)
    total_ms: int = Field(default=180000, ge=1000, le=180000)
    request_ms: int = Field(default=45000, ge=1000, le=45000)
    review_reserve_ms: int = Field(default=15000, ge=1000, le=15000)
    supervisor_ms: int = Field(default=20000, ge=1000, le=20000)
    supervisor_reserve_ms: int = Field(default=30000, ge=1000, le=30000)
    supervisor_start_before_ms: int = Field(default=140000, ge=1000, le=140000)
    max_context_chars: int = Field(default=64000, ge=1, le=64000)
    max_response_bytes: int = Field(default=262144, ge=1, le=262144)
    max_output_tokens: int = Field(default=8192, ge=1, le=8192)
    supervisor_output_tokens: int = Field(default=800, ge=1, le=800)
    question_limit: int = Field(default=3, ge=1, le=3)
    graph_recursion_limit: int = Field(default=48, ge=1, le=48)

    @model_validator(mode="after")
    def consistent(self):
        if (self.request_ms > self.total_ms
                or self.review_reserve_ms >= self.total_ms
                or self.supervisor_ms > self.request_ms
                or self.supervisor_reserve_ms < self.review_reserve_ms
                or self.supervisor_start_before_ms > self.total_ms - self.supervisor_reserve_ms
                or self.supervisor_output_tokens > self.max_output_tokens):
            raise ValueError("预算策略字段不一致")
        return self

    @staticmethod
    def _ledger(job: dict):
        try:
            calls, revisions = job["calls"], job["revisions"]
            elapsed = job["elapsed_ms"]
            invalid = job.get("invalid_outputs", {})
            if (type(calls) is not int or calls < 0
                    or type(revisions) is not int or revisions < 0
                    or type(elapsed) not in (int, float) or not math.isfinite(elapsed) or elapsed < 0
                    or not isinstance(invalid, dict)
                    or any(not isinstance(key, str) or type(count) is not int or count < 0
                           for key, count in invalid.items())):
                raise ValueError
        except (KeyError, TypeError, ValueError, OverflowError):
            raise ProviderError("任务预算记录无效，已有材料和候选已保留") from None
        return calls, revisions, elapsed, invalid

    def can_revise(self, job: dict) -> bool:
        calls, revisions, elapsed, _ = self._ledger(job)
        return (job.get("mode") == "generate" and revisions < self.max_revisions
                and calls <= self.max_calls - 2 and elapsed < self.total_ms)

    def can_supervise(self, job: dict) -> bool:
        calls, _, elapsed, _ = self._ledger(job)
        # Reserve the supervisor request, a revision, and its final review.
        return calls <= self.max_calls - 3 and elapsed < self.supervisor_start_before_ms

    def request_timeout_ms(self, stage: str, elapsed_ms: float) -> float:
        if (stage not in _STAGES or type(elapsed_ms) not in (int, float)
                or not math.isfinite(elapsed_ms) or elapsed_ms < 0):
            raise ProviderError("任务预算或阶段无效，已有候选保留")
        remaining = self.total_ms - elapsed_ms
        if remaining <= 0:
            raise ProviderError("任务预算已用尽，已有材料和候选已保留")
        if stage == "supervise":
            return min(self.supervisor_ms, max(1000, remaining - self.supervisor_reserve_ms))
        if stage in ("draft", "revise"):
            return min(self.request_ms, remaining, max(1000, remaining - self.review_reserve_ms))
        return min(self.request_ms, remaining)

    def validate_request(self, stage: str, job: dict) -> None:
        if stage not in _STAGES:
            raise ProviderError("任务预算阶段无效，已有材料和候选已保留")
        calls, revisions, elapsed, invalid = self._ledger(job)
        if calls >= self.max_calls or elapsed >= self.total_ms:
            raise ProviderError("任务预算已用尽，已有材料和候选已保留；请查看候选或新建任务")
        if stage in ("draft", "revise") and (
                calls >= self.max_calls - 1 or elapsed >= self.total_ms - self.review_reserve_ms):
            raise ProviderError("剩余预算需保留给审阅，不能继续生成未经审阅的新正文；已有候选保留")
        if stage == "supervise" and not self.can_supervise(job):
            raise ProviderError("主管剩余预算不足，需为修正与审阅预留调用和时间；已有候选保留")
        if invalid.get(f"{stage}:{revisions}", 0) >= self.max_invalid_outputs:
            raise ProviderError("这个阶段的结构重试已用尽，已有内容已保留")


DEFAULT_POLICY = BudgetPolicy()

# Pin every historical field explicitly: changing a future default must not
# rewrite the authorization or remaining budget of snapshotless old jobs.
LEGACY_POLICY = BudgetPolicy(
    version="budget-v1", max_calls=8, max_revisions=2, max_invalid_outputs=2,
    total_ms=180000, request_ms=45000, review_reserve_ms=15000,
    supervisor_ms=20000, supervisor_reserve_ms=30000,
    supervisor_start_before_ms=140000, max_context_chars=64000,
    max_response_bytes=262144, max_output_tokens=8192,
    supervisor_output_tokens=800, question_limit=3, graph_recursion_limit=48,
)


def budget_for_job(job: dict) -> BudgetPolicy:
    """Read a complete frozen snapshot, or the identical legacy defaults.

    A present but corrupt snapshot is an error, never a request to reset limits.
    Validation failures deliberately exclude stored payloads and Pydantic details.
    """
    if "budget_policy" not in job:
        return LEGACY_POLICY
    snapshot = job["budget_policy"]
    try:
        if not isinstance(snapshot, dict) or set(snapshot) != set(BudgetPolicy.model_fields):
            raise ValueError
        return BudgetPolicy.model_validate(snapshot)
    except (ValidationError, TypeError, ValueError):
        raise ProviderError("任务预算策略无效或版本不兼容，已有材料和候选已保留；请新建任务") from None
