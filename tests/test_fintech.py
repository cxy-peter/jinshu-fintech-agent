import asyncio,copy,json,hashlib
from decimal import Decimal
from pathlib import Path
import pytest
import jinshu
from jinshu.runtime import Runtime,StrictEmbeddings
from jinshu.fixtures import WORKFLOWS,DATA,DEPARTMENTS
from jinshu import tools
from jinshu.skills import bucket,validate_skill
from jinshu.retrieval import valid_chunk,MilvusVectorStore
from jinshu.memory import ExpiringSessionStore
from jinshu.ingestion import TableAwareChunker
from jinshu.budgets import BoundedNode
from jinshu.context import scope,run_state
from app.harness.base import Answer,VerificationResult
from app.pipeline.parser import ParsedDocument,Block
from app.config import Settings
from fastapi.testclient import TestClient

@pytest.fixture
async def runtime():
 r=await Runtime().initialize();yield r;await r.close()

@pytest.mark.parametrize('value,percentage,expected',[('1,234.50',False,'1234.50'),('(12.3)',False,'-12.3'),('--',False,None),('0',False,'0'),('2.5%',True,'0.025')])
def test_numbers(value,percentage,expected):assert tools.number(value,percentage)==(None if expected is None else Decimal(expected))
@pytest.mark.parametrize('value',['NaN','Infinity','not a number'])
def test_bad_numbers(value):
 with pytest.raises(ValueError):tools.number(value)
def test_products_peer_scope():
 r=tools.wealth_benchmark({});assert len(r['rows'])>=2 and '模拟' in r['rows'][0]['产品全称'];assert len({(x['起始日'],x['截止日']) for x in r['rows']})==1
def test_issuance_calendar():
 r=tools.issuance({'start':'2026-09-25'});assert r['rows'][0]['成立日']=='2026-09-28';assert r['rows'][0]['日历版本']=='SIM-CALENDAR-v1'
@pytest.mark.parametrize('p',[{'term_days':0},{'frequency_days':1},{'count':500}])
def test_issuance_constraints(p):
 with pytest.raises(ValueError):tools.issuance(p)
def test_weekly_no_missing_zero_or_id_conversion():
 r=tools.weekly_report({});assert r['rows'][0]['登记编码'].startswith('00');assert any(x['区间收益率'] is None for x in r['rows']);assert r['issues']
def test_onboarding_time():assert next(x for x in tools.onboarding({'decision_stage':1})['rows'] if x['field']=='bank_link')['available_now'] is False
def test_kep_not_found_not_missed():
 r=tools.kep({});assert any(x['status']=='ambiguous' for x in r['rows']);assert any(x['status']=='not_found_needs_review' for x in r['rows'])
def test_disabled_candidate():assert tools.strategy({})['candidate']['status']=='disabled'
def test_strategy_invalid():
 with pytest.raises(ValueError):tools.strategy({'feature':'execute_money_transfer'})
 with pytest.raises(ValueError):tools.strategy({'threshold':-1})
@pytest.mark.parametrize('year',[2024,2025])
def test_statement_balance(year):assert tools.statements({'year':year})['passed']
def test_unknown_year():
 with pytest.raises(ValueError):tools.statements({'year':2040})
def test_file_hash_sources():assert len(tools.run('wealth_benchmark')['source_files'][0]['sha256'])==64

@pytest.mark.parametrize('workflow',[w for w in WORKFLOWS if w not in {'fund_research','finance_learning'}])
async def test_all_workflows(runtime,workflow):
 r=await runtime.ask(WORKFLOWS[workflow]['name'],user_id='test',workflow=workflow)
 assert r['verification']['passed'];assert r['execution']['skill_plan']['skills']==['base_'+workflow]
 assert r['tool_results'] or workflow=='service';assert {s['node'] for s in r['execution']['stages']}=={'Intent','Rewrite','Retrieval','Answer','Verify'}
async def test_session_isolation(runtime):
 r=await runtime.ask('发行排期',user_id='alice',workflow='issuance')
 with pytest.raises(PermissionError):await runtime.ask('发行排期',user_id='bob',workflow='issuance',session_id=r['session_id'])
async def test_dept_isolation(runtime):
 with pytest.raises(PermissionError):await runtime.ask('开户',user_id='wealth',workflow='onboarding',allowed=['dept_wealth'])
