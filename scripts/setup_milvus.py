"""Optional Milvus/Zilliz setup: explicit invocation only, no deletes."""
import asyncio,os,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import httpx
from core.store import Store
from core.optional_services import milvus_index
async def main():
    env=os.environ;name=env.get('MILVUS_COLLECTION','jinshu_v10_bge512')
    async with httpx.AsyncClient(timeout=30,follow_redirects=False) as c:
        r=await c.post(env['MILVUS_URI'].rstrip('/')+'/v2/vectordb/collections/create',headers={'Authorization':'Bearer '+env['MILVUS_TOKEN']},json={'collectionName':name,'dimension':512,'idType':'VarChar','maxLength':100,'autoId':False,'metricType':'COSINE','primaryFieldName':'id','vectorFieldName':'vector','enableDynamicField':True})
        r.raise_for_status()
        if r.json().get('code')!=0:raise ValueError('Collection rejected; use a new collection name; never overwrite an incompatible index')
    state=await Store().read();results={}
    for d in state['documents'].values():
        status=await milvus_index(env,d);results[status]=results.get(status,0)+1
    print({'collection':name,'documents':results,'scope':'Index only. Published original documents remain authoritative.'})
if __name__=='__main__':
    try:asyncio.run(main())
    except Exception as e:print('Setup failed:',type(e).__name__);sys.exit(1)
