"""Financial workbench on the original Harness, Loop, memories, stores and authentication."""
from __future__ import annotations
import asyncio,json,os,secrets,tempfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from fastapi import FastAPI,Depends,Header,HTTPException,Request,UploadFile,File,Form
from fastapi.responses import FileResponse,JSONResponse,Response
from pydantic import BaseModel,Field
from prometheus_client import generate_latest,CONTENT_TYPE_LATEST
from app.utils.metrics import DEPT_AGENT_INFLIGHT
from .runtime import Runtime
from .fixtures import DEPARTMENTS,WORKFLOWS,DATA
from . import ROOT

class Login(BaseModel):
 username:str=Field(min_length=1,max_length=80)
 password:str=Field(min_length=1,max_length=200)
class Ask(BaseModel):
 query:str=Field(min_length=1,max_length=2000)
 workflow:str|None=None
 session_id:str=Field(default='',max_length=150)
 params:dict=Field(default_factory=dict)
 allow_external:bool=False
class Feedback(BaseModel):
 trace_id:str
 signal:Literal['up','down','correction','copy','follow_up']='down'
 category:Literal['retrieval','intent','generation','knowledge_gap']='retrieval'
 expected_terms:list[str]=Field(default_factory=list,max_length=8)
 note:str=Field(default='',max_length=1000)
class Document(BaseModel):
 title:str=Field(min_length=1,max_length=100)
 topic:str=Field(min_length=1,max_length=100,pattern=r'^[A-Za-z0-9_\-]+$')
 version:int=Field(ge=1,le=10000)
 dept_id:str
 body:str=Field(min_length=1,max_length=100000)
 effective_date:str|None=None
 manual_sensitivity:Literal['public','internal','restricted','sensitive']='internal'
class Review(BaseModel):
 final_sensitivity:Literal['public','internal','restricted','sensitive']='internal'
 allowed_depts:list[str]=Field(default_factory=list)
 external_allowed:bool=False
 reason:str=Field(min_length=1,max_length=500)
class Rollback(BaseModel):
 skill_id:str
 reason:str='人工请求暂停当前候选'
 simulate_failure:bool=False
class Ticket(BaseModel):
 session_id:str
 summary:str=Field(min_length=1,max_length=2000)
class Preference(BaseModel):
 key:str
 value:str=Field(max_length=120)
 consent:bool=False
class OrgMemo(BaseModel):
 title:str=Field(max_length=100)
 content:str=Field(max_length=1000)
 chunk_id:str


