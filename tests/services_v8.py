"""Real Mongo/Redis/Milvus + controlled HTTP model protocol. NOT model-quality evidence."""
import asyncio,hashlib,json,os,threading,uuid
from http.server import ThreadingHTTPServer,BaseHTTPRequestHandler
from pathlib import Path
import httpx
checks=[];calls=[]
class Provider(BaseHTTPRequestHandler):
 def log_message(self,*a):pass
 def do_POST(self):
  data=json.loads(self.rfile.read(int(self.headers['Content-Length'])));calls.append(self.path)
  if self.path.endswith('/embeddings'):
   result={'data':[{'index':i,'embedding':[1.0]+[0.0]*15} for i,_ in enumerate(data['input'])],'usage':{'total_tokens':1}}
  elif self.path.endswith('/rerank'):
   result={'results':[{'index':i,'relevance_score':1/(i+1)} for i in range(min(data['top_n'],len(data['documents'])))]}
  else:
   text=str(data.get('messages',''))
   if '检索查询改写助手' in text:content=json.dumps({'queries':['金融测试资料利率说明']})
   elif '核验证据和结论' in text:content=json.dumps({'passed':True,'score':1,'issues':[]})
   elif 'untrusted_source_text' in text:content='金融测试资料利率说明用于连接测试，不是投资建议。[来源1]'
   else:content='{}'
   result={'model':'ci-controlled-protocol','choices':[{'message':{'content':content}}],'usage':{'prompt_tokens':1,'completion_tokens':1,'total_tokens':2}}
  raw=json.dumps(result).encode();self.send_response(200);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
