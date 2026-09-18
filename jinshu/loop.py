"""Retains original LoopEngine.run_cycle; closes candidate -> replay -> canary -> rollback.
Self-evolution changes execution policy, NOT model weights or authoritative financial facts.
"""
from __future__ import annotations
import asyncio,copy,hashlib,json,uuid
from datetime import datetime,timezone
from app.loop.loop_engine import LoopEngine
from app.loop.skill_executor import SkillPlan
from app.harness.base import Intent
from .skills import validate_skill
from .fixtures import WORKFLOWS
from .context import scope,run_state,access
from .live import local_models
import os

def now():return datetime.now(timezone.utc).isoformat()

class FeedbackLoop(LoopEngine):
 async def _reflect(self,bad_cases):
  if self.embeddings.provider!='hash' and not local_models():
   raise PermissionError('后台Loop默认只使用私有模型；外部模型模式不自动发送反馈及跨文档正文')
  result=await super()._reflect(bad_cases)
  cats={}
  for c in bad_cases:
   category=c.get('detail',{}).get('category')
   if category in {'retrieval','intent','generation','knowledge_gap'}:cats[category]=cats.get(category,0)+1
  if cats:result['explicit_feedback_categories']=cats
  result['engine']='live runtime with recorded fallback' if self.embeddings.provider!='hash' else 'offline deterministic fallback (no model inference)'
  return result
 async def _adapt(self,reflect,bad_cases):
  proposals=[]
  for feedback in bad_cases:
   detail=feedback.get('detail') or {};trace_id=detail.get('trace_id');trace=await self.store.get('traces',trace_id or '')
   if not trace:continue
   family=detail.get('workflow') or trace.get('workflow');w=WORKFLOWS.get(family)
   if not w:continue
   category=detail.get('category','retrieval')
   if category=='knowledge_gap':
    pid='gap_'+hashlib.sha256((trace['query']+w['dept']).encode()).hexdigest()[:16]
    await self.store.upsert('knowledge_tickets',{'_id':pid,'dept_id':w['dept'],'query':trace['query'],'source_feedback':feedback['_id'],'status':'needs_document','created_at':now()})
    proposals.append({'type':'knowledge_gap','id':pid});continue
   from .retrieval import valid_chunk
   docs=[c for d in await self.store.list_active_chunks(w['dept']) if (c:=await valid_chunk(self.store,d['_id'],[w['dept']]))]
   text='\n'.join(d['content'] for d in docs)
   desired=detail.get('expected_terms') or []
   expansions=[str(t) for t in desired if 1<len(str(t))<=40 and str(t) in text]
   if not expansions:expansions=[w['query'],'来源','复核']
   from .policy import PolicyProposer
   proposal=await PolicyProposer(self.llm,self.pi_runtime,self.settings.pi_runtime_timeout_reflect).propose(trace['query'],detail,text,expansions)
   expansions=proposal['query_terms']
   key=hashlib.sha256((family+'|'+json.dumps(proposal|{'mode':''},ensure_ascii=False,sort_keys=True)).encode()).hexdigest()[:16];sid='learned_'+key
   version=2
   while existing:=await self.store.get_skill(sid):
    if existing.get('status') in {'pending','active'}:break
    version+=1;sid='learned_'+key+'_v'+str(version)
   if existing and existing.get('status') in {'pending','active'}:continue
   base=await self.store.get_skill('base_'+family)
   s={'_id':sid,'family':family,'name':w['name']+'·反馈增强','dept_id':w['dept'],'scope':'department','status':'pending','version':version,'gray_percent':0,'trigger':base['trigger'],
    'action':{'type':'workflow','steps':[{'action':'retrieve','params':{'query':'{matter} '+' '.join(expansions),'top_k':proposal['top_k']}},{'action':'generate','params':{'template':proposal['template']}}]},
    'source_feedback':[feedback['_id']],'source_trace':trace_id,'expected_terms':expansions,'created_by':'loop_engine','created_at':now(),'confidence':.7,'replaces':None,'target':'execution_policy_only','root_cause':category}
   s['proposal_mode']=proposal['mode'];s['bounded_proposal']=proposal
   validate_skill(s)
   traces=await self.store.list_recent_traces(limit=100)
   family_traces=[t for t in traces if t.get('workflow')==family]
   if len(family_traces)>=self.settings.skill_min_cluster:
    vecs=await self.embeddings.embed([t['query'] for t in family_traces])
    drafts=await self.skill_miner.mine(family_traces,{t['query']:v for t,v in zip(family_traces,vecs)})
    s['mined_draft_count']=len(drafts)
    await self.store.upsert('mining_runs',{'_id':'mining_'+key,'family':family,'traces':len(family_traces),'drafts':drafts,'mode':self.embeddings.provider,'note':'候选建议，不自动使用模型工具或规则'})
   replay=await self.strategy_evaluator.replay_skill(s,[t for t in traces if t.get('workflow')==family])
   s['replay']=replay;s['experiment_id']='exp_'+sid.removeprefix('learned_')
   await self.store.upsert_skill(s)
   await self.store.upsert('experiments',{'_id':s['experiment_id'],'artifact_id':sid,'status':'pending_review','stage':0,'replay':replay,'created_at':now()})
   await self._snapshot_strategy(s,'candidate_after_replay')
   proposals.append({'type':'skill','id':sid,'name':s['name'],'replay':replay,'auto_activated':False})
  return proposals
 async def _deploy(self):
  rolled=await self._rollback_failed_experiments()
  return {'skills':0,'hooks':0,'rules':0,'rolled_back':rolled,'note':'候选须经审核进入灰度；监控劣化后自动回滚'}
 async def approve(self,sid,actor):
  s=await self.store.get_skill(sid)
  if not s or s.get('status')!='pending':raise ValueError('没有待审核的候选')
  if not s.get('replay',{}).get('passed'):raise ValueError('回放未通过，禁止发布')
  if s.get('replay',{}).get('sample_count',0)<3:raise ValueError('至少三个不同问题回放通过才允许演示灰度；这不是统计显著性门槛')
  if actor==s.get('created_by'):raise PermissionError('不能自审')
  validate_skill(s)
  for e in await self.store.find('experiments',{'status':'running'}):
   other=await self.store.get_skill(e['artifact_id'])
   if other and other.get('family')==s.get('family'):raise ValueError('同一任务只运行一个灰度实验')
  s.update(status='active',gray_percent=.05,approved_by=actor)
  await self.store.upsert_skill(s);e=await self.store.get('experiments',s['experiment_id']);e.update(status='running',stage=.05,approved_by=actor);await self.store.upsert('experiments',e);await self._snapshot_strategy(s,'approved_canary_5pct');return e
 async def promote(self,sid,actor):
  s=await self.store.get_skill(sid)
  if not s or s.get('status')!='active':raise ValueError('策略不在灰度中')
  e=await self.store.get('experiments',s['experiment_id'])
  data=await self.metrics(sid)
  if min(data['control']['n'],data['treatment']['n'])<self.settings.loop_rollback_min_samples:raise ValueError('独立用户样本不足，不能扩量')
  if data['treatment']['rate']<data['control']['rate']:raise ValueError('处理组较差，不能扩量')
  stages=[.05,.2,.5,1.0];current=stages.index(float(s['gray_percent']));new=stages[min(current+1,3)]
  s['gray_percent']=new;e['stage']=new
  if new==1.0:e['status']='deployed'
  await self.store.upsert_skill(s);await self.store.upsert('experiments',e);await self._snapshot_strategy(s,'promoted_by_'+actor);return e
 async def metrics(self,sid):
  rows=await self.store.find('strategy_executions',{'artifact_id':sid});rows.sort(key=lambda r:r.get('reviewed_at',''));out={}
  for group in ['control','treatment']:
   byuser={r['user_id']:r for r in rows if r.get('group')==group and r.get('quality_success') is not None};rs=list(byuser.values())
   out[group]={'n':len(rs),'rate':sum(bool(r['quality_success']) for r in rs)/len(rs) if rs else None}
  return out
 async def _rollback_failed_experiments(self):
  count=0
  for e in await self.store.find('experiments',{'status':'running'}):
   m=await self.metrics(e['artifact_id']);e['metrics']=m
   if min(m['control']['n'],m['treatment']['n'])>=self.settings.loop_rollback_min_samples:
    if m['treatment']['rate']+self.settings.loop_rollback_margin<m['control']['rate']:
     s=await self.store.get_skill(e['artifact_id'])
     async def apply_rollback():
      s.update(status='deprecated',gray_percent=0,rollback_reason='treatment_underperformed_control')
      await self.store.upsert_skill(s);e.update(status='rolled_back',rolled_back_at=now())
      await self._snapshot_strategy(s,'automatic_rollback')
     recovery=getattr(self,'recovery',None)
     if recovery:
      result=await recovery.rollback(s['family'],s['_id'],apply_rollback,'treatment_underperformed_control')
      if result['status']!='remote_rollback_confirmed':e.update(status='local_frozen_remote_unconfirmed')
     else:await apply_rollback()
     count+=1
   await self.store.upsert('experiments',e)
  return count