async def test_feedback_owner(runtime):
 r=await runtime.ask('开户',user_id='alice',workflow='onboarding')
 with pytest.raises(PermissionError):await runtime.feedback(r['trace_id'],'bob')
async def test_pronoun_memory(runtime):
 r=await runtime.ask('发行排期怎么做',user_id='a',workflow='issuance');s=await runtime.ask('那怎么办',user_id='a',session_id=r['session_id'])
 assert s['workflow']=='issuance' and '发行排期怎么做' in s['execution']['rewritten_query']
async def test_neutral_followup_not_negative(runtime):
 r=await runtime.ask('发行排期怎么做',user_id='a',workflow='issuance');await runtime.ask('那怎么办',user_id='a',session_id=r['session_id'])
 assert not any(f['signal']=='follow_up' for f in await runtime.c.store.find('feedback'))
async def test_hooks_applied(runtime):
 r=await runtime.ask('开户IBAN时点',user_id='a',workflow='onboarding');assert 'hook_kyc_time' in r['execution']['hooks_applied']
 assert any('字段采集节点' in q for q in r['execution']['skill_plan']['queries'])
async def test_source_mutation_rejected(runtime):
 ch=(await runtime.c.store.list_active_chunks())[0];ch['content']='tampered';await runtime.c.store.upsert('chunks',ch)
 assert await valid_chunk(runtime.c.store,ch['_id'],[ch['dept_id']]) is None
async def test_archive_filtered(runtime):
 archived=next(d for d in await runtime.c.store.list_documents() if d['status']=='archived')
 ch=(await runtime.c.store.list_chunks_by_doc(archived['_id']))[0]
 assert await valid_chunk(runtime.c.store,ch['_id'],[ch['dept_id']]) is None
async def test_no_evidence_fails_closed(runtime):assert not (await runtime.c.orchestrator.verifier_agent.verify('unknown',Answer(),[])).passed

def test_tables_preserve_headers():
 table='|产品编码|金额|\n|---|---|\n'+'\n'.join(f'|SIM{i:03d}|{i}.00|' for i in range(20))
 d=ParsedDocument('模拟表',[Block('table',0,table)])
 cs=TableAwareChunker().chunk(d);assert len(cs)==3 and all('产品编码' in c['content'] for c in cs)
 assert all(c['metadata']['source_row_start'] for c in cs)
async def test_tables_actually_ingested(runtime):assert any(c['metadata'].get('has_table') for c in await runtime.c.store.list_all_chunks())
async def test_second_review_and_version(runtime,tmp_path):
 p=tmp_path/'v3.md';p.write_text('# 模拟新版\n\n新版本仅为测试。',encoding='utf8')
 d=await runtime.c.indexer.ingest(p,'dept_release','author',topic='calendar',version=3)
 with pytest.raises(PermissionError):await runtime.c.indexer.publish(d['_id'],'author',['dept_release'])
 await runtime.c.indexer.publish(d['_id'],'reviewer',['dept_release'])
 assert (await runtime.c.store.get('document_heads','dept_release:calendar'))['doc_id']==d['_id']
async def test_duplicate_no_overwrite(runtime):
 with pytest.raises(ValueError):await runtime.c.indexer.ingest(DATA/'calendar_v2.md','dept_release','test',topic='calendar',version=2)
async def test_future_not_publish(runtime,tmp_path):
 p=tmp_path/'x.md';p.write_text('# future\n\n未来政策',encoding='utf8');d=await runtime.c.indexer.ingest(p,'dept_release','a',topic='future',version=1,effective_date='2099-01-01')
 with pytest.raises(ValueError):await runtime.c.indexer.publish(d['_id'],'b',['dept_release'])
async def test_preference_consent(runtime):
 with pytest.raises(ValueError):await runtime.c.user_semantic_memory.remember('a','answer_style','brief',consent=False)
 with pytest.raises(ValueError):await runtime.c.user_semantic_memory.remember('a','bank_account','123',consent=True)
 m=await runtime.c.user_semantic_memory.remember('a','answer_style','brief',consent=True)
 assert (await runtime.c.user_semantic_memory.recall('a'))[0]['_id']==m['_id']
 assert await runtime.c.user_semantic_memory.forget('a',m['_id'],'a')
