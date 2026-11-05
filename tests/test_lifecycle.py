import asyncio
import json
import os
import sqlite3
import subprocess

import pytest
from fastapi.testclient import TestClient
from test_workflow import DRAFT, PASS, PLAN, request, setup

from app.main import create_app


def test_delete_resume_clears_versions_jobs_exports_and_checkpoint(tmp_path):
    from app.lifecycle import Lifecycle
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job['id'])
    exports = tmp_path / 'exports'
    exports.mkdir()
    artifact = exports / f'resume-{record.id[:8]}-r1-confirmed-abc.pdf'
    artifact.write_bytes(b'test')
    artifact.with_suffix('.pdf.json').write_text(json.dumps({'resume_id': record.id}))
    other = exports / 'unrelated.pdf'
    other.write_bytes(b'keep')
    service = Lifecycle(store, jobs, tmp_path)
    result = service.delete_resume(record.id, 1)
    assert result['deleted'] and not result['cleanup_pending']
    assert store.list() == [] and jobs.list() == []
    assert not artifact.exists() and other.exists()
    assert jobs.get(job['id'])['input'] == {}
    with sqlite3.connect(tmp_path / 'workflow-checkpoints.sqlite3') as db:
        assert db.execute('select count(*) from checkpoints where thread_id=?', (job['id'],)).fetchone()[0] == 0
    with sqlite3.connect(tmp_path / 'resumes.sqlite3') as db:
        for name in ('resume_versions', 'resume_ai_versions'):
            assert db.execute(f'select count(*) from {name}').fetchone()[0] == 0
    assert service.delete_resume(record.id, 1)['deleted']


def test_deleting_adopted_task_preserves_source_until_resume_is_deleted(tmp_path):
    from app.lifecycle import Lifecycle
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job['id'])
    service = Lifecycle(store, jobs, tmp_path)
    assert service.delete_job(job['id'])['retained_for_resume']
    assert jobs.list() == [] and jobs.get(job['id'])['evidence']
    retained = jobs.get(job['id'])
    assert retained['draft'] is None and retained['review'] is None
    assert 'contact' not in retained['input'] and 'source_text' not in retained['input']
    assert runner.takeover(record.id, 1).ai.manual_takeover
    review = runner.recheck(record.id, 1, 'review-after-delete')
    asyncio.run(runner.run_one())
    assert jobs.get(review['id'])['review']['verdict'] == 'pass'
    service.delete_resume(record.id, 1)
    assert jobs.get(job['id'])['evidence'] == []


def test_delete_routes_require_session_and_expected_revision(tmp_path):
    app = create_app(tmp_path)
    client = TestClient(app, base_url='http://127.0.0.1')
    assert client.delete('/api/resumes/' + 'a'*32).status_code == 401
    client.get('/api/session')
    row = client.post('/api/resumes', json={'name':'测试', 'target_role':'算法'}).json()
    assert client.request('DELETE', '/api/resumes/'+row['id'], json={'expected_revision':99}).status_code == 409
    assert client.get('/api/resumes/'+row['id']).status_code == 200
    assert client.request('DELETE', '/api/resumes/'+row['id'], json={'expected_revision':1}).status_code == 200
    assert client.get('/api/resumes/'+row['id']).status_code == 404


def test_deleted_job_cannot_be_read_or_adopted_via_api(tmp_path):
    app = create_app(tmp_path)
    runner = app.state.workflow
    job = runner.submit(request(source_text=''))
    client = TestClient(app, base_url='http://127.0.0.1')
    client.get('/api/session')
    assert client.delete('/api/generation-jobs/'+job['id']).status_code == 200
    assert client.get('/api/generation-jobs/'+job['id']).status_code == 404
    assert client.post('/api/generation-jobs/'+job['id']+'/adopt',json={}).status_code == 404


def test_failed_file_cleanup_is_durable_and_retried(tmp_path, monkeypatch):
    from app.lifecycle import Lifecycle
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job['id'])
    service = Lifecycle(store, jobs, tmp_path)
    original = service._cleanup
    def failed(_):
        raise PermissionError('file temporarily locked')
    monkeypatch.setattr(service, '_cleanup', failed)
    assert service.delete_resume(record.id, 1)['cleanup_pending']
    assert store.list() == []
    monkeypatch.setattr(service, '_cleanup', original)
    assert not Lifecycle(store, jobs, tmp_path).retry_cleanup()


