"""Versioned, authenticated research library outside the 8 MB governance snapshot.

Full pages are stored as an immutable compressed archive in MongoDB (SQLite for
local development), never in a deployment or public git. A published head moves
only after all upload parts, checksum and document counts have been verified.
Owner-authorized research references do NOT acquire institutional review status.
"""
from __future__ import annotations
import asyncio
import base64
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
import hashlib
import json
import math
import re
import sqlite3
import threading
import uuid
import zlib
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from . import governance as g
from .knowledge import terms
from .rag import chunk_text, digest
from .store import StoreUnavailable

PART_SIZE = 50_000
MAX_ARCHIVE = 8_000_000
MAX_TEXT = 40_000_000


def unpack(data):
    decoder=zlib.decompressobj(16+zlib.MAX_WBITS)
    raw=decoder.decompress(data,MAX_TEXT+1)
    if len(raw)>MAX_TEXT or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
        raise ValueError('资料包解压无效或超过40MB，未发布')
    value=json.loads(raw)
    docs=value.get('documents',[])
    if not isinstance(docs,list) or not 1<=len(docs)<=500:
        raise ValueError('资料包必须含1至500份资料')
    seen=set();catalog=[];page_count=0
    for d in docs:
        if not isinstance(d,dict):raise ValueError('无效资料')
        did=d.get('id','');title=d.get('title','');pages=d.get('pages',[])
        if not re.fullmatch(r'[\w-]{1,120}',did) or did in seen:raise ValueError('资料ID无效或重复')
        if not isinstance(title,str) or not 1<=len(title)<=200 or d.get('synthetic') or d.get('status')!='active':
            raise ValueError('仅恢复明确启用的非合成参考资料')
        if not isinstance(pages,list) or not 1<=len(pages)<=2000:raise ValueError('资料页数无效')
        nums=set();chars=0
        for p in pages:
            if not isinstance(p,dict) or type(p.get('page')) is not int or not 1<=p['page']<=100000 or p['page'] in nums:
                raise ValueError('原文页码无效或重复')
            if not isinstance(p.get('text'),str) or len(p['text'])>100000:raise ValueError('原文单页过长')
            nums.add(p['page']);chars+=len(p['text'])
        if not chars:raise ValueError('资料没有正文')
        seen.add(did);page_count+=len(pages)
        catalog.append(dict(id=did,title=title,pages=len(pages),characters=chars,
                            file_sha256=str(d.get('sha256',''))[:64],
                            content_hash=digest(json.dumps(pages,ensure_ascii=False,sort_keys=True))))
    return value,catalog,page_count


