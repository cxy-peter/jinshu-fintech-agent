"""Unified runtime contracts; fixtures injected ONLY by tests, never by deployment."""
import asyncio,copy,io,json,zipfile
import pytest,httpx
from unified.app import create_app
from unified import config
from unified.tasks import TaskService,Conflict,render_export
from unified.tools import execute,dispatch,REQUIRED_PARAMS
from unified.documents import UnifiedParser,check_container,page_blocks
from jinshu.runtime import Runtime
from jinshu import tools
class MemoryTasks:
 def __init__(self):self.rows={}
 async def insert(self,row):self.rows[row['_id']]=copy.deepcopy(row)
 async def get(self,id,owner):
  row=self.rows.get(id);return copy.deepcopy(row) if row and row['owner']==owner else None
 async def change(self,id,owner,revision,row):
  old=await self.get(id,owner)
  if not old or old['revision']!=revision:raise Conflict('stale')
  self.rows[id]=copy.deepcopy(row)
 async def list(self,owner):return [copy.deepcopy(r) for r in self.rows.values() if r['owner']==owner]
@pytest.fixture
async def client():
 r=await Runtime().initialize();app=create_app(r,MemoryTasks())
 async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as c:
  c.runtime=r;yield c
 await r.close()
async def headers(c,name='editor'):
 res=await c.post('/api/login',json={'username':name,'password':'demo-'+name});assert res.status_code==200,res.text
 return {'Authorization':'Bearer '+res.json()['token']}
async def test_missing_configuration_is_not_a_demo(monkeypatch):
 for k in config.REQUIRED:monkeypatch.delenv(k,raising=False)
 async with httpx.AsyncClient(transport=httpx.ASGITransport(create_app()),base_url='http://localhost') as c:
  assert (await c.get('/')).status_code==200
  status=(await c.get('/api/status')).json();assert not status['configured'] and status['mode']=='complete_server'
  assert (await c.post('/api/ask',json={'query':'发行排期'})).status_code==503
  assert (await c.get('/ready')).status_code==503
@pytest.mark.parametrize('path',['/api/catalog','/api/tasks','/api/documents','/api/traces','/api/loop','/api/memory/x'])
async def test_no_unauthenticated_workspace(client,path):assert (await client.get(path)).status_code==401
async def test_http_uses_original_harness_and_trace(client):
 h=await headers(client,'operations');res=await client.post('/api/ask',headers=h,json={'query':'发行排期需要什么','workflow':'issuance'})
 assert res.status_code==200,res.text
 d=res.json();assert d['trace_id'] and d['execution']['profile']=='offline'
 assert d['tool_results'][0]['executed'] is False
 t=await client.get('/api/traces/'+d['trace_id'],headers=h);assert t.status_code==200 and t.json()['query']=='发行排期需要什么'
 bad=await headers(client,'risk');assert (await client.get('/api/traces/'+d['trace_id'],headers=bad)).status_code==403
 assert (await client.post('/api/ask',headers=bad,json={'query':'发行排期','workflow':'issuance','session_id':d['session_id']})).status_code==403
@pytest.mark.parametrize('tool',REQUIRED_PARAMS)
def test_eight_tools_are_actual_functions(tool):
 r=execute(tool,{},examples=True);assert r['tool']==tool and r['result']['rows'];assert r['input_mode']=='synthetic_example' and r['business_action_executed'] is False
@pytest.mark.parametrize('tool',REQUIRED_PARAMS)
def test_no_implicit_synthetic_input(tool):
 with pytest.raises(ValueError):execute(tool,{})
 assert dispatch(tool,{})['executed'] is False

def test_user_sources_override_deterministic_functions_without_leakage():
 original=tools.rows('weekly_raw.csv');sources={'weekly_raw.csv':[{'登记编码':'000123','名称':'自有产品','规模万元':'1,200.50','区间收益率':'2.5%','数据日期':'2026-09-24'}]}
 r=execute('weekly_report',{},sources=sources);assert r['result']['rows'][0]['登记编码']=='000123' and not r['synthetic']
 assert tools.rows('weekly_raw.csv')==original and tools.INPUT_SOURCES.get() is None
async def test_task_ownership_versions_review_and_download(client):
 h=await headers(client);r=(await client.post('/api/tasks',headers=h,json={'tool':'issuance','values':{},'use_examples':True})).json();id=r['_id']
 assert (await client.get(f'/api/tasks/{id}/export?revision=1',headers=h)).status_code==409
 r=(await client.post(f'/api/tasks/{id}/execute',headers=h,json={'revision':1})).json();assert r['status']=='needs_review' and r['revision']==3
 assert (await client.post(f'/api/tasks/{id}/approve',headers=h,json={'revision':1})).status_code==409
 r=(await client.post(f'/api/tasks/{id}/approve',headers=h,json={'revision':3})).json();assert r['revision']==4
 result=await client.get(f'/api/tasks/{id}/export?revision=4&format=docx',headers=h);assert result.status_code==200 and zipfile.is_zipfile(io.BytesIO(result.content))
 h2=await headers(client,'reviewer');assert (await client.get(f'/api/tasks/{id}',headers=h2)).status_code==403
 edited=await client.put(f'/api/tasks/{id}',headers=h,json={'tool':'issuance','values':{'count':2},'use_examples':True,'revision':4});assert edited.status_code==200 and edited.json()['approval'] is None
 assert (await client.get(f'/api/tasks/{id}/export?revision=4',headers=h)).status_code==409
async def test_task_department_permission(client):
 h=await headers(client,'risk');assert (await client.post('/api/tasks',headers=h,json={'tool':'issuance','values':{},'use_examples':True})).status_code==403
