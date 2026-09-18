"""Compose the original Wenshu components with additive fintech adapters."""
from __future__ import annotations
import asyncio,copy,json,os,secrets,uuid
from pathlib import Path
from app.config import Settings
from app.deps import build_container
from app.harness.orchestrator import Orchestrator
from app.harness.agents.retrieval_agent import RetrievalAgent
from app.loop.skill_miner import SkillMiner
from app.memory.working import WorkingMemory
from app.llm.embeddings import EmbeddingClient
from app.retrieval.reranker import HeuristicReranker,RelayReranker
from .agents import DisabledLLM,FintechIntent,FintechRewrite,FintechAnswer,StrictVerifier
from .context import scope,run_state,access
from .fixtures import DATA,DEPARTMENTS,WORKFLOWS,generate
from .ingestion import DraftIndexer
from .retrieval import TrustedRetrieval,MilvusVectorStore
from .memory import ExpiringSessionStore,BudgetedContextBuilder,ConsentMemory,TrustedOrganizationMemory
from .skills import ExecutableSkillExecutor,seed_skills
from .loop import FeedbackLoop,SourceReplay
from .queue import RecoverableJobQueue

class StrictEmbeddings(EmbeddingClient):
 async def embed(self,texts):
  if self.provider=='hash':return await super().embed(texts)
  if self.provider=='relay':
   if not self.settings.relay_api_key:raise RuntimeError('Live embeddings need authorized credentials; no silent hash fallback')
   result=await self.relay.embed(texts,model=self.model)
   if len(result)!=len(texts) or any(len(v)!=self.dim for v in result):raise ValueError('embedding model/dimension mismatch')
   return result
  raise ValueError('Use explicitly configured relay or offline hash mode')

class FinancialOrchestrator(Orchestrator):
 async def _finalize(self,*a,**k):
  tid=await super()._finalize(*a,**k);state=run_state.get()
  if state is not None:
   trace=await self.store.get('traces',tid)
   trace.update({key:copy.deepcopy(value) for key,value in state.items() if key not in {'trace_id'}})
   trace['metric_scope']='source integrity and task execution; not semantic/user accuracy'
   await self.store.upsert('traces',trace);state['trace_id']=tid
  return tid

