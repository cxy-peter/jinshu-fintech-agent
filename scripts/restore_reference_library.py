"""Owner-authorized restore via the app's authenticated API. No DB secret needed.

The corpus stays out of Git and deployment bundles. Uploads remain invisible
until all parts, hashes and counts pass. Existing institutional records survive.
"""
import argparse
import asyncio
import base64
import csv
import getpass
import gzip
import hashlib
import json
import os
from pathlib import Path
import httpx

async def run(a):
    raw=Path(a.pack).read_bytes();pack=json.loads(raw);docs=pack['documents']
    pages=sum(len(d['pages']) for d in docs)
    compressed=gzip.compress(raw,mtime=0)
    password=os.environ.get('JINSHU_IMPORT_PASSWORD') or getpass.getpass('Account password: ')
    async with httpx.AsyncClient(base_url=a.url.rstrip('/'),timeout=120,follow_redirects=False) as c:
        async def call(method,url,**kw):
            r=await c.request(method,url,**kw)
            if not r.is_success:raise RuntimeError(f'{method} {url}: {r.status_code}: {r.text[:300]}')
            return r.json()
        await call('POST','/api/workspace/login',json={'username':a.username,'password':password})
        row=await call('POST','/api/reference-imports',json={'sha256':hashlib.sha256(compressed).hexdigest(),'compressed_bytes':len(compressed)})
        gate=asyncio.Semaphore(4)
        async def part(n):
            body=compressed[n*row['part_size']:(n+1)*row['part_size']]
            async with gate:await call('PUT',f"/api/reference-imports/{row['id']}/parts/{n}",json={'data':base64.b64encode(body).decode()})
        await asyncio.gather(*(part(n) for n in range(row['parts'])))
        result=await call('POST',f"/api/reference-imports/{row['id']}/publish",json={'sharing_confirmed':True,'expected_documents':len(docs),'expected_pages':pages})
        catalog=await call('GET','/api/library/reference-catalog')
        assert {d['id'] for d in catalog['documents']}=={d['id'] for d in docs}
        result['catalog_verified']=True
        print(json.dumps(result,ensure_ascii=False))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True);p.add_argument('--pack',required=True)
    p.add_argument('--username',default='editor');p.add_argument('--share-with-logged-in-users',action='store_true',required=True)
    a=p.parse_args()
    from urllib.parse import urlsplit
    u=urlsplit(a.url)
    if u.scheme!='https' and not (u.scheme=='http' and u.hostname in ('127.0.0.1','localhost')):p.error('HTTPS required except loopback')
    asyncio.run(run(a))
