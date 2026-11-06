"""Real Chromium acceptance of the custom synthetic case and V11 revision flow."""
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
checks, errors = [], []


def login(page, username):
    if not page.locator('#ws-user').is_visible():
        page.locator('#workspace-account').click()
    page.locator('#ws-user').fill(username)
    page.locator('#ws-pass').fill('demo-' + username)
    page.locator('#ws-login').click()
    expect(page.locator('#workspace-account')).to_contain_text(username)


def finish(page):
    row = None
    for _ in range(6):
        if page.locator('#wf-result').inner_text().find('等待独立复核') >= 0:
            break
        with page.expect_response(lambda r: r.url.endswith('/advance') and r.request.method == 'POST') as response:
            page.locator('#wf-advance').click()
        assert response.value.ok, response.value.text()
        row = response.value.json()
        if row['status'] == 'needs_review':
            break
        expect(page.locator('#wf-advance')).to_be_enabled()
    expect(page.locator('#wf-result')).to_contain_text('等待独立复核')
    return row


with tempfile.TemporaryDirectory() as tmp:
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DEEPSEEK_', 'CHAT_', 'VERCEL', 'JINSHU_', 'MONGODB_', 'BLOB_'))}
    env.update(JINSHU_DATA_DIR=tmp, JINSHU_STORE='sqlite', JINSHU_DEMO_ACCOUNTS='1', JINSHU_SEMANTIC='0')
    base = 'http://127.0.0.1:8893'
    with open(Path(tmp) / 'server.log', 'w') as log:
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', 'index:app', '--host', '127.0.0.1', '--port', '8893'],
                                cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                try:
                    if urlopen(base + '/api/status', timeout=1).status == 200:
                        break
                except Exception:
                    time.sleep(.1)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=os.environ.get('CHROMIUM_PATH') or None)
                page = browser.new_page(viewport={'width': 1400, 'height': 1000})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base)
                catalog = page.request.get(base + '/api/business-capabilities').json()
                assert len(catalog['capabilities']) == 8 and catalog['automatic_execution'] is False
                checks.append('business_catalog_route')
                page.locator('[data-tab="tools"]').click()
                page.locator('#tools-tab [data-issuance-demo]').click()
                expect(page.locator('#workflows-tab')).to_be_visible()
                expect(page.locator('#wf-type')).to_have_value('material_fill')
                expect(page.locator('#wf-sources')).to_have_value(re.compile('SYNTHETIC-SEND-DEMO-v1'))
                assert json.loads(page.locator('#wf-values').input_value())['product_name'] == '模拟稳健一号（合成演示）'
                assert not page.locator('#wf-examples').is_checked()
                checks.append('complete_case_button_routes_values_and_custom_sources')
                login(page, 'editor')
                with page.expect_response(lambda r: r.url.endswith('/api/workflows') and r.request.method == 'POST') as response:
                    page.locator('#wf-save').click()
                assert response.value.ok, response.value.text()
                saved = response.value.json()
                assert saved['payload']['synthetic'] is True
                assert saved['payload']['source_mode'] == 'user_supplied'
                checks.append('custom_synthetic_snapshot_saved')
                baseline = finish(page)
                assert baseline['nodes']['material_fill']['result']['result']['rows'][0]['候选发送日'] == '2026-11-06'
                assert baseline['nodes']['material_fill']['result']['result']['send_plan']['sent'] is False
                checks.append('baseline_executed_without_sending')
                login(page, 'reviewer')
                page.locator('#wf-refresh').click()
                expect(page.locator('#wf-queue')).to_contain_text('material_fill')
                page.locator('#wf-queue button').first.click()
                expect(page.locator('#wf-result input')).to_be_visible()
                page.locator('#wf-result input').fill('核对自定义合成日历，草稿复核，未发送')
                page.get_by_role('button', name='确认当前版本', exact=True).click()
                expect(page.locator('#wf-result')).to_contain_text('已复核，可导出草稿')
                checks.append('independent_review_of_baseline')
                login(page, 'editor')
                page.reload()
                page.locator('[data-tab="workflows"]').click()
                page.locator('#wf-refresh').click()
                expect(page.locator('#wf-history')).to_contain_text('material_fill')
                page.locator('#wf-history button').first.click()
                expect(page.locator('#wf-result')).to_contain_text('已复核，可导出草稿')
                assert not page.locator('#wf-examples').is_checked()
                sources = json.loads(page.locator('#wf-sources').input_value())
                assert sources['calendar.json']['workdays'] == ['2026-11-08']
                assert sources['calendar.json']['version'] == 'SYNTHETIC-SEND-DEMO-v1'
                checks.append('reload_preserves_source_mode_and_custom_calendar')
                sources['calendar.json'].update(version='SYNTHETIC-SEND-DEMO-v2', holidays=['2026-11-06'])
                page.locator('#wf-sources').fill(json.dumps(sources, ensure_ascii=False))
                expect(page.get_by_role('button', name='下载复核包 JSON', exact=True)).to_have_count(0)
                with page.expect_response(lambda r: r.url.endswith('/api/workflows/' + saved['id']) and r.request.method == 'PUT') as response:
                    page.locator('#wf-save').click()
                assert response.value.ok, response.value.text()
                revised = response.value.json()
                assert revised['revision'] == 2 and revised['approval'] is None
                assert revised['payload']['sources'] == sources
                checks.append('revision_preserves_inputs_and_invalidates_old_approval')
                result = finish(page)
                assert result['nodes']['material_fill']['result']['result']['rows'][0]['候选发送日'] == '2026-11-05'
                assert result['nodes']['material_fill']['result']['result']['send_plan']['sent'] is False
                checks.append('changed_holiday_recomputed_and_requires_review')
                page.locator('#wf-cn-calendar').click()
                expect(page.locator('#wf-message')).to_contain_text('2026-12-31')
                loaded = json.loads(page.locator('#wf-sources').input_value())['calendar.json']
                assert loaded['synthetic'] is False and len(loaded['holidays']) == 33
                assert loaded['coverage_end'] == '2026-12-31'
                assert not page.locator('#wf-examples').is_checked()
                checks.append('official_calendar_explicit_button_preserves_manual_mode')
                assert not errors, errors
                browser.close()
        finally:
            proc.terminate()
            proc.wait(timeout=10)

print(json.dumps({'passed': len(checks), 'checks': checks, 'page_errors': errors,
                  'scope': 'local Chromium + actual HTTP + isolated SQLite, no live model or mail'}, ensure_ascii=False))
