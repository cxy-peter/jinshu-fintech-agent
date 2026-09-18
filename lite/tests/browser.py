"""Actual browser smoke flow on CI localhost. All uploaded fixtures here are synthetic."""
import json,os,zipfile
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('evidence/v5');out.mkdir(parents=True,exist_ok=True)
report={'scope':'Chromium on static HTTP build; synthetic fixtures, not real users','checks':{},'errors':[]}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1000},accept_downloads=True)
 page.on('pageerror',lambda e:report['errors'].append(str(e)));page.on('dialog',lambda d:d.accept())
 try:
  page.goto(os.getenv('LITE_TEST_URL','http://127.0.0.1:8795/'));page.wait_for_selector('#ask-submit')
  page.fill('#ask-question','商业银行的四个职能是什么？');page.click('#ask-submit');page.wait_for_selector('#ask-result .source')
  answer=page.locator('#ask-result').inner_text()
  assert all(x in answer for x in ['信用中介','支付中介','信用创造','金融服务'])
  report['checks']['four_functions_complete']=True
  page.screenshot(path=str(out/'lite-ask.png'),full_page=True)
  ev=page.evaluate('window.jinshuTest.runEvaluation()');report['evaluation']=ev
  assert all(r['route_match'] and r['hit'] for r in ev)
  report['checks']['sixteen_regression_queries']=True
  for name in ['wealth_benchmark','issuance','material_fill','weekly_report','onboarding','kep','strategy','statements']:
   page.get_by_role('button',name='业务工具',exact=True).click();page.select_option('#tool-flow',name);page.click('#tool-run');assert page.locator('#tool-output table').count()
  report['checks']['eight_actual_tools']=True;page.screenshot(path=str(out/'lite-tools.png'),full_page=True)
  with page.expect_download() as downloaded:page.get_by_role('button',name='Word草稿',exact=True).click()
  word=out/'synthetic-export.docx';downloaded.value.save_as(str(word))
  with zipfile.ZipFile(word) as z:assert 'word/document.xml' in z.namelist()
  report['checks']['word_export']=True
  page.get_by_role('button',name='资料与上传',exact=True).click()
  fixture={'name':'模拟知识.txt','mimeType':'text/plain','buffer':'星桥模拟复核码为 DEMO-NOT-REAL-73。这里只是功能验收资料。'.encode()}
  page.set_input_files('#upload-file',fixture);page.get_by_role('button',name='解析并加入待审核',exact=True).click()
  page.wait_for_function('window.jinshuTest.getState().docs.length===1')
  page.get_by_role('button',name='本地启用',exact=True).click();page.wait_for_function("window.jinshuTest.getState().docs[0].status==='active'")
  page.reload();page.wait_for_selector('#ask-submit');assert page.evaluate('window.jinshuTest.getState().docs.length')==1
  page.fill('#ask-question','星桥模拟复核码是什么');page.click('#ask-submit');page.wait_for_selector('#ask-result .source');assert 'DEMO-NOT-REAL-73' in page.locator('#ask-result').inner_text()
  report['checks']['upload_publish_persist_search']=True
  page.get_by_role('button',name='资料与上传',exact=True).click();page.set_input_files('#upload-file',str(word));page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.wait_for_function('window.jinshuTest.getState().docs.length===2');report['checks']['docx_upload']=True
  pdf=Path('data/mock_pdfs/06_public_faq.pdf')
  if not pdf.exists():
   candidates=list(Path('data').rglob('06_public_faq.pdf'));pdf=candidates[0] if candidates else pdf
  if pdf.exists():
   page.set_input_files('#upload-file',str(pdf.resolve()));page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.wait_for_function('window.jinshuTest.getState().docs.length===3',timeout=60000);report['checks']['pdf_native_parse']=True
  else:report['checks']['pdf_native_parse']='not_run_no_fixture'
  page.screenshot(path=str(out/'lite-library.png'),full_page=True)
  page.get_by_role('button',name='学习与问答',exact=True).click();page.fill('#ask-question','发行排期遇非工作日怎么办');page.click('#ask-submit');page.wait_for_selector('#ask-result .source')
  page.get_by_role('button',name='反馈与策略',exact=True).click();page.fill('#feedback-terms','顺延');page.get_by_role('button',name='保存本次反馈',exact=True).click();page.get_by_role('button',name='生成候选并回放',exact=True).click();page.get_by_role('button',name='本地启用',exact=True).click()
  page.get_by_role('button',name='学习与问答',exact=True).click();page.fill('#ask-question','发行排期');page.click('#ask-submit');page.wait_for_selector('#ask-result .source');assert page.evaluate('window.jinshuTest.getState().traces.at(-1).topK')==8
  page.get_by_role('button',name='反馈与策略',exact=True).click();page.screenshot(path=str(out/'lite-loop.png'),full_page=True);page.get_by_role('button',name='回滚稳定基线',exact=True).click();assert page.evaluate("window.jinshuTest.getState().candidates.at(-1).status")=='rolled_back'
  report['checks']['feedback_replay_deploy_rollback']=True
  for name in ['执行记录','记忆工作台','回放与评测','体验记录','原理与部署']:
   page.get_by_role('button',name=name,exact=True).click();assert page.locator('#content').inner_text()
  report['checks']['all_nine_panels']=True
  page.set_viewport_size({'width':390,'height':844});page.get_by_role('button',name='学习与问答',exact=True).click();page.screenshot(path=str(out/'lite-mobile.png'),full_page=True)
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+2')
  report['checks']['mobile_no_horizontal_overflow']=True
  assert not report['errors'];report['status']='passed'
 except Exception as e:
  report['status']='failed';report['failure']=str(e);page.screenshot(path=str(out/'failure.png'),full_page=True);raise
 finally:
  (out/'browser-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));b.close()