async def test_org_mismatched_ref(runtime):
 docs=await runtime.c.store.list_documents(status='active');a,b=docs[:2];ch=(await runtime.c.store.list_chunks_by_doc(b['_id']))[0]
 with pytest.raises(ValueError):await runtime.c.organization_memory.publish('department','faq','x','x',[{'doc_id':a['_id'],'chunk_id':ch['_id']}],dept_id=a['dept_id'])
async def test_budget(runtime):
 await runtime.c.working_memory.set_summary('s','x'*10000);runtime.c.memory_context_builder.max_chars=500
 c=await runtime.c.memory_context_builder.build('s','a','x',['dept_release']);assert len(c.prompt_text())<=500
async def test_memory_ttl():
 s=ExpiringSessionStore();await s.set_session('s',{'a':1},ttl=-1);assert await s.get_session('s') is None
async def test_bounded_node():
 class Slow:
  async def get(self):await asyncio.sleep(.05)
 n=BoundedNode(Slow(),'get','test',.001,lambda:'fallback');assert await n.get()=='fallback'
async def test_final_answer_verified(runtime):
 class Bad:
  def __init__(self):self.calls=0
  async def verify(self,*a,**k):self.calls+=1;return VerificationResult(False,0,['test'])
 bad=Bad();runtime.c.orchestrator.verifier_agent=bad
 out=await runtime.ask('发行排期',workflow='issuance')
 assert bad.calls==3 and not out['verification']['passed'] and '未通过校验' in out['answer']
def test_skill_whitelist():
 base={'dept_id':'dept_release','trigger':{'intent_patterns':['x']},'action':{'steps':[{'action':'shell','params':{'cmd':'rm'}}]}}
 with pytest.raises(ValueError):validate_skill(base)
 base['action']['steps']=[{'action':'retrieve','params':{'top_k':50}}]
 with pytest.raises(ValueError):validate_skill(base)
def test_bucket_stable():assert bucket('alice','exp1')==bucket('alice','exp1') and 0<=bucket('alice','exp1')<1
async def test_one_replay_cannot_deploy(runtime):
 r=await runtime.ask('发行排期',user_id='a',workflow='issuance');await runtime.feedback(r['trace_id'],'a',expected_terms=['顺延']);await runtime.cycle();s=(await runtime.c.store.list_skills(status='pending'))[0]
 with pytest.raises(ValueError):await runtime.c.loop_engine.approve(s['_id'],'b')
async def test_knowledge_gap_is_not_skill(runtime):
 r=await runtime.ask('客服没有对应政策',user_id='a',workflow='service');await runtime.feedback(r['trace_id'],'a',category='knowledge_gap');job=await runtime.cycle()
 assert job['status']=='completed';assert await runtime.c.store.count('knowledge_tickets')==1;assert not await runtime.c.store.list_skills(status='pending')
async def test_metrics_unique_users(runtime):
 for i in range(10):await runtime.c.store.upsert('strategy_executions',{'_id':str(i),'artifact_id':'test','group':'treatment','user_id':'same','quality_success':True,'reviewed_at':str(i)})
 assert (await runtime.c.loop_engine.metrics('test'))['treatment']['n']==1
async def test_whole_loop():
 from jinshu.demo import run_loop_lab
 x=await run_loop_lab()
 assert x['candidate']['replay']['sample_count']==20
 assert x['final_experiment']['status']=='rolled_back' and x['after_rollback']['plan']['top_k']==2
 assert x['unchanged_financial_results'] and x['mining_runs']

class MockMilvus:
 def has_collection(self,**k):return True
 def upsert(self,**k):self.payload=k
 def search(self,**k):return [[{'id':'c','distance':.9,'entity':{'dept_id':'dept_release'}}]]
def test_milvus_dimensions():
 m=MilvusVectorStore('mock','test',3,client=MockMilvus())
 with pytest.raises(ValueError):m.check([1,2])
async def test_milvus_scope():
 m=MilvusVectorStore('mock','test',3,client=MockMilvus())
 with pytest.raises(PermissionError):await m.search([1,0,0])
 assert (await m.search([1,0,0],dept_id='dept_release'))[0]['id']=='c'
async def test_no_silent_embedding_fallback():
 e=StrictEmbeddings(Settings(_env_file=None,embedding_provider='relay',relay_api_key=''),None)
 with pytest.raises(RuntimeError):await e.embed(['hello'])