def test_delete_during_model_request_discards_late_output_and_worker_survives(tmp_path):
    from app.lifecycle import Lifecycle
    from app.model_client import Completion

    async def scenario():
        runner, jobs, store, _, _ = setup(tmp_path, [])
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            async def complete(self, config, stage, context, schema):
                entered.set()
                await release.wait()
                return Completion(schema.model_validate(PLAN), {})
        runner.client = Slow()
        job = runner.submit(request())
        running = asyncio.create_task(runner.run_one())
        await entered.wait()
        Lifecycle(store, jobs, tmp_path).delete_job(job['id'])
        release.set()
        await running
        assert jobs.list() == [] and store.list() == []
        assert jobs.get(job['id'])['input'] == {}
    asyncio.run(scenario())


def test_deletion_api_waits_for_cancelled_graph_before_removing_checkpoint(tmp_path):
    import httpx

    from app.model_client import Completion
    from app.providers import ProviderConfig

    async def scenario():
        entered, release = asyncio.Event(), asyncio.Event()
        class Slow:
            async def complete(self, config, stage, context, schema):
                entered.set()
                try:
                    await release.wait()
                except asyncio.CancelledError:
                    await release.wait()
                return Completion(schema.model_validate(PLAN), {})
        app = create_app(tmp_path, model_client=Slow())
        runner = app.state.workflow
        runner.registry.register(ProviderConfig(provider='custom', model='fixture', base_url='http://127.0.0.1:12345', api_key='test'))
        job = runner.submit(request())
        running = asyncio.create_task(runner.run_one())
        await entered.wait()
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://127.0.0.1') as client:
            await client.get('/api/session')
            deleting = asyncio.create_task(client.delete('/api/generation-jobs/'+job['id']))
            await asyncio.sleep(0.02)
            release.set()
            assert (await deleting).status_code == 200
            await running
            assert client.cookies
            assert (await client.get('/api/generation-jobs/'+job['id'])).status_code == 404
        with sqlite3.connect(tmp_path / 'workflow-checkpoints.sqlite3') as db:
            assert db.execute('select count(*) from checkpoints where thread_id=?', (job['id'],)).fetchone()[0] == 0
    asyncio.run(scenario())


@pytest.mark.skipif(os.name != 'nt', reason='Windows junction boundary')
def test_export_junction_cannot_delete_files_outside_data_root(tmp_path):
    from app.lifecycle import Lifecycle
    workspace, outside = tmp_path / 'workspace', tmp_path / 'external'
    outside.mkdir()
    runner, jobs, store, _, _ = setup(workspace, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    asyncio.run(runner.run_one())
    record = runner.adopt(job['id'])
    artifact = outside / f'resume-{record.id[:8]}-r1-confirmed-abc.pdf'
    artifact.write_bytes(b'keep outside')
    artifact.with_suffix('.pdf.json').write_text(json.dumps({'resume_id': record.id}))
    link = workspace / 'exports'
    result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(outside)], check=False, capture_output=True)
    if result.returncode:
        pytest.skip('junction creation unavailable')
    try:
        result = Lifecycle(store, jobs, workspace).delete_resume(record.id, 1)
        assert result['cleanup_pending'] and artifact.exists()
    finally:
        os.rmdir(link)


def test_deleting_one_resume_preserves_other_resume_history_and_material(tmp_path):
    from app.lifecycle import Lifecycle
    runner, jobs, store, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS, PLAN, DRAFT, PASS])
    first_job = runner.submit(request())
    asyncio.run(runner.run_one())
    first = runner.adopt(first_job['id'])
    second_job = runner.submit(request().model_copy(update={'request_id': 'second-request'}))
    asyncio.run(runner.run_one())
    second = runner.adopt(second_job['id'])
    Lifecycle(store, jobs, tmp_path).delete_resume(first.id, 1)
    assert [row['id'] for row in store.list()] == [second.id]
    assert len(store.history(second.id)) == 1
    assert store.get(second.id).ai.review_status == 'passed'
    assert [row['id'] for row in jobs.list()] == [second_job['id']]
    assert jobs.get(second_job['id'])['evidence']
