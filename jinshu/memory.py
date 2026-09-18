"""Original five planes remain, with finite TTL offline and stricter context budget."""
import copy,time
from app.storage.redis_store import MemorySessionStore
from app.memory.context_builder import MemoryContextBuilder
from .retrieval import valid_chunk

class ExpiringSessionStore(MemorySessionStore):
 def __init__(self):super().__init__();self.expiries={}
 async def set_session(self,sid,data,ttl=1800):await super().set_session(sid,data,ttl);self.expiries[sid]=time.time()+ttl
 async def get_session(self,sid):
  if self.expiries.get(sid,0)<=time.time():await self.delete_session(sid);return None
  return copy.deepcopy(await super().get_session(sid))

class BudgetedContextBuilder(MemoryContextBuilder):
 async def build(self,*a,**k):
  context=await super().build(*a,**k);depts=k.get('dept_ids') or (a[3] if len(a)>3 else [])
  validated=[]
  for c in context.evidence_chunks:
   current=await valid_chunk(self.store,c['_id'],depts)
   if current:validated.append(current)
  retained_refs={r.get('chunk_id') for item in context.org_items for r in item.get('source_refs',[])}
  context.evidence_chunks=[c for c in validated if c['_id'] in retained_refs]
  # Original budget loop cannot shrink a long summary/entities-only context.
  if len(context.prompt_text())>self.max_chars:
   context.session['summary']=str(context.session.get('summary',''))[:self.max_chars//4]
   context.session['entities']={k:str(v)[:200] for k,v in list(context.session.get('entities',{}).items())[:5]}
   self._apply_budget(context)
  while len(context.prompt_text())>self.max_chars:
   if context.session.get('entities'):context.session['entities'].pop(next(iter(context.session['entities'])))
   elif context.session.get('summary'):context.session['summary']=context.session['summary'][:max(0,len(context.session['summary'])//2)]
   elif context.org_items:context.org_items.pop()
   elif context.user_items:context.user_items.pop()
   elif context.session.get('recent_messages'):context.session['recent_messages'].pop(0)
   else:break
  from .context import run_state
  state=run_state.get()
  if state is not None:state['memory_context']={'chars':len(context.prompt_text()),'budget':self.max_chars,'user_items':len(context.user_items),'organization_items':len(context.org_items),'evidence_ids':[c['_id'] for c in context.evidence_chunks],'procedures':{k:len(v) for k,v in context.procedures.items()},'entities':context.session.get('entities',{})}
  return context

from app.memory.user_semantic import UserSemanticMemory
from app.memory.organization import OrganizationMemory
class ConsentMemory(UserSemanticMemory):
 async def remember(self,user_id,key,value,**kwargs):
  if key not in {'answer_style','language','default_workflow'}:raise ValueError('仅允许低敏偏好白名单；不存账户身份或客户记录')
  if kwargs.get('consent') is not True:raise ValueError('需明确同意才记忆')
  if kwargs.get('source_type','explicit_user')!='explicit_user':raise ValueError('模型推断不得直接写入用户偏好')
  if len(str(value))>120:raise ValueError('偏好内容过长')
  return await super().remember(user_id,key,value,**kwargs)

class TrustedOrganizationMemory(OrganizationMemory):
 async def _verify_sources(self,refs,dept_id):
  valid=[]
  for ref in refs:
   c=await self.store.get('chunks',ref.get('chunk_id',''))
   if not c or c.get('doc_id')!=ref.get('doc_id'):continue
   current=await valid_chunk(self.store,c['_id'],[dept_id] if dept_id else [c['dept_id']])
   if not current or (ref.get('document_version') and str(ref['document_version'])!=str(current['document_version'])):continue
   valid.append({'doc_id':c['doc_id'],'chunk_id':c['_id'],'document_version':current['document_version']})
  return valid
