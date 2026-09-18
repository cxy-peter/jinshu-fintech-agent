"""Keep original BM25/vector/RRF/Reranker roles; hydrate authoritative text BEFORE reranking."""
import asyncio,hashlib,inspect,math,os,json
from datetime import date
from app.harness.agents.retrieval_agent import RetrievalAgent
from app.retrieval.vector_store import VectorStore
from .context import scope,run_state,access

async def valid_chunk(store,id_,depts):
 c=await store.get('chunks',id_)
 if not c or c.get('dept_id') not in set(depts):return None
 d=await store.get_document(c.get('doc_id',''))
 if not d or d.get('status')!='active':return None
 from .document_service import can_read
 if not can_read(d,access.get()):return None
 now=date.today().isoformat()
 if d.get('effective_date') and d['effective_date']>now:return None
 if d.get('expiry_date') and d['expiry_date']<now:return None
 head=await store.get('document_heads',d.get('topic_key',''))
 if d.get('topic_key') and (not head or head['doc_id']!=d['_id']):return None
 if hashlib.sha256(c['content'].encode()).hexdigest()!=c.get('content_hash'):return None
 return {**c,'id':id_,'doc_title':d['title'],'document_version':d['version'],'external_allowed':d.get('external_allowed',False),'sensitivity':d.get('sensitivity','internal')}

class TrustedRetrieval(RetrievalAgent):
 async def retrieve(self,queries,dept_ids=None,top_k=5):
  allowed=scope.get();depts=list(dept_ids or allowed or [])
  if allowed is not None:depts=[d for d in depts if d in allowed]
  if not depts:return []
  fused={};sources={};degraded=[]
  for query in list(dict.fromkeys(queries))[:8]:
   try:
    if self.embeddings.provider!='hash' and not (run_state.get() or {}).get('allow_external'):raise PermissionError('External query encoding not opted in')
    vec=await asyncio.wait_for(self.embeddings.embed_query(query),timeout=8)
   except Exception:vec=None;degraded.append('embedding_unavailable_keywords_only')
   for dept in depts:
    bm=self.hybrid.bm25.search(query,top_k=self.hybrid.bm25_top,dept_id=dept)
    if inspect.isawaitable(bm):bm=await bm
    try:v=await self.hybrid.vector_store.search(vec,top_k=self.hybrid.vector_top,dept_id=dept) if vec is not None else []
    except Exception:v=[];degraded.append('vector_unavailable_keywords_only')
    # Do not use rank score alone as evidence. Positive candidates still require source checks.
    for route,hits in [('bm25',bm),('vector',v)]:
     for rank,h in enumerate(hits):
      if h.get('score',0)<=0:continue
      idx=h['id'];fused[idx]=fused.get(idx,0)+1/(60+rank+1);sources.setdefault(idx,set()).add(route)
  hydrated=[]
  for idx in sorted(fused,key=fused.get,reverse=True)[:80]:
   c=await valid_chunk(self.store,idx,depts)
   if c:hydrated.append(c|{'_rrf':fused[idx],'score':fused[idx],'retrieval_routes':sorted(sources[idx])})
  # The original reranker receives full text instead of vector metadata-only hits.
  try:
   from app.retrieval.reranker import HeuristicReranker
   reranker=self.hybrid.reranker
   if not isinstance(reranker,HeuristicReranker) and not ((run_state.get() or {}).get('allow_external') and all(h.get('external_allowed') for h in hydrated)):
    reranker=HeuristicReranker();degraded.append('external_reranker_not_approved_local_order')
   ranked=await asyncio.wait_for(reranker.rerank(' '.join(queries),hydrated,top_k=min(max(top_k,1),12)),timeout=8)
  except Exception:ranked=hydrated[:top_k];degraded.append('reranker_timeout_rrf_order')
  final=[]
  for h in ranked:
   c=await valid_chunk(self.store,h.get('_id') or h['id'],depts)
   if c:final.append(h|c)
  state=run_state.get()
  if state is not None:
   state.setdefault('retrieval',[]).append({'queries':queries,'top_k':top_k,'bm25_candidates':sum('bm25' in s for s in sources.values()),'vector_candidates':sum('vector' in s for s in sources.values()),'hydrated':len(hydrated),'returned':len(final),'ids':[x['_id'] for x in final],'degraded':degraded,'embedding_mode':self.embeddings.provider})
  return final

class MilvusVectorStore(VectorStore):
 """Real MilvusClient adapter. Unknown/unavailable Milvus never silently becomes memory."""
 def __init__(self,uri,collection,dimension,token='',client=None):
  self.dim=dimension;self.collection=collection
  if client is None:
   from pymilvus import MilvusClient
   client=MilvusClient(uri=uri,token=token)
  self.client=client
  if not client.has_collection(collection_name=collection):
   client.create_collection(collection_name=collection,dimension=dimension,id_type='string',max_length=256,metric_type='COSINE',consistency_level='Strong')
 def check(self,v):
  if len(v)!=self.dim or any(not math.isfinite(float(x)) for x in v):raise ValueError('Embedding dimension/model mismatch: rebuild a separate index')
 async def add(self,id_,vector,metadata):
  self.check(vector);await asyncio.to_thread(self.client.upsert,collection_name=self.collection,data=[{'id':id_,'vector':vector,**metadata}])
 async def search(self,vector,top_k=10,dept_id=None):
  self.check(vector)
  if not dept_id:raise PermissionError('Milvus requires explicit department scope')
  res=await asyncio.to_thread(self.client.search,collection_name=self.collection,data=[vector],filter='dept_id == '+json.dumps(dept_id),limit=top_k,output_fields=['doc_id','dept_id','chunk_index'])
  return [{'id':str(h['id']),'score':float(h['distance']),**h.get('entity',{})} for h in res[0]]
 async def delete_by_doc(self,doc_id):await asyncio.to_thread(self.client.delete,collection_name=self.collection,filter='doc_id == '+json.dumps(doc_id))
 async def count(self):return int((await asyncio.to_thread(self.client.get_collection_stats,collection_name=self.collection))['row_count'])
