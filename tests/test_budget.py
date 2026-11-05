import pytest
from pydantic import ValidationError

from app.budget import DEFAULT_POLICY, BudgetPolicy, budget_for_job
from app.providers import ProviderError


def job(**changes):
    return {"mode": "generate", "calls": 0, "revisions": 0, "elapsed_ms": 0,
            "invalid_outputs": {}} | changes


def test_legacy_budget_preserves_consumed_counts_and_blocks_exhaustion():
    current = job(calls=8, elapsed_ms=1234)
    before = dict(current)
    policy = budget_for_job(current)
    with pytest.raises(ProviderError, match="预算"):
        policy.validate_request("review", current)
    assert current == before
    with pytest.raises(ValidationError):
        policy.max_calls = 9


def test_legacy_snapshot_does_not_follow_changed_new_task_defaults(monkeypatch):
    import app.budget as budgets

    monkeypatch.setattr(budgets, "DEFAULT_POLICY", BudgetPolicy(max_calls=5))
    legacy = budgets.budget_for_job(job(calls=6))
    legacy.validate_request("draft", job(calls=6))
    assert legacy.can_supervise(job(calls=5))


@pytest.mark.parametrize("changes,stage,reason", [
    ({"calls": 7}, "draft", "审阅"),
    ({"elapsed_ms": 165000}, "revise", "审阅"),
    ({"elapsed_ms": 180000}, "review", "预算"),
    ({"invalid_outputs": {"review:0": 2}}, "review", "结构重试"),
    ({"calls": 6}, "supervise", "预算"),
    ({"elapsed_ms": 140000}, "supervise", "预算"),
])
def test_request_stops_at_each_budget_boundary(changes, stage, reason):
    with pytest.raises(ProviderError, match=reason):
        DEFAULT_POLICY.validate_request(stage, job(**changes))


def test_last_review_and_last_safe_draft_are_allowed():
    DEFAULT_POLICY.validate_request("review", job(calls=7, elapsed_ms=179999))
    DEFAULT_POLICY.validate_request("draft", job(calls=6, elapsed_ms=164999))


def test_supervisor_schema_retry_cannot_spend_revision_and_review_calls():
    DEFAULT_POLICY.validate_request("supervise", job(calls=5,
        invalid_outputs={"supervise:0": 1}))
    with pytest.raises(ProviderError, match="预算"):
        DEFAULT_POLICY.validate_request("supervise", job(calls=6,
            invalid_outputs={"supervise:0": 1}))


@pytest.mark.parametrize("changes,revise,supervise", [
    ({"calls": 5, "elapsed_ms": 139999}, True, True),
    ({"calls": 6}, True, False),
    ({"calls": 7}, False, False),
    ({"revisions": 2}, False, True),
    ({"elapsed_ms": 140000}, True, False),
    ({"elapsed_ms": 180000}, False, False),
    ({"mode": "recheck"}, False, True),
])
def test_routing_budget_uses_persisted_ledger(changes, revise, supervise):
    current = job(**changes)
    assert DEFAULT_POLICY.can_revise(current) is revise
    assert DEFAULT_POLICY.can_supervise(current) is supervise


@pytest.mark.parametrize("stage,elapsed,want", [
    ("plan", 0, 45000), ("review", 170000, 10000),
    ("draft", 150000, 15000), ("revise", 164999, 1000),
    ("supervise", 0, 20000), ("supervise", 139000, 11000),
])
def test_timeout_preserves_stage_reserves(stage, elapsed, want):
    assert DEFAULT_POLICY.request_timeout_ms(stage, elapsed) == want


def test_smaller_validated_snapshot_drives_all_derived_limits():
    policy = BudgetPolicy(max_calls=5, max_revisions=1, total_ms=60000,
        request_ms=10000, review_reserve_ms=5000, supervisor_ms=6000,
        supervisor_reserve_ms=10000, supervisor_start_before_ms=40000)
    snapshot = policy.model_dump()
    current = job(calls=2, elapsed_ms=39999, budget_policy=snapshot)
    frozen = budget_for_job(current)
    snapshot["max_calls"] = 8
    assert frozen.can_supervise(current)
    assert not frozen.can_supervise(job(calls=3))
    assert frozen.can_revise(job(calls=3))
    assert not frozen.can_revise(job(calls=4))
    assert frozen.request_timeout_ms("draft", 50000) == 5000
    assert frozen.request_timeout_ms("supervise", 46000) == 4000
    with pytest.raises(ProviderError, match="审阅"):
        frozen.validate_request("draft", job(calls=4))


@pytest.mark.parametrize("changes", [
    {"version": "future-secret"}, {"max_calls": 9}, {"max_calls": 0},
    {"max_calls": "8"}, {"max_calls": True}, {"total_ms": 180001},
    {"review_reserve_ms": 180000}, {"supervisor_reserve_ms": 1},
    {"supervisor_start_before_ms": 160000}, {"supervisor_ms": 46000},
    {"max_context_chars": 64001}, {"max_response_bytes": 262145},
    {"max_output_tokens": 8193}, {"supervisor_output_tokens": 8193},
    {"question_limit": 4}, {"graph_recursion_limit": 49},
    {"untrusted-secret": 1},
])
def test_invalid_snapshot_is_rejected_without_echoing_payload(changes):
    snapshot = DEFAULT_POLICY.model_dump() | changes
    with pytest.raises(ProviderError, match="预算策略") as error:
        budget_for_job(job(budget_policy=snapshot))
    assert "secret" not in str(error.value)


@pytest.mark.parametrize("snapshot", [None, {}, {"version": "budget-v1"}, "secret"])
def test_only_missing_snapshot_uses_legacy_defaults(snapshot):
    with pytest.raises(ProviderError, match="预算策略"):
        budget_for_job(job(budget_policy=snapshot))


@pytest.mark.parametrize("changes", [{"calls": -1}, {"calls": "0"},
    {"elapsed_ms": float("nan")}, {"revisions": -1},
    {"invalid_outputs": {"plan:0": -1}}])
def test_invalid_ledger_cannot_bypass_request_limits(changes):
    with pytest.raises(ProviderError, match="预算"):
        DEFAULT_POLICY.validate_request("plan", job(**changes))


def test_unknown_stage_is_rejected_safely():
    with pytest.raises(ProviderError):
        DEFAULT_POLICY.validate_request("arbitrary-secret", job())
