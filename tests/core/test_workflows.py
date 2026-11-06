"""V11 contracts. Synthetic data; no live model or cloud performance claims."""
import asyncio
import copy
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

import httpx
import pytest

from core.app import DEFAULTS, create_app
from core.store import Store, StoreUnavailable
from core.workflows import (WorkflowService, Principal, snapshot, fingerprint,
                            Conflict, run_node, MAX_ATTEMPTS, LEASE_SECONDS)
from unified.tools import REQUIRED_PARAMS, execute
from jinshu import tools

EDITOR = Principal('test-owner', 'alice', 'editor')
REVIEWER = Principal('review-owner', 'bob', 'reviewer')
STRANGER = Principal('other-owner', 'eve', 'editor')


@pytest.fixture
def service(tmp_path):
    return WorkflowService(Store({'JINSHU_STORE': 'sqlite', 'JINSHU_DATA_DIR': str(tmp_path)}))


def example(workflow='wealth_review'):
    return snapshot(workflow, DEFAULTS['wealth_benchmark' if workflow == 'wealth_review' else workflow], None, True)


async def finish(svc, row, person=EDITOR):
    for _ in range(8):
        if row['status'] in ('needs_review', 'blocked', 'approved', 'rejected', 'attention'):
            break
        row = await svc.advance(row['id'], person, row['revision'])
    return row


@pytest.mark.parametrize('name', list(REQUIRED_PARAMS)+['wealth_review'])
async def test_nine_workflows_execute_actual_tools(service, name):
    row = await service.create(EDITOR, 'workflow-'+name, example(name))
    done = await finish(service, row)
    assert done['status'] == 'needs_review'
    assert done['nodes']['report']['result']['business_action_executed'] is False
    assert done['nodes']['report']['result']['synthetic'] is True
    assert all(n['attempts'] == 1 for n in done['nodes'].values())


async def test_same_request_same_payload_deduplicated_across_instances(service):
    other = WorkflowService(Store(dict(service.store.env)))
    payload = example()
    rows = await asyncio.gather(*(s.create(EDITOR, 'repeated-key', payload) for s in [service, other]*5))
    assert len({r['id'] for r in rows}) == 1
    assert len(await service.list(EDITOR)) == 1
    changed = copy.deepcopy(payload); changed['values']['product'] = 'DIFFERENT'
    with pytest.raises(Conflict):
        await service.create(EDITOR, 'repeated-key', changed)
    assert (await service.create(STRANGER, 'repeated-key', payload))['id'] != rows[0]['id']


async def test_only_server_results_after_independent_review_export(service):
    row = await finish(service, await service.create(EDITOR, 'review-test', example()))
    with pytest.raises(Conflict):
        await service.export(row['id'], EDITOR, 1)
    with pytest.raises(PermissionError):
        await service.review(row['id'], Principal(EDITOR.owner, 'alice', 'reviewer'), 1, 'approve', '自己审核')
    with pytest.raises(PermissionError):
        await service.read(row['id'], STRANGER)
    reviewed = await service.review(row['id'], REVIEWER, 1, 'approve', '已核对字段、口径和异常')
    raw, kind = await service.export(row['id'], EDITOR, 1)
    artifact = json.loads(raw)
    assert kind == 'application/json' and artifact['approval']['reviewer'] == 'bob'
    assert artifact['export_scope'] == 'server_held_reviewed_draft'
    payload = copy.deepcopy(row['payload']); payload['sources']['weekly_raw.csv'][0]['名称'] = '修订产品'
    edited = await service.edit(row['id'], EDITOR, 1, payload)
    assert edited['approval'] is None and edited['revision'] == 2
    assert edited['nodes']['weekly_report']['status'] == 'pending'
    assert edited['nodes']['wealth_benchmark']['status'] == 'succeeded'
    assert edited['nodes']['wealth_benchmark']['reused']
    with pytest.raises(Conflict):
        await service.export(row['id'], EDITOR, 1)
    new = await finish(service, edited)
    assert new['status'] == 'needs_review' and new['nodes']['wealth_benchmark']['attempts'] == 1
    assert new['nodes']['weekly_report']['result']['result']['rows'][0]['名称'] == '修订产品'


