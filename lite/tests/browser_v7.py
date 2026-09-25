"""Browser acceptance of real local UI, using only public/synthetic inputs."""
import json, os, zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('evidence/v7/browser');out.mkdir(parents=True,exist_ok=True)
report={'scope':'Chromium local HTTP; deterministic UI and controlled optional-model response; not live model/users/production','checks':{},'page_errors':[]}
def check(name,value=True):
 assert value,name
 report['checks'][name]=True
with sync_playwright() as p:
 b=p.chromium.launch(executable_path=os.environ.get('CHROMIUM_PATH'),headless=True,args=['--no-sandbox'])
 page=b.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
 page.on('pageerror',lambda e:report['page_errors'].append(str(e)));page.on('dialog',lambda d:d.accept())
 def ask(q):
  page.get_by_role('button',name='学习与问答',exact=True).click();page.select_option('#ask-flow','auto');page.fill('#ask-question',q);page.click('#ask-submit');page.wait_for_function('!!window.jinshuTest.getState().traces.length');page.wait_for_timeout(100)
 try:
  page.goto(os.environ.get('LITE_TEST_URL','http://127.0.0.1:8795'));page.wait_for_selector('#ask-submit')
  check('build_fingerprint_loaded',len(page.evaluate('window.jinshuTest.engineHash()'))==64)
  ask('商业银行的四个职能是什么？')
  check('key_evidence_readable',all(x in page.locator('.answer-summary').all_text_contents()[0] for x in ['信用中介','支付中介','信用创造','金融服务']))
  check('full_evidence_collapsed_by_default',not page.locator('#full-evidence').evaluate('(el)=>el.open'))
  check('technical_trace_collapsed',not page.get_by_text('执行过程与参数（技术详情）',exact=True).evaluate('(el)=>el.parentElement.open'))
  page.screenshot(path=str(out/'readable-answer-desktop.png'),full_page=True)
  page.locator('#full-evidence>summary').click();check('full_evidence_accessible',page.locator('.original-quote').first.is_visible())
  page.get_by_role('button',name='打开对应原文',exact=True).first.click();check('original_document_can_open',page.locator('#viewer').is_visible());page.click('#close-viewer')
  page.get_by_role('button',name='还未解决',exact=True).click();page.get_by_role('button',name='已解决',exact=True).click()
  check('outcome_one_denominator',page.evaluate('window.jinshuTest.getState().outcomes.length')==1)
  for name in ['wealth_benchmark','issuance','material_fill','weekly_report','onboarding','kep','strategy','statements']:
   page.get_by_role('button',name='业务工具',exact=True).click();page.select_option('#tool-flow',name);page.click('#tool-run');page.wait_for_selector('#tool-output table');check('tool_executes_'+name)
  page.get_by_role('button',name='JSON导出',exact=True).click();check('unapproved_export_blocked','先复核' in page.locator('#notice').inner_text())
  page.check('#task-review-confirm');page.get_by_role('button',name='确认当前结果',exact=True).click();page.wait_for_function("document.getElementById('task-status').textContent.includes('已确认')")
  with page.expect_download() as d:page.get_by_role('button',name='JSON导出',exact=True).click()
  target=out/'task-output.json';d.value.save_as(target);data=json.loads(target.read_text());check('export_has_version_and_approval',bool(data['approval']) and data['inputVersion']==1)
  with page.expect_download() as d:page.get_by_role('button',name='Word草稿',exact=True).click()
  word=out/'task-output.docx';d.value.save_as(word)
  with zipfile.ZipFile(word) as z:check('word_export_real_ooxml','word/document.xml' in z.namelist())
  page.select_option('#tool-flow','issuance');page.fill('#param-count','2');page.click('#tool-run');page.check('#task-review-confirm');page.get_by_role('button',name='确认当前结果',exact=True).click();page.wait_for_timeout(100)
  page.screenshot(path=str(out/'versioned-task-desktop.png'),full_page=True)
  page.fill('#param-count','3');page.get_by_role('button',name='JSON导出',exact=True).click();check('edited_input_invalidates_confirmation','先复核' in page.locator('#notice').inner_text())
  page.get_by_role('button',name='学习与问答',exact=True).click();page.get_by_role('button',name='业务工具',exact=True).click();check('input_kept_across_navigation',page.locator('#param-count').input_value()=='3')
  page.reload();page.wait_for_selector('#ask-submit');page.get_by_role('button',name='业务工具',exact=True).click();page.select_option('#tool-flow','issuance');check('input_kept_after_refresh',page.locator('#param-count').input_value()=='3')
  # Native parsing remains intact; uploads never leave this page.
  page.get_by_role('button',name='资料与上传',exact=True).click();page.set_input_files('#upload-file',{'name':'验证资料.txt','mimeType':'text/plain','buffer':'星桥模拟复核码是 DEMO-V7-73。仅供开发测试，不是现行制度。'.encode()});page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.get_by_role('button',name='本地启用',exact=True).click();page.get_by_role('button',name='本地停用',exact=True).wait_for();check('local_upload_and_review')
  ask('星桥模拟复核码是什么');check('uploaded_source_can_be_retrieved','DEMO-V7-73' in page.locator('#ask-result').inner_text())
  page.get_by_role('button',name='资料与上传',exact=True).click();page.set_input_files('#upload-file',str(word.resolve()));page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.wait_for_function('window.jinshuTest.getState().docs.length===2');check('docx_import_kept')
  pdf=Path('data/mock_pdfs/06_public_faq.pdf');page.set_input_files('#upload-file',str(pdf.resolve()));page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.wait_for_function('window.jinshuTest.getState().docs.length===3',timeout=60000);check('native_pdf_import_kept')
  pages={'pages':[{'page':i,'text':'模拟分页资料 '+str(i)+'。确认末页保留。'} for i in range(1,116)]}
  page.set_input_files('#upload-file',{'name':'115pages.json','mimeType':'application/json','buffer':json.dumps(pages,ensure_ascii=False).encode()});page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.wait_for_function('window.jinshuTest.getState().docs.length===4');check('all_115_pages_kept',page.evaluate('window.jinshuTest.getState().docs[3].pages.at(-1).page')==115)
  ask('发行排期遇非工作日怎么办');page.get_by_role('button',name='反馈与策略',exact=True).click();page.fill('#feedback-terms','顺延');page.get_by_role('button',name='保存本次反馈',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('反馈已保存')")
  page.select_option('#policy-preset','expand');page.get_by_role('button',name='生成候选并回放',exact=True).click();page.get_by_role('button',name='本地启用',exact=True).wait_for(timeout=60000)
  check('same_batch_comparison_visible','同批开发检查' in page.locator('#content').inner_text())
  page.get_by_role('button',name='本地启用',exact=True).click();check('policy_confirmation_required','明确确认发布' in page.locator('#notice').inner_text())
  # Source change after evaluation forces explicit revalidation, not silent activation.
  page.get_by_role('button',name='资料与上传',exact=True).click();page.get_by_role('button',name='本地停用',exact=True).click();page.get_by_role('button',name='反馈与策略',exact=True).click();page.locator('input[id^="publish-confirm-"]').check();page.get_by_role('button',name='本地启用',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('重验收')");check('changed_source_blocks_publication')
  page.get_by_role('button',name='重新验收',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('已重验收')");check('revalidation_keeps_history',page.evaluate('window.jinshuTest.getState().candidates.at(-1).history.length')==1)
  page.screenshot(path=str(out/'policy-replay-desktop.png'),full_page=True)
  page.locator('input[id^="publish-confirm-"]').check();page.get_by_role('button',name='本地启用',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('候选对本浏览器')");check('explicit_policy_publication')
  ask('发行排期');check('next_request_uses_new_policy',page.evaluate('window.jinshuTest.getState().traces.at(-1).topK')==7)
  page.get_by_role('button',name='反馈与策略',exact=True).click();page.get_by_role('button',name='回滚稳定基线',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('已回滚')");ask('发行排期');check('rollback_restores_previous_policy',page.evaluate('window.jinshuTest.getState().traces.at(-1).topK')==5)
  # A delayed synthetic model result is cancelled by starting a new chat.
  routes=[];page.route('**/api/answer',lambda r:routes.append(r));page.get_by_role('button',name='可选：调用部署者的模型',exact=True).click();page.fill('#model-code','controlled-test');page.check('#model-consent');page.get_by_role('button',name='确认并生成',exact=True).click();page.wait_for_timeout(100);check('optional_model_consent_path',len(routes)==1)
  page.click('#close-viewer');page.get_by_role('button',name='新会话',exact=True).click();page.fill('#ask-question','解释直接融资和间接融资');page.click('#ask-submit');page.wait_for_timeout(100)
  try:routes[0].fulfill(status=200,content_type='application/json',body=json.dumps({'answer':'STALE-CONTROLLED-DRAFT【来源1】'}))
  except Exception:pass
  page.wait_for_timeout(200);check('stale_model_response_not_displayed','STALE-CONTROLLED-DRAFT' not in page.locator('#ask-result').inner_text());check('stale_model_response_not_saved',not any('modelDraft' in t for t in page.evaluate('window.jinshuTest.getState().traces')))
  for name in ['执行记录','记忆工作台','回放与评测','体验记录','原理与部署']:
   page.get_by_role('button',name=name,exact=True).click();check('navigation_'+name,bool(page.locator('#content').inner_text()))
  page.set_viewport_size({'width':390,'height':844});ask('商业银行的四个职能是什么？');check('mobile_no_horizontal_overflow',page.evaluate('document.documentElement.scrollWidth <= innerWidth+2'));page.screenshot(path=str(out/'readable-answer-mobile.png'),full_page=True)
  check('no_uncaught_browser_error',not report['page_errors']);report['status']='passed'
 except Exception as e:
  report['status']='failed';report['failure']=str(e);page.screenshot(path=str(out/'failure.png'),full_page=True);raise
 finally:
  report['passed_checks']=len(report['checks']);(out/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));b.close()