class ReferenceStore:
    def __init__(self,store):
        self.base=store;self.env=store.env;self.path=store.path.parent/'references.sqlite'

    async def get(self,key):
        if self.base.kind=='sqlite':return await asyncio.to_thread(self._sqlite_get,key)
        if self.base.kind!='mongo':return None
        from pymongo import AsyncMongoClient
        async with AsyncMongoClient(self.env['MONGODB_URI'],serverSelectionTimeoutMS=5000) as client:
            row=await client[self.env.get('MONGODB_DB','jinshu')]['reference_library'].find_one({'_id':key})
            if not row:return None
            return bytes(row['payload']) if 'payload' in row else row['value']

    def _db(self):
        self.path.parent.mkdir(parents=True,exist_ok=True)
        db=sqlite3.connect(self.path,timeout=15)
        db.execute('CREATE TABLE IF NOT EXISTS records(id TEXT PRIMARY KEY, payload BLOB NOT NULL, binary INTEGER NOT NULL)')
        return db

    def _sqlite_get(self,key):
        with self._db() as db:
            row=db.execute('SELECT payload,binary FROM records WHERE id=?',(key,)).fetchone()
            return (bytes(row[0]) if row[1] else json.loads(row[0])) if row else None

    def writable(self):
        if self.env.get('JINSHU_STORE_READ_ONLY')=='1':raise StoreUnavailable('资料库只读，未修改原数据')
        if self.base.kind not in ('sqlite','mongo'):raise StoreUnavailable('共享大资料库需要MongoDB或本地SQLite')

    async def put(self,key,value,*,temporary=False):
        self.writable()
        if self.base.kind=='sqlite':
            def save():
                with self._db() as db:
                    db.execute('INSERT INTO records VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,binary=excluded.binary',
                               (key,value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False),int(isinstance(value,bytes))))
            return await asyncio.to_thread(save)
        from pymongo import AsyncMongoClient
        async with AsyncMongoClient(self.env['MONGODB_URI'],serverSelectionTimeoutMS=5000) as client:
            col=client[self.env.get('MONGODB_DB','jinshu')]['reference_library']
            row={'payload':value} if isinstance(value,bytes) else {'value':value}
            if temporary:
                row['expires_at']=datetime.now(timezone.utc)+timedelta(days=1)
                await col.create_index('expires_at',expireAfterSeconds=0)
            await col.replace_one({'_id':key},{'_id':key,**row},upsert=True)

    async def activate(self,head,expected):
        self.writable()
        if self.base.kind=='sqlite':
            def save():
                with self._db() as db:
                    db.execute('BEGIN IMMEDIATE')
                    row=db.execute("SELECT payload FROM records WHERE id='head'").fetchone()
                    previous=json.loads(row[0])['release'] if row else None
                    if previous==head['release']:return
                    if previous!=expected:raise ValueError('共享资料版本已改变，请重新检查后导入')
                    db.execute("INSERT INTO records VALUES('head',?,0) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",(json.dumps(head,ensure_ascii=False),))
            return await asyncio.to_thread(save)
        from pymongo import AsyncMongoClient
        from pymongo.errors import DuplicateKeyError
        async with AsyncMongoClient(self.env['MONGODB_URI'],serverSelectionTimeoutMS=5000) as client:
            col=client[self.env.get('MONGODB_DB','jinshu')]['reference_library']
            old=await col.find_one({'_id':'head'})
            if old and old['value']['release']==head['release']:return
            try:
                result=await col.replace_one({'_id':'head','value.release':expected},{'_id':'head','value':head},upsert=expected is None)
            except DuplicateKeyError:raise ValueError('共享资料版本已改变，未覆盖')
            if not (result.modified_count or result.upserted_id):raise ValueError('共享资料版本冲突，未覆盖')


class ReferenceIndex:
    def __init__(self,pack):
        self.docs={d['id']:d for d in pack['documents']};self.rows=[];self.postings=defaultdict(list);self.lengths=[]
        for d in self.docs.values():
            for page in d['pages']:
                for ch in chunk_text(page['text'],d['title']):
                    if not ch['text'].strip():continue
                    i=len(self.rows);row=dict(doc_id=d['id'],title=d['title'],section=ch['section'],text=ch['text'],page=page['page'],hash=ch['hash'],chunk_id=d['id']+':'+str(i))
                    self.rows.append(row);tf=terms(d['title']+' '+ch['text']);self.lengths.append(sum(tf.values()))
                    for term,freq in tf.items():self.postings[term].append((i,freq))
        self.avg=sum(self.lengths)/max(1,len(self.rows)) or 1

    def search(self,query,limit=4):
        definition=bool(re.search(r'是什么|什么是|定义|含义|what is|definition',query,re.I))
        # Formatting/source instructions are not topic constraints. Preserve actual
        # domain terms so that an unsupported SOP is still a knowledge gap.
        query=re.sub(r'(?:请)?(?:结合|根据|依据|参考)(?:本次|这些|我的|已有|当前)?(?:的)?(?:共享)?(?:资料库|资料|原文|文献|研报)(?:里面|里的|中的|中)?',' ',query)
        query=re.sub(r'(?:请|帮我)?(?:简明|简单|简洁|详细|通俗)(?:地)?(?:解释|说明|回答|总结)(?:一下)?',' ',query)
        query=re.sub(r'(?:并|请|同时)?(?:注明|标注|附上|列出|给出)(?:一下)?(?:原文|引用|来源|文件)?(?:的)?(?:页码|出处|编号|来源)',' ',query)
        query=re.sub(r'\b(?:based on (?:the )?(?:shared )?(?:library|sources|documents)|with (?:original )?page numbers|briefly explain)\b',' ',query,flags=re.I)
        query=re.sub(r'请问|请帮我|帮我|解释一下|介绍一下|是什么|有什么|有哪些|怎么|如何|为什么|什么|一下',' ',query)
        wanted=set(terms(query));scores=Counter();covered=defaultdict(set);total=len(self.rows)
        for t in wanted:
            found=self.postings.get(t,[]);idf=math.log(1+(total-len(found)+.5)/(len(found)+.5))
            for i,tf in found:
                scores[i]+=idf*tf*2.2/(tf+1.2*(.25+.75*self.lengths[i]/self.avg));covered[i].add(t)
        ranked=[]
        for i,score in scores.items():
            row=self.rows[i]
            if len(covered[i])/max(1,len(wanted))<.45:continue
            if row['text'].count('�')/max(1,len(row['text']))>.08:continue
            if len(re.findall(r'(?:\.{4,}|…{2,})\s*\d+',row['text']))>=3:score*=.18
            if definition:
                if len(re.findall(r'\d',row['text']))/max(1,len(row['text']))>.12:score*=.3
                if re.search(r'什么是|本质上|核心思想|是指|定义|指的是',row['text']):score*=1.8
            ranked.append((score,i))
        seen=Counter();out=[]
        for score,i in sorted(ranked,reverse=True):
            r=self.rows[i]
            if seen[r['doc_id']]>=2:continue
            seen[r['doc_id']]+=1;out.append(r|{'score':round(score,4)})
            if len(out)>=limit:break
        return out


