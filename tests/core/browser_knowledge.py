"""Browser acceptance for private upload, no-model search and one-use handoff.
Only the outbound model transport is mocked. No private user files are fixtures.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(os.getenv('JINSHU_EVIDENCE_DIR', str(ROOT / 'evidence/v11-1/knowledge')))
OUT.mkdir(parents=True, exist_ok=True)
checks, errors = [], []
base = 'http://127.0.0.1:8879'
with tempfile.TemporaryDirectory(prefix='jinshu-browser-knowledge-') as tmp:
    env = {k: v for k, v in os.environ.items() if not k.startswith(('DEEPSEEK_', 'CHAT_', 'MODEL_', 'JINSHU_', 'MAX_MODEL_'))}
    env.update(PYTHONPATH=str(ROOT) + os.pathsep + str(ROOT / 'tests/core'), JINSHU_DATA_DIR=tmp)
    command = "from browser_fixture import respond; from core.app import create_app; import httpx,os,uvicorn; app=create_app(env={'DEEPSEEK_API_KEY':'test-only-key','JINSHU_STORE':'sqlite','JINSHU_DATA_DIR':os.environ['JINSHU_DATA_DIR'],'JINSHU_SEMANTIC':'0'},transport=httpx.MockTransport(respond)); uvicorn.run(app,host='127.0.0.1',port=8879)"
    with (OUT / 'server.log').open('w') as log:
        process = subprocess.Popen([sys.executable, '-c', command], cwd=ROOT, env=env, stdout=log, stderr=subprocess.STDOUT)
        try:
            for _ in range(80):
                try:
                    with urllib.request.urlopen(base + '/api/status', timeout=1) as response:
                        if response.status == 200:
                            break
                except Exception:
                    if process.poll() is not None:
                        raise RuntimeError('knowledge fixture exited')
                    time.sleep(.1)
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True, executable_path=os.getenv('CHROMIUM_PATH') or shutil.which('chromium') or None,
                                            args=['--no-sandbox', '--disable-dev-shm-usage'])
                first, second, third = [browser.new_context(viewport={'width':1440,'height':1050}) for _ in range(3)]
                a, b, c = first.new_page(), second.new_page(), third.new_page()
                for page in (a, b, c):
                    page.on('pageerror', lambda error: errors.append(str(error)))
                a.goto(base)
                expect(a.locator('#private-chat-status')).to_contain_text('0 份')
                a.locator('[data-tab="library"]').click()
                sample = '仅项目合成检索测试。\nFOF（基金中基金）是以其他基金为主要投资对象的基金。\n合成案例中的选基过程需要核对基金经理、费率和资产配置。'
                a.locator('#cloud-files').set_input_files({'name':'合成FOF学习资料.txt','mimeType':'text/plain','buffer':sample.encode()})
                expect(a.locator('#cloud-status')).to_contain_text('新导入 1 份', timeout=15000)
                expect(a.locator('#cloud-list')).to_contain_text('合成FOF学习资料.txt')
                checks.append('browser_upload_parses_and_persists_private_document')
                a.locator('#cloud-list').get_by_role('button', name='合成FOF学习资料.txt').click()
                expect(a.locator('#private-reader')).to_contain_text('其他基金')
                expect(a.locator('#private-reader select')).to_contain_text('文本段')
                a.locator('#private-reader').get_by_role('button', name='关闭', exact=True).click()
                checks.append('private_original_opens_with_honest_text_location')
                a.locator('[data-tab="chat"]').click()
                a.locator('#query').fill('基金中基金是什么？')
                a.locator('#search-only').click()
                expect(a.locator('#messages')).to_contain_text('未调用模型')
                expect(a.locator('#messages blockquote')).to_contain_text('其他基金')
                checks.append('retrieve_only_reaches_backend_without_model_consent')
                a.locator('#consent').check()
                a.locator('#send').click()
                expect(a.locator('.message.assistant').last).to_contain_text('HTTP协议模拟测试', timeout=10000)
                expect(a.locator('.message.assistant').last).to_contain_text('合成FOF学习资料.txt')
                checks.append('streamed_chat_uses_private_evidence_and_shows_citations')
                a.reload()
                expect(a.locator('#private-chat-status')).to_contain_text('1 份')
                b.goto(base)
                expect(b.locator('#private-chat-status')).to_contain_text('0 份')
                checks.append('reload_persists_and_another_browser_cannot_read_private_catalog')
                a.locator('[data-tab="library"]').click()
                a.locator('#cloud-handoff').click()
                expect(a.locator('#cloud-handoff-result a')).to_be_visible()
                link = a.locator('#cloud-handoff-result a').get_attribute('href')
                b.goto(link)
                expect(b.locator('#cloud-list')).to_contain_text('合成FOF学习资料.txt', timeout=10000)
                assert '#library=' not in b.url
                a.locator('#cloud-refresh').click()
                expect(a.locator('#private-chat-status')).to_contain_text('0 份')
                checks.append('one_use_handoff_moves_access_and_removes_token_from_address')
                c.goto(link)
                expect(c.locator('#cloud-status')).to_contain_text('已使用或已过期')
                checks.append('handoff_cannot_be_replayed')
                b.locator('#cloud-list').get_by_role('button', name='移出检索').click()
                expect(b.locator('#private-chat-status')).to_contain_text('0 份')
                b.locator('[data-tab="chat"]').click()
                b.locator('#query').fill('基金中基金是什么？')
                b.locator('#consent').check()
                b.locator('#send').click()
                expect(b.locator('.message.assistant').last).to_contain_text('没有取得足够相关的资料正文')
                expect(b.locator('#model-status')).to_contain_text('未调用模型')
                checks.append('removed_source_cannot_be_retrieved_or_replaced_with_generic_model_answer')
                b.set_viewport_size({'width':390,'height':844})
                b.locator('[data-tab="library"]').click()
                assert b.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
                b.screenshot(path=str(OUT / 'private-library-mobile.png'), full_page=True)
                checks.append('private_library_mobile_has_no_horizontal_overflow')
                browser.close()
            assert not errors, errors
            report = {'passed':len(checks),'checks':checks,'page_errors':errors,'scope':'Actual HTTP + browser; synthetic text; model transport mocked; does not measure model accuracy or production latency.'}
            (OUT / 'browser.json').write_text(json.dumps(report, ensure_ascii=False, indent=2))
            print(json.dumps(report, ensure_ascii=False, indent=2))
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
