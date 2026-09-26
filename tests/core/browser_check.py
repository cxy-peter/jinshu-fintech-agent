"""Real Chromium + local HTTP; only the provider HTTP response is explicitly mocked."""
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
import urllib.request
from playwright.sync_api import sync_playwright, expect

ROOT=Path(__file__).resolve().parents[2]
OUT=Path(os.getenv('JINSHU_EVIDENCE_DIR', str(ROOT/'evidence/core-v9')))
OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[];processes=[];logs=[]
base='http://127.0.0.1:8876';mock='http://127.0.0.1:8877'
def passed(name):checks.append(name)
def start(module, port, test=False):
    env={k:v for k,v in os.environ.items() if not k.startswith(('DEEPSEEK_', 'CHAT_', 'MODEL_', 'JINSHU_ACCESS_', 'MAX_MODEL_'))}
    env['PYTHONPATH']=str(ROOT)+os.pathsep+str(ROOT/'tests/core')
    log=(OUT/f'server-{port}.log').open('w');logs.append(log)
    p=subprocess.Popen([sys.executable,'-m','uvicorn',module,'--host','127.0.0.1','--port',str(port)],cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT)
    processes.append(p)
    for _ in range(80):
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/status',timeout=1) as r:
                if r.status==200:return
        except Exception:pass
        if p.poll() is not None:raise RuntimeError(f'server exited: {port}')
        time.sleep(.1)
    raise RuntimeError(f'server not ready: {port}')

try:
    start('index:app',8876)
    # Use agent-browser when installed. This environment may only ship Playwright.
    try:
        subprocess.run(['agent-browser','open',base],check=True,timeout=20,capture_output=True)
        subprocess.run(['agent-browser','snapshot','-i'],check=True,timeout=20,capture_output=True)
        subprocess.run(['agent-browser','close'],timeout=10,capture_output=True)
        browser_tool='agent-browser initial check + Playwright acceptance'
    except FileNotFoundError:
        browser_tool='Playwright + system Chromium (agent-browser CLI not installed)'
    with sync_playwright() as p:
        executable=os.getenv('CHROMIUM_PATH') or (shutil.which('chromium') or None)
        browser=p.chromium.launch(headless=True,executable_path=executable,args=['--no-sandbox','--disable-dev-shm-usage'])
        page=browser.new_page(viewport={'width':1440,'height':1050},accept_downloads=True)
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(base);expect(page.locator('#model-status')).to_contain_text('待配置')
        expect(page.get_by_role('heading',name='把问题交给金枢')).to_be_visible();passed('default_entrypoint_opens_with_zero_environment')
        assert page.evaluate('document.body.innerText.length')>300;passed('no_blank_page_or_required_login')
        page.screenshot(path=str(OUT/'default-no-key.png'),full_page=True)
        page.locator('#query').fill('没有密钥时能否明确提示');page.locator('#consent').check();page.locator('#send').click()
        expect(page.locator('.message.error')).to_contain_text('未配置');passed('missing_key_error_visible_not_fake_answer')
        page.locator('[data-tab="tools"]').click()
        for name in ['issuance','material_fill','wealth_benchmark','weekly_report','onboarding','kep','strategy','statements']:
            page.locator('#tool-select').select_option(name)
            page.locator('#load-example').click();expect(page.locator('#tool-examples')).to_be_checked()
            page.locator('#run-tool').click();expect(page.locator('#tool-result')).to_contain_text('"tool": "'+name+'"')
            expect(page.locator('#reviewed')).to_be_enabled();passed('browser_tool_without_key_'+name)
        page.locator('#reviewed').check()
        with page.expect_download() as event:page.locator('#export-json').click()
        event.value.save_as(str(OUT/'browser-tool-export.json'));passed('reviewed_json_export')
        page.locator('#tool-values').fill('{}');expect(page.locator('#export-json')).to_be_disabled();passed('edit_invalidates_export')
        page.locator('[data-tab="status"]').click();expect(page.locator('#status-details')).to_contain_text('DEEPSEEK_API_KEY');passed('configuration_screen_only_model_key_required')
        start('browser_fixture:app',8877,True)
        page.goto(mock);expect(page.locator('#model-status')).to_contain_text('模拟测试环境');passed('mock_transport_is_visibly_labelled')
        page.locator('[data-tab="status"]').click();page.locator('#check-consent').check();page.locator('#model-check').click()
        expect(page.locator('#check-result')).to_contain_text('mock_http_test_only');passed('model_check_through_actual_same_app')
        page.locator('[data-tab="chat"]').click()
        page.locator('#doc-title').fill('<img src=x onerror=alert(1)> 排期资料')
        page.locator('#doc-text').fill('发行排期需要核对日历和募集成立日期。所有日期必须由人员复核。')
        page.locator('#add-doc').click();expect(page.locator('#doc-count')).to_have_text('1 / 3');passed('current_request_document_added')
        assert page.locator('#documents img').count()==0;passed('document_title_rendered_as_text_not_html')
        page.locator('#query').fill('发行排期需要注意什么？');page.locator('#consent').check();page.locator('#send').click()
        expect(page.locator('.message.assistant').last).to_contain_text('HTTP协议模拟测试',timeout=10000)
        expect(page.locator('.message.assistant details').first).to_contain_text('本次检索片段');passed('chat_retrieval_citation_and_trace_render')
        assert page.locator('.message.assistant img').count()==0;passed('answer_rendered_as_text')
        page.screenshot(path=str(OUT/'chat-protocol-test.png'),full_page=True)
        page.locator('#query').fill('模拟401');page.locator('#send').click();expect(page.locator('.message.error').last).to_contain_text('密钥无效');passed('upstream_401_is_actionable')
        page.locator('#query').fill('慢请求测试');page.locator('#send').click();expect(page.locator('#cancel')).to_be_visible()
        page.locator('#clear-chat').click();page.wait_for_timeout(1800)
        assert page.locator('.message.assistant').count()==0;passed('late_response_does_not_restore_cleared_conversation')
        page.reload();expect(page.locator('#doc-count')).to_have_text('0 / 3');expect(page.locator('#welcome')).to_be_visible();passed('refresh_clears_browser_only_documents_and_history')
        page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'mobile.png'),full_page=True)
        assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');passed('mobile_no_horizontal_overflow')
        for tab in ['tools','status','chat']:
            page.locator(f'[data-tab="{tab}"]').click()
            assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth')
        passed('all_mobile_tabs_navigate')
        browser.close()
    assert not errors,errors
    result={'passed':len(checks),'checks':checks,'page_errors':errors,'browser':browser_tool,
            'scope':'Actual default index:app for zero-config checks; same core app with HTTP-only mock for provider scenarios. No live DeepSeek key or cloud deployment tested.'}
    (OUT/'browser.json').write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps(result,ensure_ascii=False,indent=2))
finally:
    for process in processes:
        process.terminate()
    for process in processes:
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill()
    for log in logs:log.close()
