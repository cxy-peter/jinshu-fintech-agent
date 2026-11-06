"""Chromium acceptance of V11 against real local HTTP and isolated SQLite.

No provider is used by the new business workflow. Existing chat browser tests
are maintained separately; neither set is a live-model quality benchmark.
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.request import urlopen
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.environ.get('JINSHU_V11_EVIDENCE',str(ROOT/'evidence/v11')))
OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[]
with tempfile.TemporaryDirectory() as tmp:
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_','CHAT_','VERCEL','JINSHU_','MONGODB_','BLOB_'))}
    env.update(JINSHU_DATA_DIR=tmp,JINSHU_STORE='sqlite',JINSHU_DEMO_ACCOUNTS='1',JINSHU_SEMANTIC='0')
    log=(OUT/'browser-server.log').open('w')
    proc=subprocess.Popen([sys.executable,'-m','uvicorn','index:app','--host','127.0.0.1','--port','8891'],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    base='http://127.0.0.1:8891'
    try:
        for _ in range(70):
            try:
                if urlopen(base+'/api/status',timeout=1).status==200:break
            except Exception:time.sleep(.1)
        with sync_playwright() as p:
            browser=p.chromium.launch(headless=True,executable_path=os.environ.get('CHROMIUM_PATH') or shutil.which('chromium'))
            page=browser.new_page(viewport={'width':1400,'height':1000},accept_downloads=True)
            page.on('pageerror',lambda e:errors.append(str(e)))
            page.goto(base);page.locator('[data-tab="workflows"]').click()
            expect(page.locator('#wf-type')).to_contain_text('周报质检');checks.append('workflow_catalog_on_same_app')
            page.locator('#wf-example').click();page.locator('#wf-save').click()
            expect(page.locator('#wf-message')).to_contain_text('登录');checks.append('anonymous_cannot_persist_task')
            page.locator('#workspace-account').click()
            page.locator('#ws-user').fill('editor');page.locator('#ws-pass').fill('demo-editor');page.locator('#ws-login').click()
            expect(page.locator('#workspace-account')).to_contain_text('editor')
            page.locator('#wf-save').click();expect(page.locator('#wf-result')).to_contain_text('待执行');checks.append('snapshot_persisted')
            page.locator('#wf-advance').click();expect(page.locator('#wf-message')).to_contain_text('本批已保存');checks.append('validation_checkpoint')
            page.reload();page.locator('[data-tab="workflows"]').click();page.locator('#wf-refresh').click()
            expect(page.locator('#wf-history')).to_contain_text('wealth_review');page.locator('#wf-history button').first.click()
            expect(page.locator('#wf-result')).to_contain_text('已完成');checks.append('reload_recovers_server_checkpoint')
            for _ in range(3):
                page.locator('#wf-advance').click()
                expect(page.locator('#wf-advance')).to_be_enabled() if _<2 else None
                page.wait_for_timeout(200)
            expect(page.locator('#wf-result')).to_contain_text('等待独立复核');checks.append('parallel_tools_verify_and_report')
            page.locator('#wf-result input').fill('不能自审');page.get_by_role('button',name='确认当前版本',exact=True).click()
            expect(page.locator('#wf-message')).to_contain_text('审核角色');checks.append('server_rejects_author_approval')
            page.locator('#workspace-account').click()
            page.locator('#ws-user').fill('reviewer');page.locator('#ws-pass').fill('demo-reviewer');page.locator('#ws-login').click()
            expect(page.locator('#workspace-account')).to_contain_text('reviewer')
            page.locator('#wf-refresh').click();expect(page.locator('#wf-queue')).to_contain_text('editor')
            page.locator('#wf-queue button').first.click();page.locator('#wf-result input').fill('核对了示例口径及缺失项，作为草稿导出')
            page.get_by_role('button',name='确认当前版本',exact=True).click();expect(page.locator('#wf-result')).to_contain_text('已复核，可导出草稿');checks.append('independent_review')
            with page.expect_download() as download:page.get_by_role('button',name='下载复核包 JSON',exact=True).click()
            download.value.save_as(str(OUT/'workflow-export.json'))
            artifact=json.loads((OUT/'workflow-export.json').read_text());assert artifact['approval']['reviewer']=='reviewer';assert not artifact['business_action_executed'];checks.append('server_held_export_download')
            page.screenshot(path=str(OUT/'workflow-reviewed.png'),full_page=True)
            page.locator('#wf-values').fill('{}');expect(page.locator('#wf-result')).to_contain_text('输入已改');expect(page.get_by_role('button',name='下载复核包 JSON',exact=True)).to_have_count(0);checks.append('unsaved_edit_hides_old_export')
            page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'workflow-mobile.png'),full_page=True)
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');checks.append('mobile_no_overflow')
            assert not errors,errors
            browser.close()
    finally:
        proc.terminate();proc.wait(timeout=10);log.close()
result={'passed':len(checks),'checks':checks,'page_errors':errors,'scope':'real Chromium + local HTTP + isolated SQLite; no live model and no cloud deployment claim'}
(OUT/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
print(json.dumps(result,ensure_ascii=False))
