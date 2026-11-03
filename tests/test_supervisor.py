import asyncio
import json

import httpx
import pytest
from test_model_client import config
from test_workflow import DRAFT, PASS, PLAN, request, setup

from app.model_client import Completion, ModelClient
from app.providers import ProviderError


def two_issues():
    from tests_support import fixture_quality
    q = fixture_quality()
    for row in q['dimensions'][:2]:
        row.update(action='revise', score=1, reason='已有接口与测试依据，可突出个人贡献。')
    q['status'] = 'revise'
    return {**PASS, 'quality': q}


def tool_response(arguments=None, name='delegate_to_writer', reason='tool_calls'):
    return {'choices': [{'finish_reason': reason, 'message': {'content': None, 'tool_calls': [
        {'id': 'call-1', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(arguments or {
            'action': 'revise', 'issue_indices': [0, 1], 'rationale': '先突出贡献并压缩表达。'})}}
    ]}}], 'usage': {'total_tokens': 17}}


def test_native_delegate_validates_the_registered_tool_and_usage():
    seen = []
    def server(req):
        body = json.loads(req.content)
        seen.append(body)
        assert body['tools'][0]['function']['name'] == 'delegate_to_writer'
        assert body['tool_choice']['function']['name'] == 'delegate_to_writer'
        assert 'response_format' not in body
        return httpx.Response(200, json=tool_response())
    result = asyncio.run(ModelClient(transport=httpx.MockTransport(server)).delegate(config(), {'issues': []}))
    assert result.value.issue_indices == [0, 1] and result.usage['total_tokens'] == 17
    assert len(seen) == 1


@pytest.mark.parametrize('envelope', [
    tool_response(name='write_database'), tool_response(reason='length'),
    tool_response({'action': 'revise', 'issue_indices': [0], 'rationale': 'x', 'user_confirmed': True}),
    {'choices': [{'finish_reason': 'stop', 'message': {'content': 'private-provider-output'}}]},
])
def test_bad_tool_reply_never_executes_or_echoes_remote_values(envelope):
    with pytest.raises(ProviderError) as caught:
        asyncio.run(ModelClient(transport=httpx.MockTransport(lambda _: httpx.Response(200, json=envelope))).delegate(config(), {}))
    assert 'private-provider-output' not in str(caught.value)


class SupervisorModel:
    def __init__(self, inner, decision=None):
        self.inner, self.delegations = inner, []
        self.decision = decision or {'action': 'revise', 'issue_indices': [0], 'rationale': '先修改一项。'}

    async def complete(self, *args):
        return await self.inner.complete(*args)

    async def delegate(self, config, context):
        from app.supervisor import RepairDecision
        self.delegations.append(context)
        return Completion(RepairDecision.model_validate(self.decision), {'total_tokens': 11})


def enabled(tmp_path, outputs, decision=None):
    runner, jobs, store, registry, model = setup(tmp_path, outputs)
    registry.verify_tools(registry.current)
    runner.client = wrapped = SupervisorModel(model, decision)
    return runner, jobs, store, registry, model, wrapped


def test_supervisor_is_optional_and_unverified_models_are_rejected_before_generation(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [])
    with pytest.raises(ValueError, match='工具'):
        runner.submit(request(execution_mode='supervisor'))
    assert jobs.list() == [] and model.calls == []


def test_supervisor_delegates_only_selected_issues_and_counts_its_call(tmp_path):
    runner, jobs, _, _, model, wrapped = enabled(tmp_path, [PLAN, DRAFT, two_issues(), DRAFT, PASS])
    job = runner.submit(request(execution_mode='supervisor'))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 6
    assert result['review']['verdict'] == 'pass'
    assert len(wrapped.delegations) == 1
    assert len(model.calls[3][1]['issues_to_fix']) == 1
    assert 'plan' not in wrapped.delegations[0]
    assert 'me@example.com' not in json.dumps(wrapped.delegations)
    assert any(row['stage'] == 'supervise' for row in result['call_log'])


def test_missing_evidence_is_delivered_without_rewrite_or_supervisor(tmp_path):
    from tests_support import fixture_quality
    q = fixture_quality()
    q['dimensions'][0].update(action='need_input', score=0, evidence_ids=[], reason='缺少相关经历。')
    q['status'] = 'insufficient'
    runner, jobs, _, _, _, wrapped = enabled(tmp_path, [PLAN, DRAFT, {**PASS, 'quality': q}])
    job = runner.submit(request(execution_mode='supervisor'))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 3
    assert wrapped.delegations == []


def test_supervisor_cannot_target_unknown_issues(tmp_path):
    runner, jobs, _, _, _, wrapped = enabled(tmp_path, [PLAN, DRAFT, two_issues()], {
        'action': 'revise', 'issue_indices': [39], 'rationale': '越权索引'})
    job = runner.submit(request(execution_mode='supervisor'))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'failed' and result['calls'] == 5
    assert result['draft'] and result['stage'] == 'supervise'
    assert len(wrapped.delegations) == 2  # only one structure retry


def test_supervisor_does_not_spend_last_review_and_revision_calls(tmp_path):
    runner, jobs, _, _, _, wrapped = enabled(tmp_path, [two_issues(), DRAFT, PASS])
    job = runner.submit(request(execution_mode='supervisor'))
    jobs.mutate(job['id'], lambda j, _: j.update(stage='review', draft=DRAFT, calls=5, plan=PLAN))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 8
    assert wrapped.delegations == []


