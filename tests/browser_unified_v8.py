"""Actual browser / local HTTP with explicit fixture runtime. No live provider claim."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
OUT=Path('evidence/unified-v8');OUT.mkdir(parents=True,exist_ok=True)
checks=[];errors=[]
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1280,'height':900})
 page.on('pageerror',lambda e:errors.append(str(e)))
 page.goto('http://127.0.0.1:8092');expect(page.get_by_text('云端配置待完成',exact=True)).to_be_visible();checks.append('missing_config_is_visible')
 expect(page.locator('#content')).to_contain_text('index.py');page.screenshot(path=str(OUT/'setup.png'),full_page=True)
 page.goto('http://127.0.0.1:8091');page.locator('#username').fill('editor');page.locator('#password').fill('demo-editor');page.get_by_role('button',name='登录',exact=True).click();expect(page.locator('#logout')).to_be_visible();checks.append('login_and_shared_backend')
 page.get_by_role('button',name='资料问答',exact=True).click();page.locator('#content select').select_option('issuance');page.locator('#content textarea').fill('发行排期需要确认哪些日期？');page.get_by_role('button',name='提交问答',exact=True).click();expect(page.get_by_role('heading',name='回答',exact=True)).to_be_visible();expect(page.locator('#content')).to_contain_text('模式：');checks.append('actual_harness_answer')
 page.get_by_role('button',name='已解决',exact=True).click();expect(page.locator('#notice')).to_contain_text('已更新');checks.append('feedback_endpoint')
 page.screenshot(path=str(OUT/'answer.png'),full_page=True)
 for tool in ['issuance','material_fill','wealth_benchmark','weekly_report','onboarding','kep','strategy','statements']:
  page.get_by_role('button',name='业务任务',exact=True).click();page.locator('#content select').nth(1).select_option(tool);page.get_by_role('button',name='填入合成示例参数',exact=True).click();expect(page.locator('#content')).to_contain_text('输入已修改');page.get_by_role('button',name='执行已保存版本',exact=True).click();expect(page.locator('#content')).to_contain_text('状态：needs_review');checks.append('server_tool_'+tool)
  page.once('dialog',lambda d:d.accept());page.get_by_role('button',name='我已核对当前输入、异常和结果',exact=True).click();expect(page.locator('#content')).to_contain_text('状态：approved')
  with page.expect_download() as d:page.get_by_role('button',name='导出 JSON',exact=True).click()
  path=OUT/(tool+'.json');d.value.save_as(path);record=json.loads(path.read_text());assert record['approval']['actor']=='editor';checks.append('approved_export_'+tool)
 page.get_by_role('button',name='业务任务',exact=True).click();page.locator('#content select').nth(1).select_option('issuance');page.get_by_role('button',name='填入合成示例参数',exact=True).click();page.get_by_role('button',name='执行已保存版本',exact=True).click();expect(page.locator('#content')).to_contain_text('状态：needs_review');page.get_by_label('批次数',exact=True).fill('2');expect(page.locator('#content')).to_contain_text('旧结果不能确认或导出');expect(page.get_by_role('button',name='我已核对当前输入、异常和结果',exact=True)).to_have_count(0);checks.append('unsaved_edit_disables_approval')
 for name in ['知识维护','记忆与偏好','反馈与策略','执行记录','异常与工单','验收与体验','服务与配置']:
  page.get_by_role('button',name=name,exact=True).click();expect(page.locator('#content h2').first).to_be_visible();checks.append('screen_'+name)
 page.set_viewport_size({'width':390,'height':844});page.screenshot(path=str(OUT/'mobile.png'),full_page=True);assert page.evaluate('document.documentElement.scrollWidth<=window.innerWidth');checks.append('mobile_no_overflow')
 browser.close()
assert not errors,errors
(OUT/'browser.json').write_text(json.dumps({'checks':checks,'passed':len(checks),'page_errors':errors,'scope':'Real browser over local HTTP; test-only offline Runtime and CAS memory. No cloud databases or paid models tested.'},ensure_ascii=False,indent=2))
print(json.dumps({'browser_passed':len(checks),'errors':errors}))
