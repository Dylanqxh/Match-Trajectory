import asyncio

import pytest
from test_workflow import DRAFT, PASS, PLAN, request, setup


def test_new_graph_uses_role_handlers_instead_of_legacy_stage_dispatch(tmp_path, monkeypatch):
    runner, jobs, _, _, model = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    async def forbidden(*_):
        raise AssertionError('new graph must not call legacy dispatcher')
    monkeypatch.setattr(runner, 'execute_step', forbidden)
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 3
    assert result['engine_version'] != 'm15-v1'
    assert [c[0] for c in model.calls] == ['plan', 'draft', 'review']


def test_old_graph_keeps_its_pinned_version(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, PASS])
    job = runner.submit(request())
    jobs.mutate(job['id'], lambda j, _: j.update(engine_version='m15-v1'))
    asyncio.run(runner.run_one())
    assert jobs.get(job['id'])['state'] == 'ready'
    assert jobs.get(job['id'])['engine_version'] == 'm15-v1'


def test_stage_result_does_not_change_business_route_until_committed(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN])
    job = runner.submit(request())
    claimed = jobs.claim_next()
    result = asyncio.run(runner.plan_stage(claimed, claimed['run_token']))
    stored = jobs.get(job['id'])
    assert stored['stage'] == 'plan' and stored['plan'] is None
    runner.commit_stage(claimed, claimed['run_token'], result)
    assert jobs.get(job['id'])['stage'] == 'draft'


def test_reference_date_uses_shanghai_day_across_utc_midnight(tmp_path):
    runner, jobs, _, _, _ = setup(tmp_path, [])
    job = runner.submit(request())
    jobs.mutate(job['id'], lambda j, _: j.update(created_at='2026-11-04T18:20:00+00:00'))
    context = runner._context(jobs.get(job['id']), 'plan')
    assert context['reference_date'] == '2026-11-05'
    assert context['reference_timezone'] == 'Asia/Shanghai'


@pytest.mark.parametrize(('source', 'claim'), [
    ('2024 年 1 月完成实验。', '2024-01完成实验。'),
    ('处理1,000条记录。', '处理1000条记录。'),
    ('耗时1.0秒。', '耗时1秒。'),
])
def test_equivalent_number_forms_are_supported_inside_cited_evidence(source, claim):
    from test_skill import make_draft

    from app.skill import build_evidence, validate_draft
    assert not validate_draft(make_draft(claim), build_evidence(source))


@pytest.mark.parametrize(('source', 'claim'), [('准确率10%。', '准确率100%。'), ('处理100条。', '处理100万条。')])
def test_numeric_normalization_keeps_units_and_magnitude(source, claim):
    from test_skill import make_draft

    from app.skill import build_evidence, validate_draft
    assert any(i.severity == 'blocking' for i in validate_draft(make_draft(claim), build_evidence(source)))


def test_numbers_from_another_evidence_cannot_support_the_claim():
    from test_skill import make_draft

    from app.generation_models import Evidence
    from app.skill import validate_draft
    evidence = [Evidence(id='e1', text='本人完成实验。', start=0, end=7),
                Evidence(id='e2', text='另一项目处理1000条。', start=7, end=20)]
    assert any(i.severity == 'blocking' for i in validate_draft(make_draft('本人处理1000条。'), evidence))


def test_fixed_education_collision_is_retried_before_candidate_commit(tmp_path):
    import json
    repaired = json.loads(json.dumps(DRAFT))
    repaired['sections'][0]['items'][0]['id'] = 'repaired-item'
    runner, jobs, _, _, _ = setup(tmp_path, [PLAN, DRAFT, repaired, PASS])
    job = runner.submit(request(education=[{'id': 'item1', 'school': '合成测试学院', 'degree': '本科', 'major': '计算机'}]))
    asyncio.run(runner.run_one())
    result = jobs.get(job['id'])
    assert result['state'] == 'ready' and result['calls'] == 4
    assert result['draft']['education'][0]['id'] == 'item1'
    assert result['draft']['sections'][0]['items'][0]['id'] == 'repaired-item'
    assert result['invalid_outputs']['draft:0'] == 1
