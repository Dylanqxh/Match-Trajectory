import asyncio
import sqlite3

import pytest
from test_workflow import DRAFT, PASS, PLAN, request, setup

from app.providers import ProviderError


@pytest.mark.parametrize('engine', ['legacy', 'langgraph'])
def test_engines_deliver_same_reviewed_candidate_without_extra_calls(tmp_path, engine):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request(execution_mode=engine))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready'
    assert result['review']['verdict'] == 'pass'
    assert result['calls'] == 3
    assert runner.adopt(job['id']).ai.review_status == 'passed'
    assert [c[0] for c in model.calls] == ['plan', 'draft', 'review']
    if engine == 'langgraph':
        with sqlite3.connect(tmp_path / 'workflow-checkpoints.sqlite3') as db:
            rows = db.execute('select checkpoint from checkpoints').fetchall()
        assert rows
        data = b''.join(bytes(row[0]) for row in rows)
        assert b'private-key-not-on-disk' not in data
        assert b'me@example.com' not in data
        assert '课程预约'.encode() not in data
        assert len(result['step_receipts']) == 3


def test_pre_upgrade_job_without_engine_still_finishes(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    def old(value, _):
        value.pop('engine', None)
        value.pop('engine_version', None)
    jobs.mutate(job['id'], old)
    asyncio.run(runner.run_one())
    assert jobs.get(job['id'])['state'] == 'ready'


def test_graph_wait_survives_new_runner_and_duplicate_answer(tmp_path):
    ask = {**PLAN, 'decision': 'ask', 'questions': [{'id': 'q1', 'text': '交付了什么？'}]}
    runner, jobs, store, registry, model = setup(tmp_path, [ask, DRAFT, PASS])
    job = runner.submit(request(execution_mode='langgraph'))
    asyncio.run(runner.run_one())
    waiting = jobs.get(job['id'])
    assert waiting['state'] == 'waiting_input' and waiting['calls'] == 1
    from app.workflow import Workflow
    restarted = Workflow(store, jobs, registry, model)
    payload = {'question_group': waiting['question_group'], 'skip': True, 'answers': {}}
    restarted.answer(job['id'], payload)
    restarted.answer(job['id'], payload)
    asyncio.run(restarted.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 3
    assert [c[0] for c in model.calls] == ['plan', 'draft', 'review']


def test_saved_step_is_not_repeated_when_checkpoint_write_failed(tmp_path, monkeypatch):
    from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
    original = AsyncSqliteSaver.aput
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request(execution_mode='langgraph'))
    failed = False
    async def fail_once(self, *args, **kwargs):
        nonlocal failed
        if not failed and jobs.get(job['id'])['calls'] == 1:
            failed = True
            raise OSError('simulated disk write failure')
        return await original(self, *args, **kwargs)
    monkeypatch.setattr(AsyncSqliteSaver, 'aput', fail_once)
    asyncio.run(runner.run_one())
    assert failed and jobs.get(job['id'])['state'] == 'failed'
    runner.resume(job['id'])
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 3
    assert [c[0] for c in model.calls] == ['plan', 'draft', 'review']


def test_unknown_graph_version_cannot_silently_switch_engine(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request(execution_mode='langgraph'))
    jobs.mutate(job['id'], lambda j, _: j.update(engine_version='future-version'))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'failed'
    assert '版本' in result['error']
    assert model.calls == []


def test_graph_provider_failure_continues_only_failed_step(tmp_path):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, ProviderError('限流'), DRAFT, PASS])
    job = runner.submit(request(execution_mode='langgraph'))
    asyncio.run(runner.run_one())
    assert jobs.get(job['id'])['calls'] == 2
    runner.resume(job['id'])
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 4
    assert [c[0] for c in model.calls] == ['plan', 'draft', 'draft', 'review']


def test_retry_of_pre_upgrade_request_returns_existing_job_without_changing_engine(tmp_path):
    from app.skill import build_evidence, load_skill
    runner, jobs, _, registry, model = setup(tmp_path, [])
    inputs = request().model_dump(exclude={'execution_mode'})
    old = jobs.create(inputs, registry.current, registry.describe(registry.get(registry.current)),
                      load_skill(inputs['target_role']), [e.model_dump() for e in build_evidence(inputs['source_text'])])
    repeated = runner.submit(request())
    assert repeated['id'] == old['id'] and repeated['engine'] == 'legacy'
    assert model.calls == []


def test_review_commit_and_next_stage_are_atomic_across_crash(tmp_path, monkeypatch):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS, PASS])
    job = runner.submit(request(execution_mode='langgraph'))
    original = jobs.mutate
    crashed = False
    def crash_after_review(job_id, callback):
        nonlocal crashed
        result = original(job_id, callback)
        if result['review'] and not crashed:
            crashed = True
            raise OSError('simulated crash immediately after review commit')
        return result
    monkeypatch.setattr(jobs, 'mutate', crash_after_review)
    asyncio.run(runner.run_one())
    if jobs.get(job['id'])['state'] != 'ready':
        runner.resume(job['id'])
        asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert crashed and result['state'] == 'ready'
    assert result['calls'] == 3
    assert [c[0] for c in model.calls] == ['plan', 'draft', 'review']


def test_unexpected_exception_does_not_persist_raw_provider_or_material_text_in_checkpoint(tmp_path):
    marker = 'private-raw-response-must-not-be-in-checkpoint'
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, RuntimeError(marker)])
    job = runner.submit(request(execution_mode='langgraph'))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'failed'
    assert marker not in result['error']
    assert marker.encode() not in (tmp_path / 'workflow-checkpoints.sqlite3').read_bytes()
