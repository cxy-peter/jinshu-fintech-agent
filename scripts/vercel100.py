"""Actual website browser execution; labels stay in test harness and never feed QA prompts."""
import json,os,time,hashlib
from pathlib import Path
from playwright.sync_api import sync_playwright
site=os.getenv('SITE','https://jinshu-workbench.vercel.app');out=Path('evidence/v6');out.mkdir(parents=True,exist_ok=True)
cases=json.loads(Path('lite/web/benchmark100.json').read_text());report={'site':site,'scope':'actual deployed website, no model API requested, self-authored development acceptance','real_users':0,'rows':[]}
with sync_playwright() as p:
 browser=p.chromium.launch(headless=True);page=browser.new_page(viewport={'width':1440,'height':1100},accept_downloads=True);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
 try:
  page.goto(site,wait_until='networkidle');page.wait_for_selector('#ask-submit');r=page.request.get(site+'/build-info.json');report['build']=r.json();assert report['build']['version']=='6.0.0','Vercel has not served V6 yet'
  report['served_hashes']={}
  for path in ['app.mjs','core.mjs','assurance.mjs','knowledge.json','benchmarking.mjs']:
   r=page.request.get(site+'/'+path);assert r.ok;report['served_hashes'][path]=hashlib.sha256(r.body()).hexdigest()
  # Execute the actual app ask function, including its routing, memory, persistence and tool integration.
  for c in cases['rows']:
   page.get_by_role('button',name='新会话',exact=True).click()
   if c.get('previous'):page.evaluate('q=>window.jinshuTest.ask(q,"auto")',c['previous'])
   page.evaluate('q=>window.jinshuTest.ask(q,"auto")',c['question'])
   scored=page.evaluate('''async c=>{const {scoreCase}=await import('/benchmarking.mjs');return scoreCase(c,window.jinshuTest.getState().traces.at(-1),window.jinshuTest.index);}''',c)
   report['rows'].append(scored)
  report['summary']=page.evaluate('''async rows=>{const {summarize}=await import('/benchmarking.mjs');return summarize(rows);}''',report['rows'])
  page.evaluate('()=>window.jinshuTest.ask("商业银行的四个职能是什么？","auto")');page.screenshot(path=str(out/'vercel-cited-answer.png'),full_page=True)
  assert page.locator('.evidence-reference').count()>0
  assert page.locator('.original-quote').count()>0
  page.get_by_role('button',name='回放与评测',exact=True).click();page.get_by_role('button',name='运行100题带出处验收',exact=True).click();page.get_by_role('button',name='导出100题答案、原文与出处',exact=True).wait_for()
  with page.expect_download() as d:page.get_by_role('button',name='导出100题答案、原文与出处',exact=True).click()
  d.value.save_as(str(out/'website-export100.json'));page.screenshot(path=str(out/'vercel-benchmark100.png'),full_page=True)
  report['errors']=errors;assert not errors;assert report['summary']['criterion_passed'];report['status']='passed'
 except Exception as e:
  report['status']='failed';report['error']=str(e);page.screenshot(path=str(out/'vercel-failure.png'),full_page=True);raise
 finally:
  (out/'vercel100.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));browser.close()
