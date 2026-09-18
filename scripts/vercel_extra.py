"""Additional functional transitions on the real website; synthetic documents only."""
import io,json,zipfile,os
from pathlib import Path
from playwright.sync_api import sync_playwright
site=os.getenv('SITE','https://jinshu-workbench.vercel.app');out=Path('evidence/v6-extra');out.mkdir(parents=True,exist_ok=True)
r={'site':site,'scope':'real website functional transitions, no private data or live model','checks':{}}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);page=b.new_page(viewport={'width':1440,'height':1100},accept_downloads=True);page.on('dialog',lambda d:d.accept())
 try:
  page.goto(site,wait_until='networkidle');page.wait_for_selector('#ask-submit')
  page.get_by_role('button',name='记忆工作台',exact=True).click();page.locator('#content select').first.select_option('full');page.check('#pref-consent');page.get_by_role('button',name='保存偏好',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('偏好已保存')")
  page.reload();page.wait_for_selector('#ask-submit');assert page.evaluate('window.jinshuTest.getState().preferences.style')=='full';r['checks']['preference_saved_across_reload']=True
  page.evaluate('()=>window.jinshuTest.ask("商业银行的四个职能是什么","auto")');page.get_by_role('button',name='体验记录',exact=True).click();assert page.is_checked('#pilot-test');page.select_option('#pilot-phase','agent');page.check('#pilot-consent');page.check('#pilot-done');page.get_by_role('button',name='保存体验',exact=True).click();page.wait_for_function('window.jinshuTest.getState().pilot.length===1');assert page.evaluate('window.jinshuTest.getState().pilot[0].is_test') is True
  assert page.evaluate('Boolean(window.jinshuTest.getState().pilot[0].trace_id)');page.get_by_role('button',name='撤回并删除记录',exact=True).click();page.wait_for_function('window.jinshuTest.getState().pilot.length===0');r['checks']['pilot_test_default_trace_link_and_withdraw']=True
  page.get_by_role('button',name='业务工具',exact=True).click()
  content='登记编码,名称,规模万元,区间收益率,数据日期\n0009,模拟产品,"1,200",2%,2026-08-30\n'.encode('utf-8')
  page.set_input_files('#tool-csv',{'name':'synthetic.csv','mimeType':'text/csv','buffer':content});page.wait_for_function("document.getElementById('notice').textContent.includes('CSV')");page.click('#tool-run');assert '0009' in page.locator('#tool-output').inner_text();r['checks']['csv_upload_real_computation_leading_zero']=True
  for label in ['CSV导出','JSON导出']:
   with page.expect_download() as dl:page.get_by_role('button',name=label,exact=True).click()
   path=out/('tool.csv' if label.startswith('CSV') else 'tool.json');dl.value.save_as(str(path));assert path.stat().st_size>10
  r['checks']['csv_json_exports']=True
  page.get_by_role('button',name='资料与上传',exact=True).click();buf=io.BytesIO()
  fixture={'doc_id':'v6-synthetic','title':'演示资料A','content':'V6演示复核码为SYNTH-629。仅用于功能测试，不是任何真实业务规则。','page':7,'source_kind':'learning_reference'}
  with zipfile.ZipFile(buf,'w') as z:z.writestr('chunks.jsonl',json.dumps(fixture,ensure_ascii=False)+'\n')
  payload={'name':'synthetic-chunks.zip','mimeType':'application/zip','buffer':buf.getvalue()};page.set_input_files('#upload-file',payload);page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.get_by_role('button',name='本地启用',exact=True).wait_for();assert page.evaluate('window.jinshuTest.getState().docs[0].status')=='pending_review'
  page.get_by_role('button',name='本地启用',exact=True).click();page.get_by_role('button',name='本地停用',exact=True).wait_for();r['checks']['zip_chunks_import_and_publish']=True
  page.set_input_files('#upload-file',payload);page.get_by_role('button',name='解析并加入待审核',exact=True).click();page.wait_for_function("document.getElementById('notice').textContent.includes('解析完成')");assert page.evaluate('window.jinshuTest.getState().docs.length')==1;r['checks']['duplicate_file_dedup']=True
  page.get_by_role('button',name='学习与问答',exact=True).click();page.evaluate('()=>window.jinshuTest.ask("V6演示复核码是什么","finance_learning")');page.wait_for_selector('.original-quote');text=page.locator('.original-quote').first.inner_text();assert text==fixture['content'];r['checks']['uploaded_original_exact_quote_and_page']=True
  page.get_by_role('button',name='打开对应原文',exact=True).first.click();page.locator('#viewer[open]').wait_for();assert 'SYNTH-629' in page.locator('#viewer-body').inner_text();page.click('#close-viewer');r['checks']['source_viewer_opens_original']=True
  page.get_by_role('button',name='资料与上传',exact=True).click();page.get_by_role('button',name='本地停用',exact=True).click();page.get_by_role('button',name='本地启用',exact=True).wait_for();page.get_by_role('button',name='学习与问答',exact=True).click();page.evaluate('()=>window.jinshuTest.ask("SYNTH-629","finance_learning")');assert page.evaluate('window.jinshuTest.getState().traces.at(-1).sources.length')==0;r['checks']['archived_document_no_longer_answered']=True
  page.get_by_role('button',name='原理与部署',exact=True).click()
  with page.expect_download() as dl:page.get_by_role('button',name='导出完整工作区',exact=True).click()
  dl.value.save_as(str(out/'synthetic-workspace.json'));page.get_by_role('button',name='清空本浏览器数据',exact=True).click();page.wait_for_function('window.jinshuTest.getState().docs.length===0');r['checks']['workspace_export_and_clear']=True
  r['status']='passed'
 except Exception as e:r['status']='failed';r['error']=str(e);page.screenshot(path=str(out/'failure.png'),full_page=True);raise
 finally:(out/'result.json').write_text(json.dumps(r,ensure_ascii=False,indent=2));b.close()