class Runtime:
 def __init__(self,profile='offline',settings=None,instance_id=None):
  if settings is None:
   if profile=='offline':
    settings=Settings(_env_file=None,storage_mode='memory',vector_backend='memory',embedding_provider='hash',embedding_dim=256,reranker_enabled=False,pi_agent_enabled=False,dept_agents_enabled=False,
     seed_demo_users=False,app_name='金枢｜金融产品中后台自进化 Agent',auth_secret=secrets.token_hex(32),hybrid_topk=2,loop_rollback_min_samples=3,
     loop_rollback_margin=.1,deepseek_api_key='',relay_api_key='')
   elif profile=='services':
    settings=Settings(app_name='金枢｜金融产品中后台自进化 Agent',storage_mode='mongo',seed_demo_users=False)
    if os.getenv('JINSHU_MODEL_SCOPE','external')!='local' and not os.getenv('JINSHU_ALLOW_EXTERNAL')=='1':raise RuntimeError('Services profile requires explicit JINSHU_ALLOW_EXTERNAL=1')
    if not settings.auth_secret or settings.auth_secret=='wenshu-dev-secret-change-me':raise RuntimeError('Configure AUTH_SECRET')
    if settings.embedding_provider=='hash':raise RuntimeError('Services must use semantic embeddings, not hash')
   else:raise ValueError('Unknown runtime profile')
  from .operations import RecoveryController,TicketOutbox
  from . import ROOT
  directory=ROOT/'workspace'/(instance_id or os.getenv('JINSHU_INSTANCE_ID','local'))
  self.recovery=RecoveryController(directory);self.outbox=TicketOutbox(directory)
  self.profile=profile;self.c=c=build_container(settings);self.sessions={};self.worker_task=None;self.stop=asyncio.Event()
  if profile=='services':
   from .live import configure_clients
   configure_clients(c,settings)
  if profile=='offline':
   c.llm=DisabledLLM();c.session_store=ExpiringSessionStore()
  c.embeddings=c.live_embeddings if profile=='services' else StrictEmbeddings(settings,c.relay)
  if settings.vector_backend=='milvus':
   c.vector_store=MilvusVectorStore(os.getenv('MILVUS_URI','http://localhost:19530'),os.getenv('MILVUS_COLLECTION','jinshu_chunks')+('_'+c.embeddings.fingerprint if profile=='services' else ''),settings.embedding_dim,os.getenv('MILVUS_TOKEN',''))
  elif settings.vector_backend not in {'memory','mongo','chroma'}:raise ValueError('Unrecognized vector backend')
  original_hybrid=c.retrieval_agent.hybrid;original_hybrid.vector_store=c.vector_store
  c.retrieval_agent=TrustedRetrieval(original_hybrid,c.embeddings,c.store)
  c.user_semantic_memory=ConsentMemory(c.store,settings.memory_user_retention_days)
  c.organization_memory=TrustedOrganizationMemory(c.store)
  c.indexer=DraftIndexer(c.store,c.vector_store,c.embeddings,c.bm25,c.llm);c.indexer.organization_memory=c.organization_memory
  from .document_service import ReviewedDocumentService
  c.documents=ReviewedDocumentService(c.indexer)
  if profile=='services':
   from .live_chunker import LiveChunker
   c.indexer.chunker=LiveChunker()
  if profile=='services':
   from .service_ops import SharedPublisher,SharedRecovery
   c.documents.indexer=c.indexer=SharedPublisher.from_indexer(c.indexer,c.mongo)
   self.recovery=SharedRecovery(directory,c.store);c.documents.indexer.organization_memory=c.organization_memory
  c.working_memory=WorkingMemory(c.session_store,ttl=settings.memory_session_ttl_seconds,max_history=settings.memory_max_recent_messages)
  c.memory_context_builder=BudgetedContextBuilder(c.store,c.working_memory,c.episodic_memory,c.user_semantic_memory,c.organization_memory,c.learning_memory,max_chars=settings.memory_context_max_chars,user_limit=settings.memory_user_limit,org_limit=settings.memory_org_limit,recent_limit=settings.memory_max_recent_messages)
  from .hooks import FintechHooks
  c.hook_engine=FintechHooks(c.store)
  c.skill_executor=ExecutableSkillExecutor(c.store,default_top_k=settings.hybrid_topk)
  c.skill_executor.recovery=self.recovery
  c.skill_miner=SkillMiner(c.store,c.llm,min_cluster=settings.skill_min_cluster)
  c.loop_engine=FeedbackLoop(settings,c.store,c.llm,c.embeddings,c.skill_miner,c.hook_engine,c.rule_engine,c.feedback_collector,None,c.pi_runtime)
  c.loop_engine.recovery=self.recovery
  c.orchestrator=FinancialOrchestrator(settings=settings,store=c.store,working_memory=c.working_memory,user_memory=c.user_memory,dept_memory=c.dept_memory,episodic_memory=c.episodic_memory,memory_context_builder=c.memory_context_builder,organization_memory=c.organization_memory,
   intent_agent=FintechIntent(c.llm,c.store,c.pi_runtime,settings.pi_runtime_timeout_intent),dept_router=c.dept_router,
   query_rewriter=FintechRewrite(c.llm,c.store,c.pi_runtime,settings.pi_runtime_timeout_rewrite),retrieval_agent=c.retrieval_agent,
   answer_agent=FintechAnswer(c.llm,c.store,c.pi_runtime,settings.pi_runtime_timeout_answer),verifier_agent=StrictVerifier(c.store,c.llm,c.pi_runtime,settings.pi_runtime_timeout_verify),
   feedback_agent=c.feedback_agent,loop_engine=c.loop_engine,hook_engine=c.hook_engine,rule_engine=c.rule_engine,skill_executor=c.skill_executor,
   dept_agent_client=None,pi_client=c.pi_client)
  from .budgets import BoundedNode
  from app.harness.base import Intent,VerificationResult
  o=c.orchestrator
  o.intent_agent=BoundedNode(o.intent_agent,'infer','Intent',settings.timeout_intent,lambda *a,**k:Intent(depts=list(scope.get() or []),raw={'type':'other','depts':list(scope.get() or [])}))
  o.query_rewriter=BoundedNode(o.query_rewriter,'rewrite','Rewrite',settings.pi_runtime_timeout_rewrite,lambda query,*a,**k:[query])
  o.retrieval_agent=BoundedNode(o.retrieval_agent,'retrieve','Retrieval',settings.timeout_retrieval,lambda *a,**k:[])
  backup=FintechAnswer(DisabledLLM(),c.store)
  o.answer_agent=BoundedNode(o.answer_agent,'generate','Answer',settings.timeout_answer,backup.generate)
  o.verifier_agent=BoundedNode(o.verifier_agent,'verify','Verify',settings.timeout_verify,lambda *a,**k:VerificationResult(False,0,['verify_timeout_no_approval']))
  c.retrieval_agent=o.retrieval_agent
  c.strategy_evaluator=SourceReplay(c);c.loop_engine.strategy_evaluator=c.strategy_evaluator
  c.job_queue=RecoverableJobQueue(c.store,c.session_store,settings.async_stream_name)
  c.review_engine.llm=c.llm;c.review_engine.retrieval_agent=c.retrieval_agent;c.review_engine.answer_agent=c.orchestrator.answer_agent

 async def initialize(self):
  if self.profile=='services':
   await self.c.mongo.connect();await self.c.session_store.connect()
  if not (DATA/'documents.json').exists():generate()
  for did,name in DEPARTMENTS.items():await self.c.store.upsert_department({'_id':did,'name':name,'description':name,'keywords':[name]})
  should_seed=self.profile=='offline' or os.getenv('JINSHU_BOOTSTRAP')=='1'
  if not await self.c.store.count('documents') and should_seed:
   manifest=json.loads((DATA/'documents.json').read_text())
   for d in manifest:
    doc=await self.c.indexer.ingest(DATA/d['file'],d['dept_id'],uploaded_by='seed_author',topic=d['topic'],version=d['version'])
    if d['status']=='active':await self.c.indexer.publish(doc['_id'],'seed_reviewer',list(DEPARTMENTS))
    elif d['status']=='archived':await self.c.store.update_document(doc['_id'],{'status':'archived'})
  else:
   for ch in await self.c.store.list_active_chunks():self.c.bm25.remove(ch['_id']);self.c.bm25.add(ch)
  if should_seed:
   await seed_skills(self.c.store)
   from .hooks import seed_controls
   await seed_controls(self.c.store)
  for name,dept,role in [('analyst','dept_wealth','student'),('risk','dept_risk','student'),('operations','dept_release','student'),('service','dept_service','student'),('editor','','admin'),('reviewer','','admin')]:
   if self.profile=='offline' and not await self.c.store.get('users',name):
    u=self.c.auth._to_user({'username':name,'password':'demo-'+name,'name':{'analyst':'理财分析员','risk':'风控产品人员','operations':'发行报表人员','service':'客服人员','editor':'知识编辑','reviewer':'独立复核员'}[name],'role':role,'dept_id':dept})
    await self.c.store.upsert_user(u)
  return self

 async def ask(self,query,user_id='analyst',workflow=None,session_id='',params=None,allowed=None,clearance='internal',allow_external=False):
  if not query.strip() or len(query)>2000:raise ValueError('请输入1至2000字的问题')
  session_id=session_id or uuid.uuid4().hex
  row=await self.c.store.get('session_owners',session_id)
  if row and row['user_id']!=user_id:raise PermissionError('会话不属于当前用户')
  await self.c.store.upsert('session_owners',{'_id':session_id,'user_id':user_id})
  ctx=await self.c.working_memory.get_context(session_id)
  previous=[m['content'] for m in ctx['messages'] if m['role']=='user']
  if workflow is None:
   workflow=next((k for k,v in WORKFLOWS.items() if any(t.lower() in query.lower() for t in v['triggers'])),None)
   if not workflow and query.strip() in {'那怎么办','那怎么办？','然后呢','怎么处理','再说一下'}:workflow=ctx.get('entities',{}).get('workflow')
  if workflow not in WORKFLOWS:raise ValueError('请明确选择金融产品工作流')
  allowed=allowed if allowed is not None else [WORKFLOWS[workflow]['dept']]
  if self.profile=='services' and os.getenv('DEPT_ID'):
   allowed=[d for d in allowed if d==os.environ['DEPT_ID']]
  if WORKFLOWS[workflow]['dept'] not in allowed:raise PermissionError('当前身份无权执行该部门工作流')
  state={'user_id':user_id,'workflow':workflow,'original_query':query,'params':params or {},'tools':[],'profile':self.profile,'last_user_query':previous[-1] if previous else ''}
  state['allow_external']=bool(allow_external and self.profile=='services')
  from .live import local_models
  state['models_enabled']=self.profile=='services' and (local_models() or allow_external)
  if self.profile=='services':await self.recovery.refresh(workflow)
  tk=scope.set(allowed);sk=run_state.set(state);ak=access.set({'departments':allowed,'clearance':clearance})
  try:
   state['selected_workflow']=workflow
   result=await self.c.orchestrator.answer(query,session_id,user_id,[WORKFLOWS[workflow]['dept']])
   result.update(trace_id=state.get('trace_id'),workflow=workflow,tool_results=state['tools'],execution=state)
   return result
  finally:scope.reset(tk);run_state.reset(sk);access.reset(ak)

 async def feedback(self,tid,user_id,signal='down',category='retrieval',expected_terms=None,note=''):
  t=await self.c.store.get('traces',tid)
  if not t or t['user_id']!=user_id:raise PermissionError('只能反馈自己的任务')
  if category not in {'retrieval','intent','generation','knowledge_gap'}:raise ValueError('无效归因类别')
  if signal not in {'up','down','correction','copy','follow_up'}:raise ValueError('无效反馈信号')
  if signal in {'up','down','correction'}:
   for ex in await self.c.store.find('strategy_executions',{'trace_id':tid}):
    ex.update(quality_success=signal=='up',quality_source='explicit_user_feedback',reviewed_at=__import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat())
    await self.c.store.upsert('strategy_executions',ex)
  await self.c.feedback_collector.collect_explicit(t['session_id'],user_id,t['query'],t['answer'],signal,{'trace_id':tid,'workflow':t['workflow'],'category':category,'expected_terms':expected_terms or [],'note':note[:1000]})

 async def cycle(self):
  job=await self.c.job_queue.enqueue('loop',{})
  await self.process_jobs()
  return await self.c.store.get('async_jobs',job['_id'])
 async def process_jobs(self):
  for j in await self.c.job_queue.next_jobs(count=1,block_ms=20):
   stages=[]
   async def progress(stage,detail):
    stages.append({'stage':stage,'detail':detail})
    await self.c.job_queue.update_progress(j['_id'],{'stage':stage,'history':list(stages)})
   try:
    if j['type']=='loop':r=await self.c.loop_engine.run_cycle(progress)
    elif j['type']=='document_stage':
     r=await self.c.documents.stage_file(**j['payload'])
    else:raise ValueError('未知作业类型')
    await self.c.job_queue.finish(j,'completed',r)
   except Exception as e:await self.c.job_queue.finish(j,'failed',{'error':type(e).__name__,'message':str(e)})
 async def worker(self):
  while not self.stop.is_set():
   try:await self.process_jobs()
   except Exception:
    await asyncio.sleep(2)
   try:await asyncio.wait_for(self.stop.wait(),timeout=.5)
   except asyncio.TimeoutError:pass
 async def close(self):
  self.stop.set()
  if self.worker_task:await self.worker_task
  await self.c.pi_runtime.close()
  if hasattr(self.c.llm,'close'):await self.c.llm.close()
  if hasattr(self.c.relay,'close'):await self.c.relay.close()
  if self.profile=='services':
   await self.c.embeddings.close();await self.c.live_reranker.close()
   await self.c.session_store.close();await self.c.mongo.close()