async def test_partial_branch_failure_preserves_success(service):
    p = example(); p['sources']['nav.csv'] = p['sources']['nav.csv'][:1]
    row = await finish(service, await service.create(EDITOR, 'partial-failure', p))
    assert row['status'] == 'attention'
    assert row['nodes']['weekly_report']['status'] == 'succeeded'
    assert row['nodes']['wealth_benchmark']['status'] == 'failed'
    assert row['nodes']['report']['result'] is None
    fixed = example()
    revised = await service.edit(row['id'], EDITOR, 1, fixed)
    assert revised['nodes']['weekly_report']['reused']
    done = await finish(service, revised)
    assert done['status'] == 'needs_review'
    assert done['nodes']['weekly_report']['attempts'] == 1


async def test_hard_validation_blocks_approval_and_export(service):
    p = example('statements')
    p['sources']['statements.csv'][1]['assets'] = '999999'
    row = await finish(service, await service.create(EDITOR, 'hard-invalid', p))
    assert row['status'] == 'blocked' and row['quality']['label'] == 'REWRITE'
    assert row['nodes']['report']['result'] is None
    with pytest.raises((PermissionError, Conflict)):
        await service.review(row['id'], REVIEWER, 1, 'approve', '不能覆盖硬校验')
    with pytest.raises(Conflict):
        await service.export(row['id'], EDITOR, 1)


async def test_missing_weekly_rate_is_review_not_fabricated_zero(service):
    p = example('weekly_report');p['sources']['weekly_raw.csv'][0]['区间收益率'] = ''
    row = await finish(service, await service.create(EDITOR, 'missing-rate', p))
    assert row['quality']['label'] == 'REVIEW'
    assert row['nodes']['weekly_report']['result']['result']['rows'][0]['区间收益率'] is None


async def test_failed_step_has_bounded_attempts(service):
    p = example('wealth_benchmark');p['sources']['nav.csv'] = p['sources']['nav.csv'][:1]
    row = await finish(service, await service.create(EDITOR, 'retry-budget', p))
    for _ in range(5):
        row = await service.advance(row['id'], EDITOR, 1)
    assert row['nodes']['wealth_benchmark']['attempts'] == MAX_ATTEMPTS
    assert row['status'] == 'attention'


async def test_running_batch_cannot_be_double_claimed(service):
    row = await service.create(EDITOR, 'lease-race', example())
    await service.store.mutate(lambda s: s['workflow_runs'][row['id']].update(lease={'id': 'occupied', 'until': time.time()+60}, status='running'))
    with pytest.raises(Conflict):
        await WorkflowService(Store(dict(service.store.env))).advance(row['id'], EDITOR, 1)


async def test_edit_fences_off_late_results(service):
    entered = threading.Event(); release = threading.Event()
    def delayed(name, payload, completed):
        entered.set(); assert release.wait(5)
        return run_node(name, payload, completed)
    runner = WorkflowService(service.store, delayed)
    row = await runner.create(EDITOR, 'late-results', example())
    running = asyncio.create_task(runner.advance(row['id'], EDITOR, 1))
    assert await asyncio.to_thread(entered.wait, 3)
    payload = example();payload['values']['product'] = 'SIM0002'
    await service.edit(row['id'], EDITOR, 1, payload)
    release.set()
    with pytest.raises(Conflict):
        await running
    result = await service.read(row['id'], EDITOR)
    assert result['revision'] == 2 and result['nodes']['validate']['result'] is None