def test_api_auth_controls():
 from jinshu.api import create_app
 with TestClient(create_app()) as c:
  assert c.get('/api/catalog').status_code==401
  j=c.post('/api/login',json={'username':'analyst','password':'demo-analyst'}).json();h={'Authorization':'Bearer '+j['token']}
  assert 'wealth_benchmark' in c.get('/api/catalog',headers=h).json()['workflows']
  assert c.post('/api/ask',headers=h,json={'query':'开户','workflow':'onboarding'}).status_code==403
  assert c.post('/api/loop/run',headers=h).status_code==403
  r=c.post('/api/ask',headers=h,json={'query':'理财对标','workflow':'wealth_benchmark'})
  assert r.status_code==200 and r.json()['tool_results']

def test_api_import_review():
 from jinshu.api import create_app
 with TestClient(create_app()) as c:
  def login(n):return {'Authorization':'Bearer '+c.post('/api/login',json={'username':n,'password':'demo-'+n}).json()['token']}
  a,b=login('editor'),login('reviewer')
  r=c.post('/api/documents',headers=a,json={'title':'模拟规范','topic':'test-123','version':1,'dept_id':'dept_release','body':'## 规则\n\n需要复核。'})
  assert r.status_code==200;did=r.json()['_id']
  review={'final_sensitivity':'internal','reason':'审核模拟内容和部门范围'}
  assert c.post(f'/api/documents/{did}/review',headers=a,json=review).status_code==403
  assert c.post(f'/api/documents/{did}/review',headers=b,json=review).status_code==200

async def test_live_verifier_does_not_approve_heuristic(runtime):
 from app.harness.base import Citation
 from jinshu.agents import StrictVerifier,DisabledLLM
 ch=(await runtime.c.store.list_active_chunks())[0]
 tok=scope.set([ch['dept_id']]);tk=run_state.set({'answer_mode':'llm'})
 try:
  from jinshu.agents import FintechAnswer
  a=await FintechAnswer(DisabledLLM(),runtime.c.store).generate('test',[ch])
  run_state.get()['answer_mode']='llm'
  out=await StrictVerifier(runtime.c.store,DisabledLLM()).verify('test',a,[ch])
  assert not out.passed and 'semantic_review_unavailable' in out.issues
 finally:scope.reset(tok);run_state.reset(tk)

@pytest.mark.parametrize('completed',[True,False])
async def test_redis_pending_recovery_contract(runtime,completed):
 from types import SimpleNamespace
 from jinshu.queue import RecoverableJobQueue
 class RedisFake:
  def __init__(self):self.acked=[];self.reads=0
  async def xgroup_create(self,*a,**k):pass
  async def xautoclaim(self,*a,**k):return ['1-0',[('42-0',{'job_id':'rj'})],[]]
  async def xack(self,*args):self.acked.append(args)
  async def xreadgroup(self,*a,**k):self.reads+=1;return []
 fake=RedisFake();queue=RecoverableJobQueue(runtime.c.store,SimpleNamespace(_redis=fake),'test-jobs')
 await runtime.c.store.upsert('async_jobs',{'_id':'rj','type':'loop','status':'completed' if completed else 'running','attempts':1})
 jobs=await queue.next_jobs(1,10)
 assert queue.reclaim_cursor=='1-0'
 if completed:assert not jobs and len(fake.acked)==1
 else:
  assert len(jobs)==1 and jobs[0]['attempts']==2
  await queue.finish(jobs[0],'completed',{'ok':True});assert len(fake.acked)==1

async def test_model_policy_delta_is_used_and_bounded():
 from jinshu.policy import PolicyProposer
 class Model:
  async def complete_json(self,*a,**k):return {'query_terms':['复核'],'top_k':7,'template':'default'}
 out=await PolicyProposer(Model()).propose('q',{},'需要复核',['来源'])
 assert out['top_k']==7 and out['mode']=='python_llm'
 class BadModel:
  async def complete_json(self,*a,**k):return {'query_terms':['秘密'],'top_k':10000,'template':'shell','permissions':'admin'}
 out=await PolicyProposer(BadModel()).propose('q',{},'复核',['来源'])
 assert out['mode'].endswith('fallback') and out['top_k']==8
