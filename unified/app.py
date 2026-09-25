"""Same complete ASGI application on uvicorn and Vercel; no browser RAG fallback."""
from __future__ import annotations
import asyncio,hashlib,hmac,json,os,re,sys,tempfile,uuid
from pathlib import Path
from typing import Literal
from contextlib import asynccontextmanager
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'engine/backend'))
from fastapi import FastAPI,Request,HTTPException,Depends,UploadFile,File,Form
from fastapi.responses import FileResponse,JSONResponse,Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel,Field,ConfigDict
from .runtime import RuntimeManager,RuntimeUnavailable
from .tasks import TaskService,MongoTasks,Conflict,Missing
from .tools import REQUIRED_PARAMS
from jinshu.api import create_app as original_app
from jinshu.fixtures import WORKFLOWS,DEPARTMENTS
class Body(BaseModel):model_config=ConfigDict(extra='forbid')
class TaskInput(Body):
 tool:str
 values:dict=Field(default_factory=dict)
 sources:dict|None=None
 use_examples:bool=False
class TaskEdit(TaskInput):revision:int=Field(ge=1)
class Revision(Body):revision:int=Field(ge=1)
class Login(Body):
 username:str=Field(min_length=1,max_length=80)
 password:str=Field(min_length=1,max_length=200)
class UserCreate(Login):
 role:Literal['student','admin']='student'
 dept_id:str=''
class Feedback(Body):
 trace_id:str
 signal:Literal['up','down','correction']='down'
 category:Literal['retrieval','intent','generation','knowledge_gap']='retrieval'
 expected_terms:list[str]=Field(default_factory=list,max_length=8)
 note:str=Field(default='',max_length=1000)