_cache={};_cache_lock=threading.Lock()
def index_for(release,data):
    with _cache_lock:
        if release not in _cache:
            pack,_,_=unpack(data);idx=ReferenceIndex(pack);_cache.clear();_cache[release]=idx
        return _cache[release]


async def loaded(ref,head):
    # Never acquire the long-running index build lock on the event loop.
    existing=_cache.get(head['release'])
    if existing:return existing
    data=await ref.get('archive:'+head['release'])
    if not data or hashlib.sha256(data).hexdigest()!=head['release']:raise StoreUnavailable('共享资料正文校验失败，未引用')
    return await asyncio.to_thread(index_for,head['release'],data)


def records(head):
    return [d|dict(status='active_reference',version=head['release'],origin='shared_reference',
                  department='shared',author=head['author'],reviewer=None,
                  review_note='用户授权恢复的学习参考，不代表机构制度审核',
                  published_at=head['published_at'],embedding='page_bm25',chunks=[],chunk_count=None)
            for d in head['catalog']]


async def search(store,query,who,limit=4):
    if not who:return [],'login_required'
    ref=ReferenceStore(store);head=await ref.get('head')
    if not head:return [],'not_imported'
    idx=await loaded(ref,head)
    hits=await asyncio.to_thread(idx.search,query,limit)
    return [r|dict(version=head['release'],origin='shared_reference',department='shared',
                   authority='用户授权恢复的学习参考；非现行机构制度',external_allowed=True) for r in hits], 'shared_reference_page_bm25'


async def verify(store,sources,request):
    refs=[s for s in sources if s.get('origin')=='shared_reference']
    if not refs:return
    g.require(g.actor(await store.read(),request),'editor','reviewer','operator')
    head=await ReferenceStore(store).get('head')
    if not head or any(s['version']!=head['release'] for s in refs):raise ValueError('回答期间共享资料版本已更新，请重新提问')


class Input(BaseModel):model_config=ConfigDict(extra='forbid')
class ImportStart(Input):
    sha256:str=Field(pattern=r'^[a-f0-9]{64}$')
    compressed_bytes:int=Field(ge=1,le=MAX_ARCHIVE)
class Part(Input):data:str=Field(min_length=1,max_length=68000)
class Publish(Input):
    sharing_confirmed:StrictBool=False
    expected_documents:int=Field(ge=1,le=500)
    expected_pages:int=Field(ge=1,le=100000)