async def test_actual_process_death_and_new_instance_resume(tmp_path):
    # Dies inside a pure calculation, after input validation was checkpointed.
    script = '''
import asyncio,os
from core.store import Store
from core.workflows import WorkflowService,Principal,snapshot,run_node
from core.app import DEFAULTS
p=Principal('test-owner','alice','editor')
def crash(name,payload,done):
 if name=='weekly_report':os._exit(23)
 return run_node(name,payload,done)
async def main():
 s=WorkflowService(Store({'JINSHU_DATA_DIR':os.environ['TEST_DATA']}),crash)
 r=await s.create(p,'process-death',snapshot('weekly_report',DEFAULTS['weekly_report'],None,True))
 await s.advance(r['id'],p,1)
 await s.advance(r['id'],p,1)
asyncio.run(main())
'''
    result = await asyncio.to_thread(subprocess.run, [sys.executable, '-c', script],
                                    env={**os.environ, 'TEST_DATA': str(tmp_path)}, capture_output=True, timeout=15)
    assert result.returncode == 23, result.stderr.decode()
    store = Store({'JINSHU_DATA_DIR': str(tmp_path)})
    svc = WorkflowService(store, clock=lambda: time.time()+LEASE_SECONDS+1)
    row = next(iter((await store.read())['workflow_runs'].values()))
    assert row['nodes']['validate']['status'] == 'succeeded'
    assert row['nodes']['weekly_report']['status'] == 'running'
    done = await finish(svc, row)
    assert done['status'] == 'needs_review'
    assert done['nodes']['validate']['attempts'] == 1
    assert done['nodes']['weekly_report']['attempts'] == 2
    assert any(e['kind'] == 'lease_recovered' for e in done['events'])


async def test_no_storage_no_execution():
    calls = []
    svc = WorkflowService(Store({'VERCEL': '1'}), lambda *x: calls.append(x))
    with pytest.raises(StoreUnavailable):
        await svc.create(EDITOR, 'fail-closed', example())
    assert not calls


async def test_csv_export_neutralizes_formula_injection(service):
    p = example('weekly_report');p['sources']['weekly_raw.csv'][0]['名称'] = '=CMD()'
    row = await finish(service, await service.create(EDITOR, 'csv-formula', p))
    await service.review(row['id'], REVIEWER, 1, 'approve', '仅测试脱敏导出')
    raw, _ = await service.export(row['id'], EDITOR, 1, 'csv')
    assert "'=CMD()" in raw.decode('utf-8-sig')


async def test_authenticated_http_workflow_and_owner_isolation(tmp_path):
    env = {'JINSHU_DATA_DIR': str(tmp_path), 'JINSHU_DEMO_ACCOUNTS':'1','JINSHU_SEMANTIC':'0'}
    app = create_app(env=env)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver') as a, \
               httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url='http://testserver') as b:
        assert (await a.get('/api/workflows')).status_code == 403
        await a.get('/api/workspace/bootstrap');await b.get('/api/workspace/bootstrap')
        assert (await a.post('/api/workspace/login',json={'username':'editor','password':'demo-editor'})).status_code == 200
        await b.post('/api/workspace/login',json={'username':'reviewer','password':'demo-reviewer'})
        data={'workflow':'weekly_report','values':{},'use_examples':True,'request_id':'http-idempotency'}
        response=await a.post('/api/workflows',json=data);assert response.status_code==200,response.text
        row=response.json();id=row['id']
        assert (await b.get('/api/workflows/'+id)).status_code == 403
        for _ in range(5):
            r=await a.post(f'/api/workflows/{id}/advance',json={'revision':1});assert r.status_code==200,r.text
        assert r.json()['status']=='needs_review'
        queue=(await b.get('/api/workflows?queue=true')).json();assert len(queue)==1
        assert (await a.post(f'/api/workflows/{id}/review',json={'revision':1,'decision':'approve','reason':'自审'})).status_code==403
        assert (await b.post(f'/api/workflows/{id}/review',json={'revision':1,'decision':'approve','reason':'已核对示例'})).status_code==200
        out=await a.get(f'/api/workflows/{id}/export?revision=1');assert out.status_code==200
        assert out.headers['x-jinshu-export-scope']=='server-held-reviewed-draft'
        assert (await a.post(f'/api/workflows/{id}/export',json={'result':{'fake':1}})).status_code==405
        assert (await a.get(f'/api/workflows/{id}/export?revision=0')).status_code==409
        assert (await a.delete(f'/api/workflows/{id}?revision=1')).status_code==200