def create_app(profile='offline',runtime=None):
 @asynccontextmanager
 async def lifespan(app):
  r=runtime or Runtime(profile)
  await r.initialize();app.state.runtime=r
  if profile=='offline' or os.getenv('JINSHU_EMBEDDED_WORKER')=='1':
   r.worker_task=asyncio.create_task(r.worker())
  yield
  await r.close()
 app=FastAPI(title='金枢｜金融产品中后台自进化 Agent',version='3.1.0',lifespan=lifespan)
 def rt():return app.state.runtime
 async def auth(authorization:str|None=Header(default=None)):
  if not authorization or not authorization.startswith('Bearer '):raise HTTPException(401,'请先登录')
  uid=rt().c.auth.verify_token(authorization[7:])
  if not uid:raise HTTPException(401,'身份无效或已过期')
  u=await rt().c.auth.get_user(uid)
  if not u:raise HTTPException(401,'用户不存在')
  return u
 def depts(u):return [u['dept_id']] if u.get('dept_id') else list(DEPARTMENTS) if u['role']=='admin' else []
 async def admin(u=Depends(auth)):
  if u['role']!='admin':raise HTTPException(403,'需要管理员/复核员')
  return u
 async def global_admin(u=Depends(admin)):
  if u.get('dept_id'):raise HTTPException(403,'需要全局实验管理员')
  return u
 @app.exception_handler(ValueError)
 async def value_err(req,e):return JSONResponse(status_code=422,content={'detail':str(e)})
 @app.exception_handler(PermissionError)
 async def permission_err(req,e):return JSONResponse(status_code=403,content={'detail':str(e)})
 @app.get('/')
 def index():return FileResponse(ROOT/'static'/'index.html')
 @app.get('/health')
 def health():return {'status':'ok','profile':rt().profile,'synthetic':True,'note':'offline uses original in-memory stores/hash vectors, not learned semantic models'}
 @app.get('/metrics')
 def metrics():return Response(generate_latest(),media_type=CONTENT_TYPE_LATEST)
 @app.post('/api/login')
 async def login(data:Login,request:Request):
  limiter=rt().c.login_limiter;key=(request.client.host if request.client else 'unknown')+':'+data.username
  if not limiter.check(key):raise HTTPException(429,'尝试过多，请稍后再试')
  user=await rt().c.auth.authenticate(data.username,data.password)
  if not user:limiter.hit(key);raise HTTPException(401,'用户名或口令不正确')
  limiter.clear(key);return {'token':rt().c.auth.issue_token(user['id']),'user':user,'departments':depts(user)}
 @app.get('/api/catalog')
 async def catalog(u=Depends(auth)):
  return {'workflows':{k:v for k,v in WORKFLOWS.items() if v['dept'] in depts(u)},'departments':DEPARTMENTS,'profile':rt().profile,'documents':await rt().c.store.count('documents'),'chunks':await rt().c.store.count('chunks'),'synthetic':True,'python_skills':__import__('jinshu.python_skills',fromlist=['catalog']).catalog()}
 @app.post('/api/ask')
 async def ask(q:Ask,u=Depends(auth)):
  label=WORKFLOWS.get(q.workflow or '',{}).get('dept','auto')
  DEPT_AGENT_INFLIGHT.labels(dept=label).inc()
  try:return await rt().ask(**q.model_dump(),user_id=u['id'],allowed=depts(u),clearance='sensitive' if u['role']=='admin' else 'internal')
  finally:DEPT_AGENT_INFLIGHT.labels(dept=label).dec()
 @app.get('/api/traces')
 async def traces(u=Depends(auth)):return await rt().c.store.find('traces',{'user_id':u['id']},limit=30)
 @app.get('/api/traces/{tid}')
 async def trace(tid:str,u=Depends(auth)):
  t=await rt().c.store.get('traces',tid)
  if not t or t['user_id']!=u['id']:raise HTTPException(403,'无权访问执行记录')
  return t
 @app.post('/api/feedback')
 async def feedback(f:Feedback,u=Depends(auth)):
  await rt().feedback(tid=f.trace_id,user_id=u['id'],**f.model_dump(exclude={'trace_id'}));return {'status':'observed','note':'归因与回放将进入Loop，不直接修改线上策略'}
 @app.get('/api/loop')
 async def loop_state(u=Depends(global_admin)):
  return {'skills':await rt().c.store.list_skills(),'hooks':await rt().c.store.list_hooks(),'rules':await rt().c.store.list_rules(),'experiments':await rt().c.store.find('experiments'),'versions':await rt().c.store.find('strategy_versions'),'jobs':await rt().c.store.find('async_jobs'),'knowledge_gaps':await rt().c.store.find('knowledge_tickets'),'feedback':await rt().c.feedback_collector.stats()}
 @app.post('/api/loop/run')
 async def loop_run(u=Depends(global_admin)):return await rt().c.job_queue.enqueue('loop',{'requested_by':u['id']})
 @app.post('/api/skills/{sid}/approve')
 async def approve(sid:str,u=Depends(global_admin)):return await rt().c.loop_engine.approve(sid,u['id'])
 @app.post('/api/skills/{sid}/promote')
 async def promote(sid:str,u=Depends(global_admin)):return await rt().c.loop_engine.promote(sid,u['id'])
 @app.get('/api/skills/{sid}/metrics')
 async def skill_metrics(sid:str,u=Depends(global_admin)):return await rt().c.loop_engine.metrics(sid)
 @app.post('/api/loop/lab')
 async def lab(u=Depends(global_admin)):
  if rt().profile!='offline':raise HTTPException(403,'实验室仅开放离线模拟模式')
  from .demo import run_loop_lab
  return await run_loop_lab()
 @app.get('/api/documents')
 async def documents(u=Depends(auth)):
  ds=await rt().c.store.list_documents()
  
  from .document_service import can_read
  who={'departments':depts(u),'clearance':'sensitive' if u['role']=='admin' else 'internal'}
  return [d for d in ds if d['dept_id'] in depts(u) and (u['role']=='admin' or (d['status']=='active' and can_read(d,who)))]
 @app.get('/api/documents/{did}/chunks')
 async def chunks(did:str,u=Depends(auth)):
  d=await rt().c.store.get_document(did)
  from .document_service import can_read
  if not d or d['dept_id'] not in depts(u) or (u['role']!='admin' and (d['status']!='active' or not can_read(d,{'departments':depts(u),'clearance':'internal'}))):raise HTTPException(403,'无权限/未生效资料')
  return await rt().c.store.list_chunks_by_doc(did)
 @app.post('/api/documents')
 async def import_document(d:Document,u=Depends(admin)):
  if d.dept_id not in depts(u):raise HTTPException(403,'部门不允许')
  if d.effective_date:
   from datetime import date;date.fromisoformat(d.effective_date)
  # The API never accepts a filesystem path or arbitrary URL. Uploaded text is not executable.
  with tempfile.TemporaryDirectory() as td:
   p=Path(td)/'upload.md';p.write_text('# '+d.title+'\n\n'+d.body,encoding='utf-8')
   return await rt().c.documents.stage_file(p,d.dept_id,u['id'],d.topic,d.version,d.manual_sensitivity,d.effective_date)
 @app.post('/api/documents/{did}/publish')
 async def publish(did:str,u=Depends(admin)):
  d=await rt().c.store.get_document(did)
  if d and d.get('review_required'):raise HTTPException(422,'请填写最终敏感级别和审核理由，再通过review接口发布')
  return await rt().c.indexer.publish(did,u['id'],depts(u))
 @app.get('/api/memory/{session_id}')
 async def memory(session_id:str,u=Depends(auth)):
  owner=await rt().c.store.get('session_owners',session_id)
  if not owner or owner['user_id']!=u['id']:raise HTTPException(403,'会话不属于你')
  return {'working':await rt().c.working_memory.get_context(session_id),'episodic':await rt().c.store.find('conversation_events',{'session_id':session_id,'user_id':u['id']},limit=20),
   'user_semantic':await rt().c.user_semantic_memory.recall(u['id']),
   'organization':[x for x in await rt().c.store.find('org_memory_items') if x.get('dept_id') in depts(u)],
   'procedural':[s for s in await rt().c.store.list_skills() if s['dept_id'] in depts(u)]}
 @app.post('/api/memory/preferences')
 async def pref(p:Preference,u=Depends(auth)):return await rt().c.user_semantic_memory.remember(u['id'],p.key,p.value,consent=p.consent,actor_id=u['id'])
 @app.delete('/api/memory/preferences/{mid}')
 async def forget(mid:str,u=Depends(auth)):return {'deleted':await rt().c.user_semantic_memory.forget(u['id'],mid,u['id'])}
 @app.post('/api/memory/organization')
 async def org(o:OrgMemo,u=Depends(admin)):
  c=await rt().c.store.get('chunks',o.chunk_id)
  if not c or c['dept_id'] not in depts(u):raise HTTPException(403,'无权使用该来源')
  d=await rt().c.store.get_document(c['doc_id'])
  return await rt().c.organization_memory.publish('department','faq',o.title,o.content,[{'doc_id':c['doc_id'],'chunk_id':o.chunk_id,'document_version':d['version']}],dept_id=c['dept_id'],access_scope=['staff','student','admin'],actor_id=u['id'])

 @app.post('/api/documents/pdf')
 async def upload_pdf(file:UploadFile=File(...),dept_id:str=Form(...),topic:str=Form(...),version:int=Form(1),manual_sensitivity:str=Form('internal'),u=Depends(admin)):
  if dept_id not in depts(u):raise HTTPException(403,'不是授权部门')
  raw=await file.read(10_000_001)
  if len(raw)>10_000_000 or not raw.startswith(b'%PDF-'):raise HTTPException(422,'请上传10MB以内原生PDF')
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/Path(file.filename or 'upload.pdf').name;p.write_bytes(raw)
   return await rt().c.documents.stage_file(p,dept_id,u['id'],topic,version,manual_sensitivity)
 @app.post('/api/documents/{did}/review')
 async def review(did:str,d:Review,u=Depends(admin)):
  return await rt().c.documents.review_and_publish(did,u['id'],depts(u),**d.model_dump())
 @app.post('/api/demo/load-pdfs')
 async def load_pdf(u=Depends(global_admin)):
  if rt().profile!='offline':raise HTTPException(403,'只用于离线样例')
  from .mock_pdfs import generate,OUT
  result=[]
  for d in generate():
   try:r=await rt().c.documents.stage_file(OUT/d['file'],d['dept_id'],u['id'],d['topic'],d['version'],d['manual_sensitivity']);result.append(r)
   except ValueError as exc:result.append({'file':d['file'],'status':'already_loaded','detail':str(exc)})
  return {'documents':result,'note':'已本地解析；待另一审核人确认后建共享索引，不是上传即公开。'}
 @app.post('/api/documents/{did}/reject')
 async def reject_document(did:str,request:Request,u=Depends(admin)):
  d=await rt().c.store.get_document(did)
  if not d or d['dept_id'] not in depts(u):raise HTTPException(403,'无审核权限')
  if d['source']['uploaded_by']==u['id']:raise HTTPException(403,'由另一位审核人处理')
  if d['status']!='pending_review':raise HTTPException(422,'只处理待审核资料')
  reason=str((await request.json()).get('reason','')).strip()
  if not reason:raise HTTPException(422,'请填写退回理由')
  await rt().c.store.update_document(did,{'status':'returned','reviewed_by':u['id'],'review_reason':reason})
  return await rt().c.store.get_document(did)
 @app.post('/api/operations/lab')
 async def recovery_lab(u=Depends(global_admin)):
  if rt().profile!='offline':raise HTTPException(403,'仅离线实验')
  import copy,uuid
  from .operations import RecoveryController
  isolated=await Runtime(instance_id='recovery-lab-'+uuid.uuid4().hex[:10]).initialize()
  try:
   candidate=copy.deepcopy(await isolated.c.store.get_skill('base_issuance'))
   candidate.update(_id='local-lab-candidate',version=2,experiment_id='local-lab-exp',gray_percent=1)
   for step in candidate['action']['steps']:
    if step['action']=='retrieve':step['params']['top_k']=8
   await isolated.c.store.upsert_skill(candidate)
   before=await isolated.ask('发行排期',user_id='operations',workflow='issuance')
   async def failure():raise ConnectionError('模拟控制API失败')
   result=await isolated.recovery.rollback('issuance',candidate['_id'],failure,'隔离故障演示')
   after=await isolated.ask('发行排期',user_id='operations',workflow='issuance')
   return {'before_top_k':before['execution']['skill_plan']['top_k'],'after_top_k':after['execution']['skill_plan']['top_k'], 'result':result,'restart_keeps_freeze':RecoveryController(isolated.recovery.path.parent).frozen('issuance'),'scope':'isolated single-instance demo, not distributed rollback'}
  finally:await isolated.close()
 @app.get('/api/operations')
 async def operations(u=Depends(global_admin)):
  return {'recovery':rt().recovery.state,'tickets':rt().outbox.list(),'scope':'当前实例；非跨Pod一致性'}
 @app.post('/api/operations/rollback')
 async def rollback(d:Rollback,u=Depends(global_admin)):
  s=await rt().c.store.get_skill(d.skill_id)
  if not s or not s.get('experiment_id'):raise HTTPException(422,'选择有实验ID的候选，不是稳定基线')
  if d.simulate_failure and rt().profile!='offline':raise HTTPException(403,'只允许离线模拟接口故障')
  async def remote():
   if d.simulate_failure:raise ConnectionError('模拟控制接口不可用')
   s.update(status='rolled_back',gray_percent=0);await rt().c.store.upsert_skill(s)
   exp=await rt().c.store.get('experiments',s['experiment_id'])
   if exp:
    exp.update(status='rolled_back',rollback_reason=d.reason);await rt().c.store.upsert('experiments',exp)
  return await rt().recovery.rollback(s['family'],s['_id'],remote,d.reason)
 @app.post('/api/operations/resume/{family}')
 async def resume(family:str,u=Depends(global_admin)):
  return rt().recovery.resume(family,u['id'])
 @app.post('/api/tickets')
 async def tickets(d:Ticket,u=Depends(auth)):
  draft=rt().outbox.draft(u['id']+':'+d.session_id,d.summary)
  return await rt().outbox.submit(draft)
 @app.post('/api/tickets/{ticket_id}/retry')
 async def retry_ticket(ticket_id:str,u=Depends(global_admin)):
  row=next((x for x in rt().outbox.list() if x['id']==ticket_id),None)
  if not row:raise HTTPException(404,'待办不存在')
  return await rt().outbox.submit(row)
 @app.get('/api/outputs/{filename}')
 async def output(filename:str,u=Depends(auth)):
  if 'dept_release' not in depts(u):raise HTTPException(403,'发行部门材料')
  if not __import__('re').fullmatch(r'issuance-[a-f0-9]{20}\.docx',filename):raise HTTPException(404,'材料不存在')
  p=ROOT/'workspace'/'outputs'/filename
  if not p.exists():raise HTTPException(404,'材料尚未生成')
  return FileResponse(p,filename=filename)
 @app.get('/diagrams/{filename}')
 async def diagram(filename:str):
  if '/' in filename or '..' in filename or Path(filename).suffix not in {'.svg','.png'}:raise HTTPException(404)
  p=ROOT/'diagrams'/filename
  if not p.exists():raise HTTPException(404)
  return FileResponse(p)
 return app
app=create_app(os.getenv('JINSHU_PROFILE','offline'))
