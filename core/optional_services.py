"""Optional services never own factual authority, permissions or publication.
All URLs are server configuration, never request-provided. No silent fake success.
"""
import json
import httpx
from .rag import MODEL_ID, digest


async def working_history(env,conversation,history):
    if not env.get('REDIS_ADDR') or not conversation:return history,'persistent_history'
    try:
        import redis.asyncio as redis
        key='jinshu:v10:working:'+digest(conversation['owner']+'|'+conversation['id'])+':'+str(conversation['revision'])
        async with redis.from_url(env['REDIS_ADDR'],decode_responses=True,socket_connect_timeout=2,socket_timeout=2) as client:
            cached=await client.get(key)
            if cached:
                value=json.loads(cached)
                if value==history:return value,'redis_hit'
            await client.set(key,json.dumps(history,ensure_ascii=False),ex=1800)
        return history,'redis_updated'
    except Exception:return history,'redis_unavailable_persistent_history'


async def pi_rewrite(env,query):
    if env.get('PI_AGENT_ENABLED')!='true' or not env.get('PI_AGENT_URL') or not env.get('INTERNAL_API_TOKEN'):
        return query,'python_bounded_rewrite'
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
            response=await client.post(env['PI_AGENT_URL'].rstrip('/')+'/v1/agent/run',
                headers={'X-Internal-Token':env['INTERNAL_API_TOKEN']},json={
                    'agentType':'rewrite','systemPrompt':'只改写检索表达，保留问题中的数字、否定、机构、产品和条件。不回答问题。不调用工具。返回 JSON {"queries":["查询"]}。',
                    'prompt':query,'outputMode':'json','allowedTools':[],'timeoutMs':8000,'traceId':digest(query)[:16]})
            response.raise_for_status();body=response.json()
            if body.get('code')!=0:raise ValueError('pi failure')
            output=body['data']['output'];output=json.loads(output) if isinstance(output,str) else output
            queries=output.get('queries',[])
            if not isinstance(queries,list) or not all(isinstance(q,str) and 0<len(q)<=500 for q in queries) or not 1<=len(queries)<=3:raise ValueError('pi invalid schema')
            return query+'\n'+'\n'.join(queries),'pi_rewrite'
    except Exception:return query,'pi_unavailable_python_rewrite'


async def milvus_index(env,document):
    if not env.get('MILVUS_URI') or not env.get('MILVUS_TOKEN'):return 'not_configured'
    rows=[{'id':document['id']+':'+str(c['index']),'vector':c['vector'],'doc_id':document['id'],
           'model':MODEL_ID} for c in document['chunks'] if c.get('embedding_model')==MODEL_ID]
    if not rows:return 'no_semantic_vectors'
    try:
        async with httpx.AsyncClient(timeout=10,follow_redirects=False) as client:
            response=await client.post(env['MILVUS_URI'].rstrip('/')+'/v2/vectordb/entities/upsert',
                headers={'Authorization':'Bearer '+env['MILVUS_TOKEN']},
                json={'collectionName':env.get('MILVUS_COLLECTION','jinshu_v10_bge512'),'data':rows})
            response.raise_for_status()
            if response.json().get('code')!=0:raise ValueError('vector index rejected')
        return 'indexed'
    except Exception:return 'milvus_unavailable_local_semantic_retained'


async def milvus_candidates(env,vector,allowed_ids):
    if not env.get('MILVUS_URI') or not env.get('MILVUS_TOKEN'):return None,'local_semantic'
    if not allowed_ids:return [],'no_authorized_candidates'
    try:
        async with httpx.AsyncClient(timeout=8,follow_redirects=False) as client:
            response=await client.post(env['MILVUS_URI'].rstrip('/')+'/v2/vectordb/entities/search',
                headers={'Authorization':'Bearer '+env['MILVUS_TOKEN']},json={
                    'collectionName':env.get('MILVUS_COLLECTION','jinshu_v10_bge512'),
                    'data':[vector],'limit':40,'filter':'id in '+json.dumps(allowed_ids),
                    'outputFields':['doc_id','model']})
            response.raise_for_status();body=response.json()
            if body.get('code')!=0:raise ValueError('milvus failure')
            # Only ids enter core retrieval. Text/scope/status always refill from fact plane.
            return [r['id'] for r in body['data'] if r.get('id') in allowed_ids and r.get('model')==MODEL_ID],'milvus_semantic'
    except Exception:return None,'milvus_unavailable_local_semantic'
