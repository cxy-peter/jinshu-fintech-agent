"""Add Redis pending recovery and completed-job de-duplication to original JobQueue.
Redis path needs real integration verification; offline worker uses the original MemoryStore.
"""
from app.storage.job_queue import JobQueue,_now
class RecoverableJobQueue(JobQueue):
 async def next_jobs(self,count=10,block_ms=1000):
  redis=getattr(self.session_store,'_redis',None)
  if redis is None:return await super().next_jobs(count,block_ms)
  try:await redis.xgroup_create(self.stream_name,'workers',id='0',mkstream=True)
  except Exception as e:
   if 'BUSYGROUP' not in str(e):raise
  # Reclaim only after a long idle period; at-least-once execution still requires idempotent operations.
  recovered=await redis.xautoclaim(self.stream_name,'workers',self.consumer_name,120000,getattr(self,'reclaim_cursor','0-0'),count=count)
  self.reclaim_cursor=recovered[0] if recovered else '0-0'
  entries=list(recovered[1]) if len(recovered)>1 else []
  if not entries:
   batches=await redis.xreadgroup('workers',self.consumer_name,{self.stream_name:'>'},count=count,block=block_ms)
   entries=[entry for _,batch in batches for entry in batch]
  result=[]
  for stream_id,fields in entries:
   jid=fields.get('job_id') or fields.get(b'job_id');jid=jid.decode() if isinstance(jid,bytes) else jid
   j=await self.store.get('async_jobs',jid)
   if not j or j['status']=='completed':await redis.xack(self.stream_name,'workers',stream_id);continue
   if int(j.get('attempts',0))>=3:
    j.update(status='failed',result={'error':'retry_exhausted'});await self.store.upsert('async_jobs',j);await redis.xack(self.stream_name,'workers',stream_id);continue
   j.update(status='running',attempts=int(j.get('attempts',0))+1,updated_at=_now())
   await self.store.upsert('async_jobs',j);j['_stream_id']=stream_id;result.append(j)
  return result