def test_supervisor_revision_cannot_rewrite_an_unselected_item(tmp_path):
    draft = json.loads(json.dumps(DRAFT))
    draft['sections'][0]['items'].append({'id': 'untouched', 'text': '编写测试记录。', 'fact_ids': ['e1']})
    changed = json.loads(json.dumps(draft))
    changed['sections'][0]['items'][1]['text'] = '使用 Java 编写测试记录。'
    report = two_issues()
    for row in report['quality']['dimensions'][:2]:
        row['item_ids'] = ['item1']
    runner, jobs, _, _, _, _ = enabled(tmp_path, [PLAN, draft, report, changed, changed])
    job = runner.submit(request(execution_mode='supervisor'))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'failed'
    assert result['draft']['sections'][0]['items'][1]['text'] == '编写测试记录。'


def test_capability_probe_is_explicit_and_bound_to_model_revision(tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app
    from app.supervisor import RepairDecision

    class Probe:
        async def delegate(self, config, context):
            assert 'synthetic' in json.dumps(context)
            return Completion(RepairDecision(action='revise', issue_indices=[0], rationale='合成测试'), {'total_tokens': 9})

    app = create_app(tmp_path, model_client=Probe())
    registry = app.state.workflow.registry
    first = registry.register(config())
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.post('/api/model-settings/test-tools').status_code == 401
    client.get('/api/session')
    result = client.post('/api/model-settings/test-tools')
    assert result.status_code == 200 and result.json()['calls'] == 1
    assert registry.supports_tools(first)
    second = registry.register(config())
    assert not registry.supports_tools(second)


def test_resumed_supervisor_with_insufficient_budget_keeps_candidate_without_call(tmp_path):
    runner, jobs, _, _, _, wrapped = enabled(tmp_path, [])
    job = runner.submit(request(execution_mode='supervisor'))
    jobs.mutate(job['id'], lambda j, _: j.update(stage='supervise', draft=DRAFT, calls=6,
                                                plan=PLAN, issues=[]))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 6
    assert wrapped.delegations == [] and result['draft']


def test_revision_structure_retry_does_not_spend_reserved_review_call(tmp_path):
    from app.model_client import ModelOutputError
    runner, jobs, _, _, _, wrapped = enabled(tmp_path, [two_issues(), ModelOutputError('invalid structure'), DRAFT])
    job = runner.submit(request(execution_mode='supervisor'))
    jobs.mutate(job['id'], lambda j, _: j.update(stage='review', calls=4, plan=PLAN, draft=DRAFT))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'failed' and result['calls'] == 7
    assert len(wrapped.delegations) == 1


def test_probe_releases_queue_even_when_submission_woke_worker_while_locked(tmp_path):
    from test_workflow import ScriptedModel

    from app.main import create_app
    from app.supervisor import RepairDecision

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Probe(ScriptedModel):
            async def delegate(self, config, context):
                entered.set()
                await release.wait()
                return Completion(RepairDecision(action='revise', issue_indices=[0], rationale='测试'), {})
        app = create_app(tmp_path, model_client=Probe([PLAN, DRAFT, PASS]))
        runner = app.state.workflow
        runner.registry.register(config())
        await runner.start()
        try:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1') as client:
                await client.get('/api/session')
                probing = asyncio.create_task(client.post('/api/model-settings/test-tools'))
                await entered.wait()
                job = runner.submit(request())
                await asyncio.sleep(0.05)
                release.set()
                assert (await probing).status_code == 200
                for _ in range(100):
                    if runner.jobs.get(job['id'])['state'] == 'ready':
                        break
                    await asyncio.sleep(0.01)
                assert runner.jobs.get(job['id'])['state'] == 'ready'
        finally:
            await runner.close()
    asyncio.run(scenario())


def test_local_revision_cannot_move_contributions_between_experiences():
    from app.generation_models import Draft
    from app.supervisor import validate_revision_scope

    before = json.loads(json.dumps(DRAFT))
    before['sections'].append({'id': 'other-project', 'title': '另一段项目经历', 'items': [
        {'id': 'untouched', 'text': '编写测试记录。', 'fact_ids': ['e1']}]})
    after = json.loads(json.dumps(before))
    after['sections'][0]['items'], after['sections'][1]['items'] = after['sections'][1]['items'], after['sections'][0]['items']
    job = {'draft': before, 'issues': [{'item_id': 'item1'}], 'repair_decision': {'issue_indices': [0]}}
    with pytest.raises(ProviderError):
        validate_revision_scope(job, Draft.model_validate(after))


def test_need_input_semantics_override_rewrite_words_in_the_reason():
    from app.generation_models import QualityReview
    from app.supervisor import RepairDecision, eligible_issues, validate_decision
    from app.writing_quality import quality_issues

    report = two_issues()['quality']
    report['dimensions'][0].update(action='need_input', evidence_ids=[], reason='缺少另一项目交付信息，无法合并成完整贡献。')
    job = {'issues': [i.model_dump() for i in quality_issues(QualityReview.model_validate(report))]}
    assert eligible_issues(job) == [1]
    with pytest.raises(ProviderError):
        validate_decision(job, RepairDecision(action='revise', issue_indices=[0], rationale='不能靠合并补事实'))
