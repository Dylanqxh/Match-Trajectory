"""Stage results and the single, pure business transition policy."""
from dataclasses import dataclass, field
from typing import Any

from pydantic import ValidationError

from app.budget import budget_for_job
from app.generation_models import Draft, DraftEducation, ReviewDraft
from app.jobs import fingerprint
from app.skill import validate_quality
from app.supervisor import should_supervise
from app.writing_quality import editorial_quality, quality_issues


def phase_key(job):
    digest = fingerprint({key: job.get(key) for key in ('input', 'evidence', 'plan', 'draft', 'issues', 'review', 'provider', 'budget_policy')})
    return f"{job['stage']}:{job['revisions']}:{job.get('skill', {}).get('version', '')}:{digest}"


def prepare_draft(job, output):
    from app.model_client import ModelOutputError, safe_validation_fields

    payload = output.model_dump()
    if job['input'].get('education'):
        payload['education'] = [DraftEducation(**row, fact_ids=[e['id'] for e in job['evidence']
            if e['id'].startswith(f"profile-{row['id']}-")]).model_dump() for row in job['input']['education']]
    try:
        return Draft.model_validate(payload)
    except ValidationError as exc:
        raise ModelOutputError('合并固定教育信息后结构不符合约定，请保留教育字段并使用不同的段落标识',
                               diagnostic={'category': 'schema', 'fields': safe_validation_fields(exc, Draft)}) from None


@dataclass(frozen=True)
class StageResult:
    stage: str
    key: str
    kind: str
    value: Any = None


@dataclass(frozen=True)
class Transition:
    target: str
    updates: dict = field(default_factory=dict)


def transition(job, result):
    policy = budget_for_job(job)
    if result.kind == 'retry':
        return Transition(result.stage)
    if result.kind == 'stop':
        return Transition('done', {'stop_reason': '剩余预算不足以安排主管、修正和审阅，已保留当前候选与问题'})
    if result.kind == 'program_issues':
        return Transition('revise' if policy.can_revise(job) else 'done', {'issues': result.value, 'review': None})
    output = result.value
    if result.stage == 'plan':
        return Transition('wait' if output.decision == 'ask' and job['input']['allow_questions'] else 'draft', {'plan': output.model_dump()})
    if result.stage in ('draft', 'revise'):
        payload = prepare_draft(job, output).model_dump()
        return Transition('review', {'draft': payload, 'review': None, 'issues': [], 'repair_decision': None,
                                    'revisions': job['revisions'] + (result.stage == 'revise')})
    if result.stage == 'supervise':
        return Transition('done' if output.action == 'deliver' else 'revise', {'repair_decision': output.model_dump()})
    if result.stage == 'review':
        candidate_type = ReviewDraft if job['mode'] == 'recheck' else Draft
        warnings = validate_quality(candidate_type.model_validate(job['draft']))
        report = editorial_quality(output.quality, warnings, job['evidence'])
        review = output.model_dump()
        if report:
            review['quality'] = report.model_dump()
        issues = [i.model_dump() for i in [*output.issues, *warnings, *quality_issues(report)]]
        updates = {'review': review, 'issues': issues}
        editorial_fix = (report and report.status == 'revise') or any(i.repair_action == 'revise' for i in warnings)
        if (output.verdict == 'pass' and not editorial_fix) or not policy.can_revise(job):
            return Transition('done', updates)
        proposed = {**job, **updates}
        return Transition('supervise' if should_supervise(proposed) else 'revise', updates)
    raise ValueError('Unknown business stage')


ALLOWED = {
    'plan': ('plan', 'draft', 'wait'),
    'draft': ('draft', 'review'),
    'review': ('review', 'revise', 'supervise', 'done'),
    'revise': ('revise', 'review'),
    'supervise': ('supervise', 'revise', 'done'),
}
