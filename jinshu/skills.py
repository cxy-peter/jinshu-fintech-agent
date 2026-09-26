"""Executable skills extend the original SkillExecutor; stable buckets, safe tools and traces."""
import hashlib,uuid
from datetime import datetime,timezone
from app.loop.skill_executor import SkillExecutor,SkillPlan
from .context import scope,run_state
from .fixtures import WORKFLOWS
from . import tools

ALLOWED_TEMPLATES={'范围—指标—来源—复核','日期—差异—待确认','输入—异常—输出','字段—时点—责任—待确认','状态—证据—人工复核','输入—约束—候选—审批','核对—差异—来源','依据—行动—转人工','结论—证据—操作—复核'}

def bucket(user_id,experiment_id):return int(hashlib.sha256(f'{experiment_id}:{user_id}'.encode()).hexdigest()[:8],16)/2**32

def validate_skill(s):
 if s.get('dept_id') not in {w['dept'] for w in WORKFLOWS.values()}:raise ValueError('Skill缺少合法部门')
 if not s.get('trigger',{}).get('intent_patterns'):raise ValueError('没有触发条件')
 for step in s.get('action',{}).get('steps',[]):
  kind=step.get('action');p=step.get('params') or {}
  if kind=='retrieve':
   if not 1<=int(p.get('top_k',5))<=12:raise ValueError('top-k超限')
   if len(str(p.get('query','')))>300:raise ValueError('查询扩展过长')
  elif kind=='generate':
   if p.get('template') not in ALLOWED_TEMPLATES:raise ValueError('未批准的回答模板')
  elif kind=='call_tool':
   if p.get('tool') not in tools.TOOLS:raise ValueError('未授权工具')
  else:raise ValueError('不允许Skill修改代码、权限、财务值或正式风控规则')
 return s

async def seed_skills(store):
 for name,w in WORKFLOWS.items():
  s={'_id':'base_'+name,'family':name,'name':w['name'],'dept_id':w['dept'],'scope':'department','status':'active','version':1,'gray_percent':1,'trigger':{'intent_patterns':w['triggers']},'action':{'type':'workflow','steps':[{'action':'retrieve','params':{'query':'{matter} '+w['query'],'top_k':2}},{'action':'generate','params':{'template':w['template']}}]},'created_by':'seed','created_at':datetime.now(timezone.utc).isoformat()}
  if w['tool']:s['action']['steps'].insert(0,{'action':'call_tool','params':{'tool':w['tool']}})
  validate_skill(s)
  if not await store.get_skill(s['_id']):await store.upsert_skill(s)

class ExecutableSkillExecutor(SkillExecutor):
 async def matching(self,query,dept_ids=None):
  found=await super().matching(query,dept_ids)
  state=run_state.get() or {};family=state.get('selected_workflow')
  if family:
   found=[s for s in await self.store.list_skills(status='active') if s.get('family')==family]
  allowed=scope.get()
  found=[s for s in found if allowed is None or s.get('dept_id') in allowed]
  recovery=getattr(self,'recovery',None)
  if recovery:
   excluded=[s['_id'] for s in found if s.get('experiment_id') and recovery.frozen(s.get('family'))]
   found=[s for s in found if s['_id'] not in excluded]
   if excluded and run_state.get() is not None:run_state.get()['local_recovery']={'excluded_candidates':excluded,'mode':'stable_baseline_only'}
  return found
 async def prepare(self,query,base_queries,skills,session_id,user_id):
  plan=SkillPlan(queries=list(base_queries),top_k=self.default_top_k);state=run_state.get()
  for s in sorted(skills,key=lambda s:(s.get('version',1),s['_id'])):
   validate_skill(s);exp=s.get('experiment_id') or s['_id'];b=bucket(user_id,exp)
   group='treatment' if b<float(s.get('gray_percent',1)) else 'control';eid='sx_'+uuid.uuid4().hex
   row={'_id':eid,'artifact_id':s['_id'],'version':s.get('version',1),'experiment_id':exp,'group':group,'bucket':b,'session_id':session_id,'user_id':user_id,'query':query,'success':None,'created_at':datetime.now(timezone.utc).isoformat()}
   await self.store.upsert('strategy_executions',row);plan.execution_ids.append(eid)
   if group=='treatment':plan.treatment_skills.append(s);self._execute_workflow(plan,s,query)
  plan.queries=list(dict.fromkeys(plan.queries))[:8];plan.top_k=min(plan.top_k,12)
  if state is not None:
   state['skill_plan']={'queries':plan.queries,'top_k':plan.top_k,'instructions':plan.instructions,'skills':[s['_id'] for s in plan.treatment_skills],'executions':plan.execution_ids}
   for s in plan.treatment_skills:
    for step in s.get('action',{}).get('steps',[]):
     if step['action']=='call_tool':
      tool=step['params']['tool']
      if tool not in [r['tool'] for r in state.setdefault('tools',[])]:
       from .python_skills import REGISTRY,execute
       runner=getattr(self,'tool_runner',None)
       result=runner(tool,state.get('params',{})) if runner else execute(tool,state.get('params',{})) if tool in REGISTRY else tools.run(tool,state.get('params',{}));state['tools'].append(result)
  return plan
