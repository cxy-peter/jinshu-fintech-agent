"""Actual local launcher + Chromium: configure, scan, retrieve, read original.

Uses temporary synthetic text, no model key and no files from the user's drive.
CHROMIUM_PATH selects the installed Chromium; JINSHU_EVIDENCE_DIR selects output.
"""
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.getenv('JINSHU_EVIDENCE_DIR', str(ROOT / 'evidence/v11-1/local-folder')))
OUT.mkdir(parents=True, exist_ok=True)
checks, errors = [], []

with tempfile.TemporaryDirectory(prefix='jinshu-browser-local-') as temporary:
    base_dir = Path(temporary)
    initial, selected = base_dir / 'initial', base_dir / 'selected'
    initial.mkdir()
    selected.mkdir()
    name = '合成本地FOF资料.txt'
    (selected / name).write_text('仅合成检索测试。\nFOF（基金中基金）是指以其他基金为主要投资对象的基金。', encoding='utf-8')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = {k: v for k, v in os.environ.items()
           if not k.startswith(('DEEPSEEK_', 'CHAT_', 'MODEL_', 'JINSHU_', 'MAX_MODEL_', 'VERCEL'))}
    env.update(JINSHU_DATA_DIR=str(base_dir / 'state'), JINSHU_STORE='sqlite', JINSHU_SEMANTIC='0')
    with (OUT / 'server.log').open('w') as log:
        process = subprocess.Popen([sys.executable, 'scripts/run_local_folder.py', '--root', str(initial), '--port', str(port)],
                                   cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                try:
                    with urllib.request.urlopen(base + '/api/local-folder', timeout=1) as response:
                        if response.status == 200:
                            break
                except OSError:
                    if process.poll() is not None:
                        raise RuntimeError('Local launcher exited; inspect server.log')
                    time.sleep(.1)
            else:
                raise RuntimeError('Local launcher did not become ready')
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True,
                    executable_path=os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or None,
                    args=['--no-sandbox', '--disable-dev-shm-usage'])
                page = browser.new_page(viewport={'width': 1440, 'height': 1050})
                page.on('pageerror', lambda error: errors.append(str(error)))
                page.goto(base)
                page.locator('[data-tab="library"]').click()
                expect(page.locator('#folder-local-controls')).to_be_visible()
                expect(page.locator('#folder-root')).to_have_value(str(initial))
                page.locator('#folder-root').fill(str(selected))
                page.locator('#folder-save').click()
                expect(page.locator('#folder-status')).to_contain_text(str(selected))
                expect(page.locator('#folder-status')).to_contain_text('已索引 0 份')
                checks.append('same_workbench_configures_selected_local_directory')

                page.locator('#folder-scan').click()
                expect(page.locator('#folder-status')).to_contain_text('已索引 1 份', timeout=15000)
                expect(page.locator('#folder-list')).to_contain_text(name)
                page.screenshot(path=str(OUT / 'local-folder-catalog.png'), full_page=True)
                checks.append('scan_builds_index_and_renders_readable_catalog')
                page.locator('#folder-list').get_by_role('button', name='查看提取原文').click()
                expect(page.locator('#private-reader')).to_contain_text('其他基金')
                expect(page.locator('#private-reader select')).to_contain_text('文本段')
                page.locator('#private-reader').get_by_role('button', name='关闭', exact=True).click()
                checks.append('catalog_opens_local_original_with_honest_location')

                page.locator('[data-tab="chat"]').click()
                expect(page.locator('#use-local-folder')).to_be_checked()
                expect(page.locator('#consent')).not_to_be_checked()
                page.locator('#query').fill('基金中基金是什么？')
                with page.expect_response(lambda response: response.url == base + '/api/retrieve') as event:
                    page.locator('#search-only').click()
                result = event.value.json()
                assert event.value.status == 200
                assert result['sources'] and all(s['origin'] == 'local_folder' for s in result['sources'])
                assert result['diagnostics']['local_folder']['model_called'] is False
                expect(page.locator('#messages')).to_contain_text('未调用模型')
                expect(page.locator('#messages blockquote')).to_contain_text('其他基金')
                checks.append('retrieve_only_uses_local_evidence_without_model_consent')
                page.locator('#messages').get_by_role('button', name='查看提取原文').click()
                expect(page.locator('#private-reader')).to_contain_text(name)
                expect(page.locator('#private-reader')).to_contain_text('其他基金')
                page.screenshot(path=str(OUT / 'local-folder-original.png'), full_page=True)
                checks.append('retrieval_result_opens_same_local_original')
                browser.close()
            assert not errors, errors
            report = {'passed': len(checks), 'checks': checks, 'page_errors': errors,
                      'scope': 'Actual launcher, same FastAPI workbench, HTTP and Chromium; synthetic local text; no model call or production latency measurement.'}
            (OUT / 'browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
