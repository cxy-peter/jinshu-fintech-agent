"""Isolated reproducible Loop laboratory: genuine execution changes, labeled fault injection.
No results here are production quality, user satisfaction, or model improvement estimates.
"""
from __future__ import annotations
import asyncio,copy,json,logging,uuid
from .runtime import Runtime
from .skills import bucket
from .context import run_state
from app.harness.base import VerificationResult

async def run_loop_lab():
 r=await Runtime(instance_id='loop-lab-'+uuid.uuid4().hex[:10]).initialize()
 try:
  question='发行排期需要确认哪些内容'
  # A small development history for actual original SkillMiner/DBSCAN and paired replay.
  variants=[question,'募集结束日与成立日如何安排','发行到期日为什么可能变化']
  first=None
  for i in range(21):
   q=variants[i%3]+f'（模拟任务{i+1}）'
   res=await r.ask(q,user_id='lab_author',workflow='issuance')
   if first is None:first=res
  await r.feedback(first['trace_id'],'lab_author',expected_terms=['顺延','日历版本'],note='LAB：补充检索非工作日处理和日历版本依据')
  job=await r.cycle()
  if job['status']!='completed':raise RuntimeError(job)
  candidates=await r.c.store.list_skills(status='pending')
  if not candidates:raise RuntimeError('Loop did not create a candidate')
  candidate=candidates[0];sid=candidate['_id'];exp=await r.c.loop_engine.approve(sid,'lab_reviewer')
  key=exp['_id'];before=first['execution']['skill_plan'];paired=[]
  def users(percent,which,n,prefix):
   return [prefix+str(i) for i in range(5000) if (bucket(prefix+str(i),key)<percent)==(which=='treatment')][:n]
  for group in ['control','treatment']:
   for u in users(.05,group,3,'lab_good_'+group):
    out=await r.ask(question,user_id=u,workflow='issuance')
    await r.feedback(out['trace_id'],u,signal='up',note='LAB：合成正反馈，仅验证灰度机制')
    paired.append({'user':u,'group':group,'bucket':bucket(u,key),'trace_id':out['trace_id'],'plan':out['execution']['skill_plan'],'source_verified':out['verification']['passed'],'source_metric_only':True,'tool_results':out['tool_results']})
  good_metrics=await r.c.loop_engine.metrics(sid)
  promoted=await r.c.loop_engine.promote(sid,'lab_reviewer')
  # Inject a real verification failure for treatment only in this isolated laboratory.
  # This does NOT claim the learned policy actually caused poorer model quality.
  bad_users=users(.2,'treatment',4,'lab_injected_')
  original_verifier=r.c.orchestrator.verifier_agent
  class InjectedFailure:
   async def verify(self,*a,**k):
    if (run_state.get() or {}).get('user_id') in bad_users:return VerificationResult(False,0,['LAB_FAULT_INJECTION: verifier failure'])
    return await original_verifier.verify(*a,**k)
  r.c.orchestrator.verifier_agent=InjectedFailure()
  bad=[]
  for u in bad_users:
   out=await r.ask(question,user_id=u,workflow='issuance')
   assert out['verification']['passed'] is False
   await r.feedback(out['trace_id'],u,signal='down',note='LAB_FAULT_INJECTION：复核失败对应合成负反馈')
   bad.append({'user':u,'trace_id':out['trace_id'],'verification':out['verification']})
  r.c.orchestrator.verifier_agent=original_verifier
  failed_metrics=await r.c.loop_engine.metrics(sid)
  rolled=await r.c.loop_engine._deploy()
  post=await r.ask(question,user_id=bad_users[0],workflow='issuance')
  final_skill=await r.c.store.get_skill(sid)
  assert final_skill['status']=='deprecated' and rolled['rolled_back']==1
  assert post['execution']['skill_plan']['top_k']==2
  assert all(x['plan']['top_k']==(8 if x['group']=='treatment' else 2) for x in paired)
  assert paired[0]['tool_results']==paired[-1]['tool_results']
  return {'project':'金枢｜金融产品中后台自进化 Agent','profile':'offline',
   'method':'original LoopEngine.run_cycle + original Skill workflow action executor + actual paired retrieval/answer/source checks',
   'warning':'全部模拟；hash向量非语义embedding；无真实LLM；负面结果为显式故障注入；不是质量提升或显著性结论',
   'execute':{'development_traces':21,'baseline_plan':before},'observe_reflect_adapt_deploy_job':job,
   'candidate':candidate,'canary_comparison':paired,'good_metrics':good_metrics,'promoted_to':promoted['stage'],
   'injected_failures':bad,'degraded_metrics':failed_metrics,'automatic_rollback':rolled,'final_experiment':await r.c.store.get('experiments',key),
   'after_rollback':{'plan':post['execution']['skill_plan'],'verification':post['verification'],'trace_id':post['trace_id']},
   'unchanged_financial_results':paired[0]['tool_results']==paired[-1]['tool_results'],
   'strategy_versions':await r.c.store.find('strategy_versions'),'mining_runs':await r.c.store.find('mining_runs')}
 finally:await r.close()

if __name__=='__main__':
 from pathlib import Path
 logging.disable(logging.WARNING)
 report=asyncio.run(run_loop_lab());p=Path('evidence/loop_lab.json');p.parent.mkdir(exist_ok=True)
 p.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
 print(json.dumps({'file':str(p),'candidate':report['candidate']['_id'],'paired_replay':report['candidate']['replay']['sample_count'],'gray_stage':report['promoted_to'],'rollback':report['automatic_rollback'],'restored_top_k':report['after_rollback']['plan']['top_k']},ensure_ascii=False,indent=2))