async def test_late_computation_cannot_replace_edited_task():
 import threading
 entered=threading.Event();released=threading.Event()
 def runner(*a,**kw):entered.set();released.wait(5);return execute(*a,**kw)
 s=TaskService(MemoryTasks(),runner);r=await s.create('x','issuance',{},None,True);running=asyncio.create_task(s.run(r['_id'],'x',1));await asyncio.to_thread(entered.wait,3)
 await s.edit(r['_id'],'x',2,{'count':1},None,True);released.set()
 with pytest.raises(Conflict):await running
 latest=await s.read(r['_id'],'x');assert latest['status']=='draft' and latest['result'] is None
async def test_feedback_has_one_latest_rating(client):
 h=await headers(client,'operations');a=(await client.post('/api/ask',headers=h,json={'query':'发行排期','workflow':'issuance'})).json()
 for signal in ['down','up']:
  res=await client.post('/api/feedback',headers=h,json={'trace_id':a['trace_id'],'signal':signal});assert res.status_code==200,res.text
 rows=await client.runtime.c.store.find('feedback',{'user_id':'operations','kind':'explicit'});assert len(rows)==1 and rows[0]['signal']=='up'
async def test_document_upload_and_independent_review(client):
 h=await headers(client)
 res=await client.post('/api/documents/upload',headers=h,data={'dept_id':'dept_wealth','topic':'native-v8','version':'1','source_kind':'learning_reference'},files={'file':('learning.json',json.dumps({'pages':[{'page':12,'text':'统一服务资料。所有原文和来源在服务器保管。'*30}]}).encode(),'application/json')})
 assert res.status_code==200,res.text
 d=res.json();assert d['status']=='pending_review' and d['source_kind']=='learning_reference'
 review={'final_sensitivity':'internal','reason':'独立核对','external_allowed':False,'allowed_depts':['dept_wealth']}
 assert (await client.post('/api/documents/'+d['_id']+'/review',headers=h,json=review)).status_code==403
 h2=await headers(client,'reviewer');assert (await client.post('/api/documents/'+d['_id']+'/review',headers=h2,json=review)).status_code==200
 arch=await client.post('/api/documents/'+d['_id']+'/archive',headers=h2,json={'reason':'停用测试'});assert arch.status_code==200,arch.text
@pytest.mark.parametrize('name',['../bad.json','/absolute.json','x\\bad.json'])
def test_archive_path_rejected(name):
 b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:z.writestr(name,'{}')
 with pytest.raises(ValueError):check_container(b.getvalue(),'input.zip')
@pytest.mark.parametrize('data',[{'pages':[]},{'pages':[{'page':1,'text':'a'},{'page':1,'text':'b'}]},{'pages':[{'page':True,'text':'a'}]},{'pages':[{'page':2,'text':5}]}])
def test_invalid_json_pages(data):
 with pytest.raises(ValueError):page_blocks(data)
@pytest.mark.parametrize('ext',['.txt','.md','.json','.csv','.docx','.pdf','.zip'])
def test_native_formats(tmp_path,ext):
 p=tmp_path/('sample'+ext)
 if ext=='.pdf':
  from reportlab.pdfgen import canvas
  c=canvas.Canvas(str(p));c.drawString(60,750,'Native test source text.');c.save()
 elif ext=='.docx':
  from docx import Document
  d=Document();d.add_paragraph('Native Word source.');d.save(p)
 elif ext=='.json':p.write_text(json.dumps({'pages':[{'page':17,'text':'Native JSON source.'}]}))
 elif ext=='.zip':
  with zipfile.ZipFile(p,'w') as z:z.writestr('pages.json',json.dumps({'pages':[{'page':17,'text':'Native ZIP source.'}]}))
 elif ext=='.csv':p.write_text('code,amount\n000123,1\n')
 else:p.write_text('Source text for native parser.')
 doc=UnifiedParser().parse(p);assert doc.text
 if ext in {'.json','.zip'}:assert doc.blocks[0].page==17
async def test_origin_and_size(client):
 h=await headers(client)
 assert (await client.post('/api/tickets',headers={**h,'Origin':'https://evil.example'},json={'summary':'x'})).status_code==403
 assert (await client.post('/api/tickets',headers=h,content=b'x'*4_000_001)).status_code==413
async def test_setup_disabled_no_public_password(client):assert (await client.post('/api/setup/user',json={'username':'admin','password':'twelvecharacters'})).status_code==403
def test_config_never_returns_secrets():
 env={k:'secret-sentinel' for k in config.REQUIRED};env['VERCEL']='1';r=config.problems(env)
 assert 'secret-sentinel' not in json.dumps(r) and 'REDIS_ADDR' in r['invalid']
@pytest.mark.parametrize('value',['=cmd',' +1+2','@SUM(1)','-cmd'])
def test_csv_formula_injection(value):
 row={'result':{'result':{'rows':[{'name':value}]}}};raw,_=render_export(row,'csv');assert "'"+value in raw.decode()

async def test_zip_documents_keep_separate_source_identity(client):
 h=await headers(client);b=io.BytesIO()
 with zipfile.ZipFile(b,'w') as z:
  for n in ['a.json','b.json']:z.writestr(n,json.dumps({'pages':[{'page':1,'text':n+'说明，分别保留每个源文件的页码。'*25}]}))
 res=await client.post('/api/documents/upload',headers=h,data={'dept_id':'dept_wealth','topic':'multi-zip','version':'1','source_kind':'learning_reference'},files={'file':('notes.zip',b.getvalue(),'application/zip')})
 assert res.status_code==200,res.text
 docs=res.json()['documents'];assert len(docs)==2 and len({d['_id'] for d in docs})==2
 assert {d['source']['file_name'] for d in docs}=={'a.json','b.json'}
 assert all(d['status']=='pending_review' for d in docs)
