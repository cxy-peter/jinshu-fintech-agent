"""Financial hooks and rules are reviewed controls; Loop may propose but cannot grant access."""
from app.loop.hook_engine import HookEngine
from .context import scope,run_state

class FintechHooks(HookEngine):
 async def apply(self,hooks,intent,dept_ids):
  allowed=set(scope.get() or []);depts=[d for d in dept_ids if d in allowed];state=run_state.get()
  for h in hooks:
   if h.get('dept_id') and h['dept_id'] not in allowed:continue
   action=h.get('action',{})
   if action.get('type')=='query_context':
    if state is not None:state.setdefault('hook_terms',[]).extend(action.get('terms',[]));state.setdefault('hooks_applied',[]).append(h['_id'])
   elif action.get('type')=='cross_dept_retrieval':
    for d in action.get('departments',[]):
     if d in allowed and d not in depts:depts.append(d)
  return depts

async def seed_controls(store):
 for d in [
  {'_id':'hook_kyc_time','name':'开户时点提醒','dept_id':'dept_risk','scope':'department','trigger':{'keyword_any':['开户','IBAN','KYC']},'action':{'type':'query_context','terms':['字段采集节点','前置信息','待确认']},'status':'active','auto_generated':False,'created_by':'reviewed_demo_design'},
  {'_id':'hook_wealth_scope','name':'理财可比范围提醒','dept_id':'dept_wealth','scope':'department','trigger':{'keyword_any':['对标','净值']},'action':{'type':'query_context','terms':['共同起止日期','同口径']},'status':'active','auto_generated':False,'created_by':'reviewed_demo_design'}]:
  if not await store.get('hooks',d['_id']):await store.upsert_hook(d)
 for id_,text in [('rule_source','引用仅限当前授权、有效版本与源片段'),('rule_no_write','不修改财务账本、不自动批准发行或冻结账户，不外发监管邮件'),('rule_synthetic','所有演示数据和制度都是模拟，输出必须保留此标识')]:
  if not await store.get('rules',id_):await store.upsert_rule({'_id':id_,'scope':'global','status':'active','content':text,'priority':100,'auto_generated':False,'created_by':'reviewed_demo_design'})
