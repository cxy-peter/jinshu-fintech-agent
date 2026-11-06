"""Recover a crash between persisting the last result and settling its batch."""
import time
import pytest
from core.store import Store
from core.workflows import WorkflowService, Principal, snapshot, LEASE_SECONDS
from core.app import DEFAULTS

@pytest.mark.parametrize('hard_failure', [False, True])
async def test_recovery_after_final_checkpoint_does_not_rerun_or_stall(tmp_path, hard_failure):
    store=Store({'JINSHU_DATA_DIR':str(tmp_path)})
    service=WorkflowService(store)
    user=Principal('owner','editor','editor')
    tool='statements' if hard_failure else 'weekly_report'
    payload=snapshot(tool,DEFAULTS[tool],None,True)
    if hard_failure:payload['sources']['statements.csv'][1]['assets']='999999'
    row=await service.create(user,'checkpoint-settlement',payload)
    for _ in range(5):
        row=await service.advance(row['id'],user,1)
        if row['status'] in ('needs_review','blocked'):break
    expected=row['status']; attempts={k:n['attempts'] for k,n in row['nodes'].items()}
    # Simulate the exact persisted state immediately before settle(): results
    # exist but the lease and running flag have not been cleared.
    await store.mutate(lambda state:state['workflow_runs'][row['id']].update(
        status='running',lease={'id':'interrupted','until':time.time()-1},quality=None))
    def must_not_run(*args):raise AssertionError('No recalculation should be required')
    resumed=await WorkflowService(Store(dict(store.env)),runner=must_not_run).advance(row['id'],user,1)
    assert resumed['status']==expected and resumed['lease'] is None
    assert {k:n['attempts'] for k,n in resumed['nodes'].items()}==attempts
    if hard_failure:assert resumed['nodes']['report']['result'] is None