class SourceReplay:
 """Paired replay uses actual retrieval/answer/verifier, not hand-assigned improvement scores."""
 def __init__(self,c):self.c=c
 async def replay_skill(self,skill,traces,limit=20):
  details=[];seen=set()
  traces=[t for t in traces if t.get('eval_split')!='frozen_holdout']
  for trace in traces[:limit]:
   if trace['query'] in seen:continue
   seen.add(trace['query'])
   query=trace['query'];depts=[skill['dept_id']];token=scope.set(depts);state=run_state.set({'params':{},'tools':[],'models_enabled':self.c.embeddings.provider!='hash' and local_models(),'profile':'services' if self.c.embeddings.provider!='hash' else 'offline'});at=access.set({'departments':depts,'clearance':'internal'})
   try:
    for label,s in [('baseline',None),('candidate',skill)]:
     original=trace.get('skill_plan') or {}
     plan=SkillPlan(queries=list(original.get('queries') or [query]),top_k=original.get('top_k',self.c.settings.hybrid_topk),instructions=list(original.get('instructions') or []))
     if s:self.c.skill_executor._execute_workflow(plan,s,query)
     chunks=await self.c.retrieval_agent.retrieve(plan.queries,depts,top_k=plan.top_k)
     answer=await self.c.orchestrator.answer_agent.generate(query,chunks,extra_instructions='；'.join(plan.instructions))
     verdict=await self.c.orchestrator.verifier_agent.verify(query,answer,chunks)
     covered=sum(any(t in x['content'] for x in chunks) for t in skill.get('expected_terms',[]))
     row={'trace_id':trace['_id'],'side':label,'source_valid':verdict.passed,'retrieved_ids':[x['_id'] for x in chunks],'expected_terms_covered':covered,'top_k':plan.top_k}
     details.append(row)
   finally:scope.reset(token);run_state.reset(state);access.reset(at)
  pairs=list(zip(details[::2],details[1::2]));passed=bool(pairs) and all(c['source_valid'] and c['expected_terms_covered']>=b['expected_terms_covered'] for b,c in pairs)
  return {'sample_count':len(pairs),'passed':passed,'details':details,'scope':'历史配对回放；仅本地模型模式允许回放生成，外部模式默认原文；词项覆盖和来源校验不是人工准确率','strict_improvements':sum(c['expected_terms_covered']>b['expected_terms_covered'] for b,c in pairs)}