def install(app,store,authorize):
    ref=ReferenceStore(store)
    async def who(request,write=False):
        actor=g.actor(await store.read(),request)
        g.require(actor,*(['editor'] if write else ['editor','reviewer','operator']))
        return actor
    async def pending(identifier,request):
        actor=await who(request,True);row=await ref.get('upload:'+identifier)
        if not row or row['author']!=actor['username']:raise HTTPException(404,'导入任务不存在')
        if row['expires']<datetime.now(timezone.utc).timestamp():raise ValueError('导入任务已过期')
        return row

    @app.post('/api/reference-imports')
    async def start(d:ImportStart,request:Request,c=Depends(authorize)):
        actor=await who(request,True);head=await ref.get('head');identifier=uuid.uuid4().hex
        row=d.model_dump()|dict(id=identifier,author=actor['username'],expected=head['release'] if head else None,
            parts=math.ceil(d.compressed_bytes/PART_SIZE),expires=(datetime.now(timezone.utc)+timedelta(days=1)).timestamp())
        await ref.put('upload:'+identifier,row,temporary=True)
        return {'id':identifier,'parts':row['parts'],'part_size':PART_SIZE}

    @app.put('/api/reference-imports/{identifier}/parts/{part}')
    async def upload_part(identifier:str,part:int,d:Part,request:Request,c=Depends(authorize)):
        row=await pending(identifier,request)
        if not 0<=part<row['parts']:raise ValueError('分片编号无效')
        raw=base64.b64decode(d.data,validate=True)
        size=min(PART_SIZE,row['compressed_bytes']-part*PART_SIZE)
        if len(raw)!=size:raise ValueError('分片长度不匹配')
        key=f'part:{identifier}:{part}';previous=await ref.get(key)
        if previous is not None and previous!=raw:raise ValueError('分片已存在不同内容，未覆盖')
        await ref.put(key,raw,temporary=True)
        return {'part':part,'bytes':len(raw)}

    @app.post('/api/reference-imports/{identifier}/publish')
    async def publish(identifier:str,d:Publish,request:Request,c=Depends(authorize)):
        row=await pending(identifier,request)
        if not d.sharing_confirmed:raise ValueError('请先确认将这批资料共享给网站登录用户并用于资料问答')
        gate=asyncio.Semaphore(4)
        async def read_part(n):
            async with gate:return await ref.get(f'part:{identifier}:{n}')
        parts=await asyncio.gather(*(read_part(n) for n in range(row['parts'])))
        if any(x is None for x in parts):raise ValueError('资料分片未上传完整')
        raw=b''.join(parts)
        if len(raw)!=row['compressed_bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('资料包校验失败，未发布')
        _,catalog,pages=await asyncio.to_thread(unpack,raw)
        if len(catalog)!=d.expected_documents or pages!=d.expected_pages:raise ValueError('目录或页数不匹配，未发布')
        head=dict(release=row['sha256'],catalog=catalog,documents=len(catalog),pages=pages,
                  compressed_bytes=len(raw),author=row['author'],published_at=g.now(),
                  scope='authenticated_research_reference',authorization='owner_requested_restore')
        await ref.put('archive:'+row['sha256'],raw)
        await ref.activate(head,row['expected'])
        def log(s):
            if not any(a.get('release')==head['release'] for a in s['audit']):
                g.audit(s,'owner_reference_restore',row['author'],release=head['release'],documents=len(catalog),pages=pages)
        await store.mutate(log)
        return {k:v for k,v in head.items() if k!='catalog'}

    @app.get('/api/library/reference-catalog')
    async def catalog(request:Request,c=Depends(authorize)):
        await who(request);head=await ref.get('head')
        return {'documents':records(head) if head else [],'release':head['release'] if head else None}

    @app.get('/api/library/reference-search')
    async def lookup(request:Request,q:str='',c=Depends(authorize)):
        actor=await who(request)
        if not 1<=len(q.strip())<=6000:raise ValueError('请输入有效检索词')
        hits,mode=await search(store,q,actor,6)
        return {'sources':hits,'mode':mode,'model_called':False}

    @app.get('/api/library/reference/{did}/page/{page}')
    async def page(did:str,page:int,request:Request,c=Depends(authorize)):
        await who(request);head=await ref.get('head')
        if not head:raise HTTPException(404,'未找到资料')
        idx=await loaded(ref,head);doc=idx.docs.get(did)
        row=next((p for p in doc['pages'] if p['page']==page),None) if doc else None
        if not row:raise HTTPException(404,'未找到原文页码')
        return {'id':did,'title':doc['title'],'version':head['release'],'pages':[p['page'] for p in doc['pages']],**row}