async def main():
 # Generate and load ephemeral CI credentials locally; don't print their values.
 env={}
 for line in Path('deploy/compose/.env').read_text().splitlines():
  if line and not line.startswith('#') and '=' in line:
   k,v=line.split('=',1);env[k]=v
 os.environ.update(AUTH_SECRET=env['AUTH_SECRET'],MONGODB_URI=f"mongodb://jinshu:{env['MONGO_PASSWORD']}@127.0.0.1:27017/?authSource=admin",MONGODB_DB='jinshu_v8_'+uuid.uuid4().hex[:10],REDIS_ADDR='redis://:'+env['REDIS_PASSWORD']+'@127.0.0.1:6379',MILVUS_URI='http://127.0.0.1:19530',MILVUS_COLLECTION='ci_v8_'+uuid.uuid4().hex[:10],JINSHU_MODEL_SCOPE='local',PI_AGENT_ENABLED='false')
 provider=ThreadingHTTPServer(('127.0.0.1',0),Provider);threading.Thread(target=provider.serve_forever,daemon=True).start();url=f'http://127.0.0.1:{provider.server_port}/v1'
 for prefix in ['CHAT','EMBEDDING','RERANKER']:os.environ.update({prefix+'_BASE_URL':url,prefix+'_API_KEY':'ci-only',prefix+'_MODEL':'ci-controlled-protocol'})
 os.environ['EMBEDDING_DIM']='16'
 from unified.app import create_app
 from unified.tasks import TaskService,MongoTasks,Conflict
 from unified.runtime import RuntimeManager
 from jinshu.live import ping_runtime
 managers=[]
 try:
  app=create_app();manager=app.state.manager;managers.append(manager);r=await manager.get()
  ping=await ping_runtime(r);assert all(v=='ok' for v in ping['services'].values()),ping;checks.append('real_mongo_redis_milvus_connections')
  assert r.profile=='services' and not await r.c.store.count('documents') and not await r.c.store.count('users');checks.append('no_seeded_demo_accounts_or_documents')
  for name in ['editor','reviewer']:
   await r.c.store.upsert_user(r.c.auth._to_user({'username':name,'password':'ci-only-password-1234','name':name,'role':'admin','dept_id':''}))
  async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',timeout=120) as c:
   async def h(name):
    res=await c.post('/api/login',json={'username':name,'password':'ci-only-password-1234'});assert res.status_code==200,res.text
    return {'Authorization':'Bearer '+res.json()['token']}
   editor=await h('editor');reviewer=await h('reviewer');checks.append('redis_rate_limited_login')
   raw=json.dumps({'pages':[{'page':12,'text':'金融测试资料利率说明用于连接测试，不是投资建议。仅检验服务连接与证据来源。'*8}]},ensure_ascii=False).encode()
   res=await c.post('/api/documents/upload',headers=editor,data={'dept_id':'dept_wealth','topic':'ci-runtime-v8','source_kind':'learning_reference'},files={'file':('public-test.json',raw,'application/json')});assert res.status_code==200,res.text;did=res.json()['_id']
   rev={'final_sensitivity':'public','allowed_depts':['dept_wealth'],'external_allowed':False,'reason':'公开合成连接检查'}
   assert (await c.post(f'/api/documents/{did}/review',headers=editor,json=rev)).status_code==403
   res=await c.post(f'/api/documents/{did}/review',headers=reviewer,json=rev);assert res.status_code==200,res.text;assert res.json()['vector_status']=='ready',res.text;checks.append('independent_publication_and_actual_milvus_write')
   res=await c.post('/api/ask',headers=editor,json={'query':'金融测试资料利率说明','workflow':'finance_learning'});assert res.status_code==200,res.text;answer=res.json()
   assert answer['verification']['passed'] and answer['execution']['profile']=='services',answer
   assert answer['execution']['answer_mode']=='llm' and answer['citations'],answer
   assert any('/embeddings' in x for x in calls) and any('/rerank' in x for x in calls) and any('/chat/completions' in x for x in calls),calls
   checks.append('complete_harness_retrieval_chat_verifier_over_controlled_http')
   task=(await c.post('/api/tasks',headers=editor,json={'tool':'issuance','values':{},'use_examples':True})).json();tid=task['_id']
   res=await c.post(f'/api/tasks/{tid}/execute',headers=editor,json={'revision':1});assert res.status_code==200,res.text;assert res.json()['status']=='needs_review'
   res=await c.post(f'/api/tasks/{tid}/approve',headers=editor,json={'revision':3});assert res.status_code==200,res.text
   svc=TaskService(MongoTasks(r.c.mongo.db));results=await asyncio.gather(svc.edit(tid,'editor',4,{'count':1},None,True),svc.edit(tid,'editor',4,{'count':2},None,True),return_exceptions=True)
   assert sum(isinstance(x,Conflict) for x in results)==1;checks.append('real_mongo_compare_and_swap_rejects_concurrent_edit')
   job=await r.c.job_queue.enqueue('loop',{});out=await c.post('/api/jobs/process',headers=editor,json={});assert out.status_code==200,out.text
   state=await r.c.store.get('async_jobs',job['_id']);assert state['status']=='completed',state;checks.append('real_redis_stream_mongo_job_processing')
   # A separate Runtime instance reads the same server-held task, session and corpus.
   other=RuntimeManager();managers.append(other);r2=await other.get();assert (await r2.c.store.get('traces',answer['trace_id']))['user_id']=='editor'
   assert (await TaskService(MongoTasks(r2.c.mongo.db)).read(tid,'editor'))['revision']==5
   context=await r2.c.working_memory.get_context(answer['session_id']);assert context['messages'];checks.append('new_runtime_recovers_trace_task_and_working_memory')
   await r2.c.bm25.search('金融测试资料',dept_id='dept_wealth')
   before=(await r.c.store.get('corpus_revisions','dept_wealth'))['value']
   res=await c.post(f'/api/documents/{did}/archive',headers=reviewer,json={'reason':'连接检查完成'});assert res.status_code==200,res.text
   assert (await r.c.store.get('corpus_revisions','dept_wealth'))['value']==before+1
   assert not await r2.c.bm25.search('金融测试资料',dept_id='dept_wealth');checks.append('deactivation_refreshes_other_instance_department_index')
   res=await c.post('/api/ask',headers=editor,json={'query':'金融测试资料利率说明','workflow':'finance_learning'});assert res.status_code==200 and not res.json()['citations'];checks.append('archived_source_cannot_answer')
 finally:
  for m in managers:
   if m.runtime:
    try:await m.runtime.close()
    except Exception:pass
  provider.shutdown()
 result={'passed':len(checks),'checks':checks,'provider':'controlled_HTTP_protocol_fixture_not_a_real_model','services':'isolated_real_MongoDB_Redis_Milvus','cloud_credentials_used':False}
 out=Path('evidence/unified-v8');out.mkdir(parents=True,exist_ok=True);(out/'services.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':asyncio.run(main())
