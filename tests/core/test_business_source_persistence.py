"""Custom synthetic input is preserved independently of the bundled-example switch."""
import copy
import json
from pathlib import Path

from core.store import Store
from core.workflows import Principal, WorkflowService, snapshot


CASE = json.loads((Path(__file__).parents[2] / 'data/synthetic/issuance_review_demo.json').read_text(encoding='utf-8'))
EDITOR = Principal('custom-case-editor', 'case-editor', 'editor')
REVIEWER = Principal('custom-case-reviewer', 'case-reviewer', 'reviewer')


async def finish(service, row):
    for _ in range(6):
        if row['status'] == 'needs_review':
            return row
        row = await service.advance(row['id'], EDITOR, row['revision'])
    assert row['status'] == 'needs_review'
    return row


def test_custom_synthetic_snapshot_freezes_supplied_sources_without_bundled_mode():
    case = copy.deepcopy(CASE)
    payload = snapshot(case['workflow'], case['values'], case['sources'], False)
    assert payload['synthetic'] is True
    assert payload['source_mode'] == 'user_supplied'
    assert payload['sources'] == case['sources']
    case['sources']['calendar.json']['workdays'].clear()
    assert payload['sources']['calendar.json']['workdays'] == ['2026-11-08']
    assert payload['sources']['calendar.json']['version'] == 'SYNTHETIC-SEND-DEMO-v1'


async def test_custom_case_survives_review_reload_revision_and_recalculation(tmp_path):
    env = {'JINSHU_STORE': 'sqlite', 'JINSHU_DATA_DIR': str(tmp_path)}
    service = WorkflowService(Store(env))
    payload = snapshot(CASE['workflow'], CASE['values'], CASE['sources'], False)
    row = await finish(service, await service.create(EDITOR, 'custom-synthetic-case', payload))
    record = row['nodes']['material_fill']['result']
    assert record['synthetic'] is True
    assert record['result']['rows'][0]['候选发送日'] == '2026-11-06'
    assert record['result']['send_plan']['sent'] is False
    await service.review(row['id'], REVIEWER, 1, 'approve', '核对合成来源及发送约束，未发送')
    # A new service instance stands in for reload/serverless invocation.
    reloaded = await WorkflowService(Store(env)).read(row['id'], EDITOR)
    assert reloaded['payload']['source_mode'] == 'user_supplied'
    assert reloaded['payload']['sources'] == CASE['sources']
    revised_sources = copy.deepcopy(reloaded['payload']['sources'])
    revised_sources['calendar.json']['version'] = CASE['revision']['calendar_version']
    revised_sources['calendar.json']['holidays'] = CASE['revision']['holidays']
    revised = snapshot(reloaded['workflow'], reloaded['payload']['values'], revised_sources, False)
    edited = await service.edit(row['id'], EDITOR, 1, revised)
    assert edited['revision'] == 2 and edited['approval'] is None
    assert edited['nodes']['material_fill']['status'] == 'pending'
    done = await finish(service, edited)
    assert done['payload']['synthetic'] is True
    assert done['payload']['source_mode'] == 'user_supplied'
    assert done['payload']['sources'] == revised_sources
    result = done['nodes']['material_fill']['result']['result']
    assert result['rows'][0]['候选发送日'] == '2026-11-05'
    assert result['send_plan']['sent'] is False
    assert result['send_plan']['business_action_executed'] is False
    assert done['nodes']['report']['result']['synthetic'] is True
    assert done['nodes']['report']['result']['business_action_executed'] is False
