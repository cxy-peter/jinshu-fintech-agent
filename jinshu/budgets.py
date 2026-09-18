"""Stage deadlines without replacing the original DAG; failures remain observable."""
import asyncio,time
from .context import run_state

class BoundedNode:
 def __init__(self,target,method,name,seconds,fallback):
  self.target=target;self.method=method;self.name=name;self.seconds=seconds;self.fallback=fallback
 def __getattr__(self,name):
  original=getattr(self.target,name)
  if name!=self.method:return original
  async def invoke(*args,**kwargs):
   started=time.perf_counter();status='completed';state=run_state.get()
   try:return await asyncio.wait_for(original(*args,**kwargs),timeout=self.seconds)
   except (asyncio.TimeoutError, ConnectionError, OSError) as exc:
    status='timeout' if isinstance(exc,asyncio.TimeoutError) else 'dependency_unavailable'
    if state is not None:state.setdefault('degraded',[]).append(self.name+'_'+status)
    result=self.fallback(*args,**kwargs)
    if hasattr(result,'__await__'):result=await result
    return result
   finally:
    if state is not None:state.setdefault('stages',[]).append({'node':self.name,'budget_seconds':self.seconds,'elapsed_ms':round((time.perf_counter()-started)*1000,2),'status':status})
  return invoke