@pytest.mark.parametrize('bad', ['', 'short', 'unsafe/id', 'x'*81])
def test_invalid_request_id_is_rejected_by_api_model(bad):
    from core.workflow_api import Create
    with pytest.raises(ValueError):
        Create(workflow='weekly_report',request_id=bad)


def test_example_snapshot_does_not_change_after_fixture_read():
    p=example('weekly_report');p['sources']['weekly_raw.csv'][0]['名称']='changed'
    assert tools.source('weekly_raw.csv')[0]['名称']!='changed'


def test_explicit_inputs_and_example_exclusion():
    with pytest.raises(ValueError):snapshot('issuance',{},None,False)
    with pytest.raises(ValueError):snapshot('weekly_report',{}, {'weekly_raw.csv':[]},True)
    with pytest.raises(ValueError):snapshot('unknown',{},None,True)


def calendar_result(calendar, **params):
    return execute('issuance',{**DEFAULTS['issuance'],'start':'2026-11-07','count':1,**params},sources={'calendar.json':calendar})['result']


def test_calendar_workday_override_and_finite_coverage():
    c={'version':'test','holidays':[],'workdays':['2026-11-07'],'coverage_start':'2026-11-01','coverage_end':'2027-12-31'}
    result=calendar_result(c)
    assert result['rows'][0]['成立日']=='2026-11-07'
    assert result['constraint_checks']['calendar_coverage_provided']


@pytest.mark.parametrize('calendar',[
    {'version':'test','holidays':['2026-11-07'],'workdays':['2026-11-07']},
    {'version':'test','holidays':[],'coverage_start':'2026-11-01'},
    {'version':'test','holidays':[],'coverage_start':'2026-11-01','coverage_end':'2026-11-30'},
    {'version':'test','holidays':[],'coverage_start':'2026-12-01','coverage_end':'2026-11-01'},
    {'version':'test','holidays':[],'workdays':['not-a-date']},
])
def test_invalid_or_incomplete_calendars_do_not_silently_schedule(calendar):
    with pytest.raises(ValueError):calendar_result(calendar)


def test_colliding_issuance_batches_are_blocked():
    from datetime import date,timedelta
    holidays=[str(date(2026,11,6)+timedelta(days=i)) for i in range(12)]
    with pytest.raises(ValueError,match='重合'):
        calendar_result({'version':'test','holidays':holidays},start='2026-11-06',count=2)

async def test_code_change_requires_new_input_revision(service):
    row = await finish(service, await service.create(EDITOR, 'code-binding', example('weekly_report')))
    await service.store.mutate(lambda s: s['workflow_runs'][row['id']].update(code_hash='old-implementation'))
    with pytest.raises(Conflict):
        await service.review(row['id'], REVIEWER, 1, 'approve', '旧代码不能直接批')
    revised = await service.edit(row['id'], EDITOR, 1, example('weekly_report'))
    from core.workflows import CODE_HASH
    assert revised['code_hash'] == CODE_HASH


async def test_operational_metrics_do_not_invent_quality(service):
    row=await finish(service,await service.create(EDITOR,'metrics-case',example('weekly_report')))
    m=await service.metrics(EDITOR)
    assert m['submitted']==1 and m['awaiting_review']==1 and m['approved']==0
    assert 'accuracy' not in m
    assert (await service.metrics(STRANGER))['submitted']==0