def create_app(runtime=None,task_repository=None):
 manager=RuntimeManager(runtime);backend=original_app('services',runtime=runtime)
 @asynccontextmanager
 async def lifespan(app):
  yield
  if manager.runtime is not None:await manager.runtime.close()
 app=FastAPI(title='金枢｜统一完整后端',version='8.0.0',lifespan=lifespan)
 from .body_limit import BodyLimitMiddleware
 app.add_middleware(BodyLimitMiddleware);app.state.manager=manager
 removed={'/','/health','/ready','/metrics','/api/login','/api/tickets','/api/tickets/{ticket_id}/retry','/api/operations','/api/outputs/{filename}','/api/documents/pdf','/api/feedback'}
 backend.router.routes=[r for r in backend.router.routes if getattr(r,'path',None) not in removed]
 async def rt():
  try:r=await manager.get()
  except RuntimeUnavailable as e:raise HTTPException(503,detail={'code':e.code,**manager.status()}) from None
  from .documents import UnifiedParser
  from .tools import dispatch
  r.c.documents.parser=UnifiedParser();r.c.skill_executor.tool_runner=dispatch;backend.state.runtime=r
  return r
 async def auth(request:Request):
  token=request.headers.get('authorization','')
  if not token.startswith('Bearer '):raise HTTPException(401,'请先登录；没有公开演示账号')
  r=await rt();uid=r.c.auth.verify_token(token[7:]);u=await r.c.auth.get_user(uid) if uid else None
  if not u:raise HTTPException(401,'账号或会话已过期')
  return u
 def departments(u):return [u['dept_id']] if u.get('dept_id') else list(DEPARTMENTS) if u['role']=='admin' else []
 async def admin(u=Depends(auth)):
  if u['role']!='admin':raise HTTPException(403,'需要管理/复核权限')
  return u
 async def global_admin(u=Depends(admin)):
  if u.get('dept_id'):raise HTTPException(403,'需要全局管理权限')
  return u
 async def tasks():
  r=await rt();return TaskService(task_repository or MongoTasks(r.c.mongo.db))
 def tool_access(tool,u):
  if tool not in REQUIRED_PARAMS:raise HTTPException(422,'未登记工具')
  if WORKFLOWS[tool]['dept'] not in departments(u):raise HTTPException(403,'无该工具部门权限')
 @app.middleware('http')
 async def guard(request,call_next):
  if request.method not in {'GET','HEAD','OPTIONS'}:
   origin=request.headers.get('origin');expected=str(request.base_url).rstrip('/');host=request.headers.get('host','')
   if origin and origin not in {expected,'https://'+host,'http://'+host if not os.getenv('VERCEL') else ''}:return JSONResponse({'detail':'跨站写入被拒绝'},403)
   try:size=int(request.headers.get('content-length','0'))
   except ValueError:return JSONResponse({'detail':'无效请求长度'},400)
   if size>4_000_000:return JSONResponse({'detail':'请求最多4MB；请拆分资料后上传'},413)
  if request.url.path.startswith('/api/') and request.url.path not in {'/api/status','/api/login','/api/setup/user'}:
   try:await rt()
   except HTTPException as e:return JSONResponse({'detail':e.detail},e.status_code)
  try:response=await call_next(request)
  except Exception as exc:response=JSONResponse({'detail':'服务请求失败，请复核输入与连接状态','error_type':type(exc).__name__},500)
  response.headers['X-Content-Type-Options']='nosniff';response.headers['X-Frame-Options']='DENY';response.headers['Referrer-Policy']='same-origin'
  if request.url.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
  return response
 @app.exception_handler(Conflict)
 async def conflict(request,e):return JSONResponse({'detail':str(e)},409)
 @app.exception_handler(Missing)
 async def missing(request,e):return JSONResponse({'detail':str(e)},403)
 @app.exception_handler(ValueError)
 async def invalid(request,e):return JSONResponse({'detail':str(e)[:500]},422)
 @app.exception_handler(PermissionError)
 async def permission(request,e):return JSONResponse({'detail':str(e)},403)
 @app.get('/')
 async def home():return FileResponse(ROOT/'unified/web/index.html')
 @app.get('/ready')
 async def ready():return JSONResponse(manager.status(),status_code=200 if manager.runtime is not None else 503)
 @app.get('/health')
 @app.get('/api/status')
 async def status():return manager.status()
 app.mount('/assets',StaticFiles(directory=ROOT/'unified/web'),name='assets')
 @app.post('/api/login')
 async def login(d:Login,request:Request):
  r=await rt()
  if r.profile=='services':
   redis=r.c.session_store.redis;key='jinshu:login:'+hashlib.sha256(d.username.strip().encode()).hexdigest()
   n=await redis.eval("local n=redis.call('INCR',KEYS[1]); if n==1 then redis.call('EXPIRE',KEYS[1],300) end; return n",1,key)
   if n>10:raise HTTPException(429,'尝试过多，5分钟后重试')
  u=await r.c.auth.authenticate(d.username,d.password)
  if not u:raise HTTPException(401,'用户名或密码不正确')
  if r.profile=='services':await redis.delete(key)
  return {'token':r.c.auth.issue_token(u['id']),'user':u,'departments':departments(u)}
 @app.post('/api/setup/user')
 async def setup(d:UserCreate,request:Request):
  secret=os.getenv('JINSHU_BOOTSTRAP_TOKEN','');supplied=request.headers.get('x-setup-token','')
  if len(secret)<32 or not hmac.compare_digest(secret,supplied):raise HTTPException(403,'初始化入口未授权')
  if len(d.password)<12 or not re.fullmatch(r'[A-Za-z0-9_-]{3,50}',d.username):raise HTTPException(422,'用户名3–50位字母数字；密码至少12位')
  if d.dept_id not in {'',*DEPARTMENTS}:raise HTTPException(422,'未知部门')
  if not d.dept_id and d.role!='admin':raise HTTPException(422,'普通成员必须分配部门')
  r=await rt();existing=await r.c.store.get('users',d.username)
  if existing:raise HTTPException(409,'账号已存在；初始化不能覆盖账号')
  from pymongo.errors import DuplicateKeyError
  try:await r.c.mongo.db['users'].insert_one(r.c.auth._to_user(d.model_dump()))
  except DuplicateKeyError:raise HTTPException(409,'账号已存在') from None
  return {'created':d.username,'note':'建立编辑与独立复核两个账号后，请删除部署中的JINSHU_BOOTSTRAP_TOKEN。'}
 @app.get('/api/tool-catalog')
 async def tool_catalog(u=Depends(auth)):
  from jinshu.tools import FILES
  return [{'tool':k,'name':WORKFLOWS[k]['name'],'required_params':v,'required_sources':FILES[k]} for k,v in REQUIRED_PARAMS.items() if WORKFLOWS[k]['dept'] in departments(u)]
 @app.get('/api/tool-examples/{tool}')
 async def tool_example(tool:str,u=Depends(auth)):
  tool_access(tool,u)
  from jinshu.tools import source,FILES
  return {'sources':{n:source(n) for n in FILES[tool]},'synthetic':True,'note':'仅项目合成示例，不是你的业务资料；点击示例执行才使用。'}
 @app.get('/api/tasks')
 async def list_tasks(u=Depends(auth)):
  svc=await tasks();rows=await svc.repo.list(u['id']);return [{k:v for k,v in r.items() if k not in {'sources'}} for r in rows]
 @app.post('/api/tasks')
 async def create_task(d:TaskInput,u=Depends(auth)):
  tool_access(d.tool,u);svc=await tasks();return await svc.create(u['id'],d.tool,d.values,d.sources,d.use_examples)
 @app.get('/api/tasks/{id}')
 async def get_task(id:str,u=Depends(auth)):
  svc=await tasks();return await svc.read(id,u['id'])
 @app.put('/api/tasks/{id}')
 async def edit_task(id:str,d:TaskEdit,u=Depends(auth)):
  tool_access(d.tool,u);svc=await tasks();row=await svc.read(id,u['id'])
  if row['tool']!=d.tool:raise HTTPException(422,'不可改变既有任务类型')
  return await svc.edit(id,u['id'],d.revision,d.values,d.sources,d.use_examples)
 @app.post('/api/tasks/{id}/execute')
 async def execute_task(id:str,d:Revision,u=Depends(auth)):
  svc=await tasks();row=await svc.read(id,u['id']);tool_access(row['tool'],u);return await svc.run(id,u['id'],d.revision)
 @app.post('/api/tasks/{id}/approve')
 async def approve_task(id:str,d:Revision,u=Depends(auth)):
  svc=await tasks();row=await svc.read(id,u['id']);tool_access(row['tool'],u);return await svc.approve(id,u['id'],d.revision)
 @app.get('/api/tasks/{id}/export')
 async def export_task(id:str,revision:int,format:Literal['json','csv','docx']='json',u=Depends(auth)):
  svc=await tasks();row=await svc.read(id,u['id']);tool_access(row['tool'],u);content,kind=await svc.export(id,u['id'],revision,format)
  return Response(content,media_type=kind,headers={'Content-Disposition':f'attachment; filename="jinshu-{id}.{format}"','Cache-Control':'no-store'})
 @app.post('/api/documents/upload')
 async def upload(file:UploadFile=File(...),dept_id:str=Form(...),topic:str=Form(...),version:int=Form(1),manual_sensitivity:str=Form('internal'),source_kind:Literal['institutional_document','learning_reference','research_reference','synthetic']=Form('institutional_document'),u=Depends(admin)):
  if dept_id not in departments(u):raise HTTPException(403,'不是授权部门')
  if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',topic) or not 1<=version<=10000:raise HTTPException(422,'主题需英文/数字编码；版本1至10000')
  raw=await file.read(3_500_001)
  if len(raw)>3_500_000:raise HTTPException(413,'单文件最多3.5MB，请拆分后上传')
  from .documents import check_container
  name=Path(file.filename or 'upload.txt').name;check_container(raw,name);r=await rt()
  with tempfile.TemporaryDirectory() as tmp:
   p=Path(tmp)/name;p.write_bytes(raw);doc=await r.c.documents.stage_file(p,dept_id,u['id'],topic,version,manual_sensitivity)
  await r.c.store.update_document(doc['_id'],{'source_kind':source_kind,'synthetic':source_kind=='synthetic'})
  return await r.c.store.get_document(doc['_id'])
 @app.post('/api/documents/{did}/archive')
 async def archive(did:str,request:Request,u=Depends(admin)):
  d=await request.json();reason=str(d.get('reason','')).strip()
  if not reason or len(reason)>500:raise HTTPException(422,'请填写停用理由，500字以内')
  r=await rt();doc=await r.c.store.get_document(did)
  if not doc or doc['dept_id'] not in departments(u):raise HTTPException(403,'无权停用')
  await r.c.store.update_document(did,{'status':'archived','archived_by':u['id'],'archive_reason':reason})
  if r.profile=='services':await r.c.mongo.db['corpus_revisions'].update_one({'_id':'global'},{'$inc':{'revision':1}},upsert=True)
  for c in await r.c.store.list_chunks_by_doc(did):r.c.bm25.remove(c['_id'])
  await r.c.organization_memory.invalidate_document(did,'document_archived')
  return {'status':'archived','doc_id':did,'note':'原文与审核留痕保留，后续查询不再作为活动依据。'}
 @app.post('/api/feedback')
 async def feedback(d:Feedback,u=Depends(auth)):
  r=await rt();t=await r.c.store.get('traces',d.trace_id)
  if not t or t['user_id']!=u['id']:raise HTTPException(403,'只能反馈自己的任务')
  fid='feedback_'+hashlib.sha256((u['id']+':'+d.trace_id).encode()).hexdigest()
  await r.c.store.upsert('feedback',{'_id':fid,'session_id':t['session_id'],'user_id':u['id'],'query':t['query'],'answer':t['answer'],'signal':d.signal,'kind':'explicit','consumed':False,'detail':{'trace_id':d.trace_id,'workflow':t.get('workflow'),**d.model_dump(exclude={'trace_id','signal'})},'created_at':__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat()})
  for ex in await r.c.store.find('strategy_executions',{'trace_id':d.trace_id}):
   ex.update(quality_success=d.signal=='up',quality_source='explicit_user_feedback');await r.c.store.upsert('strategy_executions',ex)
  return {'id':fid,'status':'recorded','note':'更新同一回答的反馈；无反馈不视为解决。'}
 @app.post('/api/jobs/process')
 async def process_jobs(u=Depends(global_admin)):
  r=await rt();redis=r.c.session_store.redis;owner=uuid.uuid4().hex;key='jinshu:v8:worker-lease'
  if not await redis.set(key,owner,nx=True,ex=240):raise HTTPException(409,'已有处理请求；请查看作业状态')
  try:
   await asyncio.wait_for(r.process_jobs(),180);return {'status':'processed_one_batch','jobs':await r.c.store.find('async_jobs',limit=20)}
  except asyncio.TimeoutError:raise HTTPException(504,'处理预算耗尽；作业状态保留，稍后可重试。') from None
  finally:await redis.eval("if redis.call('GET',KEYS[1])==ARGV[1] then return redis.call('DEL',KEYS[1]) end return 0",1,key,owner)
 @app.post('/api/tickets')
 async def ticket(request:Request,u=Depends(auth)):
  d=await request.json();summary=str(d.get('summary','')).strip()
  if not summary or len(summary)>2000:raise HTTPException(422,'工单摘要1–2000字')
  r=await rt();key=hashlib.sha256((u['id']+summary).encode()).hexdigest()
  await r.c.store.upsert('ticket_outbox',{'_id':key,'owner':u['id'],'summary':summary,'status':'pending_submission','note':'没有真实工单服务回执，不宣称已发送。'})
  return await r.c.store.get('ticket_outbox',key)
 @app.post('/api/tickets/{ticket_id}/retry')
 async def retry_ticket(ticket_id:str,u=Depends(auth)):
  r=await rt();t=await r.c.store.get('ticket_outbox',ticket_id)
  if not t or t['owner']!=u['id']:raise HTTPException(403,'无权访问工单')
  return {**t,'provider_request_sent':False,'note':'尚未配置真实工单连接；记录保留待人工处理。'}
 @app.get('/api/operations')
 async def operations(u=Depends(global_admin)):
  r=await rt();return {'recovery':await r.c.store.find('strategy_controls'),'tickets':await r.c.store.find('ticket_outbox'),'scope':'shared_mongodb'}
 @app.post('/api/connection-check')
 async def check_services(u=Depends(admin)):
  from jinshu.live import ping_runtime
  return await ping_runtime(await rt())
 @app.post('/api/model-check')
 async def check_model(request:Request,u=Depends(admin)):
  if (await request.json()).get('consent') is not True:raise HTTPException(422,'此检查会调用配置模型，请明确同意')
  r=await rt()
  from jinshu.context import run_state
  token=run_state.set({'models_enabled':True,'allow_external':True})
  try:
   from app.llm.client import ChatMessage
   answer=await r.c.llm.complete([ChatMessage.user('这是公开的连接测试。请仅回答：连接成功。')],max_tokens=32)
   return {'model_called':True,'answer':answer,'calls':run_state.get().get('model_calls',[]),'scope':'仅生成接口连接测试，不是完整RAG质量验收'}
  finally:run_state.reset(token)
 # All remaining original APIs use this SAME Runtime; no duplicate browser computation.
 app.mount('/',backend)
 return app
app=create_app()
