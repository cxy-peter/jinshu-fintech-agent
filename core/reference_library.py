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
import gzip
import json
import math
import re
import sqlite3
import threading
import time
import uuid
import zlib
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, StrictBool
from . import governance as g
from .rag import chunk_text, digest
from .retrieval_query import (LEXICON_SIGNATURE, terms, plan_query, body_text,
                              evidence_match, normalize)
from .store import StoreUnavailable

PART_SIZE = 50_000
MAX_ARCHIVE = 8_000_000
MAX_TEXT = 40_000_000
MAX_INDEX = 12_000_000  # Below MongoDB's 16 MiB BSON document boundary.
MAX_SHARED_INDEX = 48_000_000  # Shared derived indexes may span bounded records.
INDEX_PART_SIZE = 4_000_000
MAX_INDEX_TEXT = 150_000_000
INDEX_SCHEMA = 'page-bm25-alias-v5-' + LEXICON_SIGNATURE


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
        from .mongo_pool import collection
        row=await collection(self.env,'reference_library').find_one({'_id':key})
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
        from .mongo_pool import collection
        col=collection(self.env,'reference_library')
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
        from .mongo_pool import collection
        from pymongo.errors import DuplicateKeyError
        col=collection(self.env,'reference_library')
        old=await col.find_one({'_id':'head'})
        if old and old['value']['release']==head['release']:return
        try:
            result=await col.replace_one({'_id':'head','value.release':expected},{'_id':'head','value':head},upsert=expected is None)
        except DuplicateKeyError:raise ValueError('共享资料版本已改变，未覆盖')
        if not (result.modified_count or result.upserted_id):raise ValueError('共享资料版本冲突，未覆盖')


class ReferenceIndex:
    def __init__(self,pack):
        self.docs={d['id']:d for d in pack['documents'] if d.get('status','active')=='active'}
        self.rows=[];self.postings=defaultdict(list);self.lengths=[]
        for d in self.docs.values():
            # Recurring page footers are still preserved in docs/pages for the
            # original viewer. Exclude them only from retrieval, so a copyright
            # footer does not inherit a preceding definition heading as evidence.
            def footer_key(line):
                return re.sub(r'\d+','#',re.sub(r'\s+','',line))
            footer_counts=Counter()
            for page in d['pages']:
                lines=[line for line in page['text'].splitlines() if line.strip()]
                footer_counts.update({footer_key(line) for line in lines[-2:] if len(line.strip())>=8})
            repeated={line for line,count in footer_counts.items() if count>=max(3,math.ceil(len(d['pages'])*.25))}
            for page in d['pages']:
                contents_page=len(re.findall(r'(?:\.{4,}|…{2,})\s*\d+',page['text']))>=3
                lines=page['text'].splitlines();tail=[i for i,line in enumerate(lines) if line.strip()][-2:]
                text='\n'.join(line for i,line in enumerate(lines) if i not in tail or footer_key(line) not in repeated)
                for ch in chunk_text(text,d['title']):
                    if not ch['text'].strip():continue
                    i=len(self.rows);row=dict(doc_id=d['id'],title=d['title'],section=ch['section'],text=ch['text'],page=page['page'],hash=ch['hash'],chunk_id=d['id']+':'+str(i))
                    row['is_contents']=contents_page
                    heading=ch['section'] if ch['section']!=d['title'] else ''
                    row['_heading_terms']=sorted(terms(heading))
                    self.rows.append(row);tf=terms(body_text(row));self.lengths.append(sum(tf.values()))
                    for term,freq in tf.items():self.postings[term].append((i,freq))
        self.avg=sum(self.lengths)/max(1,len(self.rows)) or 1

    def search(self,query,limit=4):
        return self.search_with_diagnostics(query,limit)['sources']

    def page_context(self,row):
        """Actual same-page prefix for checking issuer/period, never for recall.

        Derived at output time from retained original pages, so existing snapshots
        need no migration and chunk hashes/lexical evidence stay unchanged.
        """
        if row.get('is_contents'):return ''
        pages=self.docs.get(row['doc_id'],{}).get('pages',[])
        page=next((p for p in pages if p.get('page')==row['page']),None)
        if not page:return ''
        text=page.get('text','')
        if not isinstance(text,str) or len(re.findall(r'(?:\.{4,}|…{2,})\s*\d+',text))>=3:return ''
        return text.lstrip()[:600]

    def search_with_diagnostics(self,query,limit=4):
        started=time.perf_counter();plan=plan_query(query);wanted=plan['terms']
        scores=Counter();covered=defaultdict(set);total=len(self.rows)
        limit=max(1,min(int(limit),20))
        for t in sorted(wanted):
            found=self.postings.get(t,[]);idf=math.log(1+(total-len(found)+.5)/(len(found)+.5))
            for i,tf in found:
                scores[i]+=idf*tf*2.2/(tf+1.2*(.25+.75*self.lengths[i]/self.avg))*(1.8 if t in plan['anchors'] else 1)
                covered[i].add(t)
        ranked=[]
        for i,score in sorted(scores.items(),key=lambda item:(-item[1],item[0]))[:max(200,limit*30)]:
            row=self.rows[i];evidence=evidence_match(plan,body_text(row),token_set=covered[i])
            if not evidence['accepted']:continue
            if row.get('is_contents') and not re.search(r'目录|目次|table of contents|哪一章|哪一页',query,re.I):continue
            heading_terms=set(row.get('_heading_terms',[]))
            # A section about A's functions is not evidence about B's functions
            # merely because B occurs in a subordinate bullet of that section.
            if 'concept_function' in wanted and 'concept_function' in heading_terms:
                topic=wanted-{'concept_function'}
                if topic and not topic&heading_terms:continue
            if len(re.findall(r'(?:\.{4,}|…{2,})\s*\d+',row['text']))>=3:score*=.18
            if plan['definition']:
                if len(re.findall(r'\d',row['text']))/max(1,len(row['text']))>.12:score*=.3
                if re.search(r'什么是|本质上|核心思想|是指|定义|指的是|是一种|称为|refers to',row['text'],re.I):score*=1.8
            phrase=normalize(plan['focus']).replace(' ','')
            if 3<=len(phrase)<=30 and phrase in normalize(body_text(row)).replace(' ',''):score*=1.35
            heading_coverage=len(wanted&heading_terms)/max(1,len(wanted))
            if heading_coverage>=(.45 if plan.get('comparison') else .7):score*=3 if plan.get('comparison') else 1.8
            score*=1+.2*evidence['coverage']
            ranked.append((score,i,evidence))
        seen=Counter();hashes=set();out=[]
        for score,i,evidence in sorted(ranked,key=lambda item:(-item[0],item[1])):
            r=self.rows[i]
            if seen[r['doc_id']]>=2 or r['hash'] in hashes:continue
            seen[r['doc_id']]+=1;hashes.add(r['hash'])
            context=self.page_context(r)
            out.append({k:v for k,v in r.items() if not k.startswith('_')}|{'score':round(score,4),'retrieval_routes':['bm25']+(['alias'] if plan['matched_aliases'] else []),
                          'query_focus':plan['focus'],'query_aliases':plan['matched_aliases'],
                          'evidence_match':evidence,'page_context':context,
                          'page_context_hash':digest(context) if context else None,
                          'page_context_scope':'same_page_prefix_not_retrieval_evidence'})
            if len(out)>=limit:break
        return {'sources':out,'diagnostics':{
            'status':'matched' if out else ('empty_index' if not self.rows else 'no_match'),
            'indexed_documents':len(self.docs),'indexed_chunks':len(self.rows),
            'query_focus':plan['focus'],'matched_aliases':plan['matched_aliases'],
            'candidates':len(scores),'hits':len(out),'mode':'page_bm25_alias_body_gate',
            'retrieval_ms':round((time.perf_counter()-started)*1000,3),
            'scope':'检索相关性与正文覆盖；不是模型准确率或事实验证'}}

    def serialize(self,release,*,max_compressed=MAX_INDEX):
        if type(max_compressed) is not int or not 1<=max_compressed<=MAX_SHARED_INDEX:
            raise ValueError('无效索引容量限制')
        value={'schema':INDEX_SCHEMA,'release':release,'docs':list(self.docs.values()),
               'rows':self.rows,'postings':dict(self.postings),'lengths':self.lengths}
        raw=json.dumps(value,ensure_ascii=False,separators=(',',':')).encode()
        if len(raw)>MAX_INDEX_TEXT:raise ValueError('检索索引超过预计算容量')
        compressed=gzip.compress(raw,compresslevel=3,mtime=0)
        if len(compressed)>max_compressed:raise ValueError('压缩检索索引超过存储容量')
        return compressed

    @classmethod
    def deserialize(cls,data,release,*,max_compressed=MAX_INDEX):
        if type(max_compressed) is not int or not 1<=max_compressed<=MAX_SHARED_INDEX:
            raise ValueError('无效索引容量限制')
        if not isinstance(data,bytes) or len(data)>max_compressed:raise ValueError('无效预计算索引')
        decoder=zlib.decompressobj(16+zlib.MAX_WBITS);raw=decoder.decompress(data,MAX_INDEX_TEXT+1)
        if len(raw)>MAX_INDEX_TEXT or decoder.unconsumed_tail or not decoder.eof or decoder.unused_data:
            raise ValueError('预计算索引解压校验失败')
        value=json.loads(raw)
        if not isinstance(value,dict) or value.get('schema')!=INDEX_SCHEMA or value.get('release')!=release:raise ValueError('预计算索引版本不匹配')
        docs=value.get('docs');rows=value.get('rows');postings=value.get('postings');lengths=value.get('lengths')
        if not isinstance(docs,list) or not isinstance(rows,list) or not isinstance(postings,dict) or not isinstance(lengths,list):
            raise ValueError('预计算索引结构无效')
        if len(docs)>500 or len(rows)>120000 or len(rows)!=len(lengths):raise ValueError('预计算索引大小无效')
        if any(not isinstance(d,dict) or not isinstance(d.get('id'),str) for d in docs):raise ValueError('预计算资料无效')
        docmap={d['id']:d for d in docs};count=len(rows)
        if len(docmap)!=len(docs):raise ValueError('预计算资料重复')
        for row,length in zip(rows,lengths):
            if not isinstance(row,dict) or row.get('doc_id') not in docmap or not isinstance(row.get('text'),str) or digest(row['text'])!=row.get('hash') or type(length) is not int or length<0:
                raise ValueError('预计算正文校验失败')
        for term,hits in postings.items():
            if not isinstance(term,str) or not isinstance(hits,list):raise ValueError('预计算倒排结构无效')
            if any(not isinstance(hit,list) or len(hit)!=2 or type(hit[0]) is not int or not 0<=hit[0]<count or type(hit[1]) is not int or hit[1]<1 for hit in hits):
                raise ValueError('预计算倒排范围无效')
        instance=cls.__new__(cls);instance.docs=docmap;instance.rows=rows
        instance.postings=postings;instance.lengths=lengths
        instance.avg=sum(lengths)/max(1,count) or 1
        return instance


_cache={};_cache_lock=threading.Lock()
def index_for(release,data):
    with _cache_lock:
        if release not in _cache:
            pack,_,_=unpack(data);idx=ReferenceIndex(pack);_cache.clear();_cache[release]=idx
        return _cache[release]


async def read_index_snapshot(ref,key,record,release):
    """Read old single-record snapshots or an atomically published manifest."""
    if isinstance(record,bytes):
        if len(record)>MAX_INDEX:raise ValueError('单记录索引超过容量')
        return record,dict(index_mode='persisted_index',index_bytes=len(record),index_parts=1)
    if (not isinstance(record,dict) or record.get('kind')!='index_parts'
            or record.get('schema')!=INDEX_SCHEMA or record.get('release')!=release):
        raise ValueError('索引分片清单无效')
    size=record.get('bytes');part_size=record.get('part_size');parts=record.get('parts');checksum=record.get('sha256')
    if (type(size) is not int or not 1<=size<=MAX_SHARED_INDEX
            or type(part_size) is not int or not 1<=part_size<=INDEX_PART_SIZE
            or not isinstance(parts,list) or not 1<=len(parts)<=math.ceil(MAX_SHARED_INDEX/INDEX_PART_SIZE)
            or len(parts)!=math.ceil(size/part_size)
            or not isinstance(checksum,str) or not re.fullmatch(r'[a-f0-9]{64}',checksum)):
        raise ValueError('索引分片总量无效')
    for n,part in enumerate(parts):
        if (not isinstance(part,dict) or type(part.get('bytes')) is not int
                or part['bytes']!=min(part_size,size-n*part_size)
                or not isinstance(part.get('sha256'),str) or not re.fullmatch(r'[a-f0-9]{64}',part['sha256'])):
            raise ValueError('索引分片描述无效')
    gate=asyncio.Semaphore(4)
    async def read_part(n,part):
        async with gate:
            data=await ref.get(f'{key}:part:{checksum}:{n}')
        if not isinstance(data,bytes) or len(data)!=part['bytes'] or hashlib.sha256(data).hexdigest()!=part['sha256']:
            raise ValueError('索引分片缺失或校验失败')
        return data
    chunks=await asyncio.gather(*(read_part(n,part) for n,part in enumerate(parts)))
    def assemble():
        data=b''.join(chunks)
        if len(data)!=size or hashlib.sha256(data).hexdigest()!=checksum:raise ValueError('索引整体校验失败')
        return data
    payload=await asyncio.to_thread(assemble)
    return payload,dict(index_mode='persisted_index_parts',index_bytes=size,index_parts=len(parts))


async def write_index_snapshot(ref,key,payload,release):
    if not isinstance(payload,bytes) or not 1<=len(payload)<=MAX_SHARED_INDEX:raise ValueError('索引总量超过容量')
    if len(payload)<=MAX_INDEX:
        await ref.put(key,payload)
        return dict(index_bytes=len(payload),index_parts=1)
    checksum=hashlib.sha256(payload).hexdigest()
    parts=[dict(bytes=len(payload[n:n+INDEX_PART_SIZE]),sha256=hashlib.sha256(payload[n:n+INDEX_PART_SIZE]).hexdigest())
           for n in range(0,len(payload),INDEX_PART_SIZE)]
    gate=asyncio.Semaphore(4)
    async def save_part(n):
        async with gate:
            await ref.put(f'{key}:part:{checksum}:{n}',payload[n*INDEX_PART_SIZE:(n+1)*INDEX_PART_SIZE])
    await asyncio.gather(*(save_part(n) for n in range(len(parts))))
    # Only this final atomic replacement publishes the complete derived index.
    # A crash leaves unreferenced parts, never a new source head or partial index.
    await ref.put(key,dict(kind='index_parts',schema=INDEX_SCHEMA,release=release,
                          bytes=len(payload),sha256=checksum,part_size=INDEX_PART_SIZE,parts=parts))
    return dict(index_bytes=len(payload),index_parts=len(parts))


async def loaded(ref,head,diagnostics=None):
    # Never acquire the long-running index build lock on the event loop.
    started=time.perf_counter();details=diagnostics if diagnostics is not None else {}
    existing=_cache.get(head['release'])
    if existing:
        details.update(getattr(existing,'_snapshot_details',{}))
        details.update(index_mode='memory_cache',index_load_ms=round((time.perf_counter()-started)*1000,3))
        return existing
    key='index:'+INDEX_SCHEMA+':'+head['release']
    persisted=await ref.get(key)
    if persisted is not None:
        try:
            payload,snapshot=await read_index_snapshot(ref,key,persisted,head['release'])
            idx=await asyncio.to_thread(ReferenceIndex.deserialize,payload,head['release'],max_compressed=MAX_SHARED_INDEX)
            idx._snapshot_details={k:v for k,v in snapshot.items() if k!='index_mode'}
            with _cache_lock:_cache.clear();_cache[head['release']]=idx
            details.update(snapshot,index_load_ms=round((time.perf_counter()-started)*1000,3))
            return idx
        except (ValueError,TypeError,KeyError,zlib.error):
            details['index_recovery']='rebuild_invalid_index'
    data=await ref.get('archive:'+head['release'])
    if not data or hashlib.sha256(data).hexdigest()!=head['release']:raise StoreUnavailable('共享资料正文校验失败，未引用')
    idx=await asyncio.to_thread(index_for,head['release'],data)
    details['index_mode']='rebuilt_from_archive'
    if ref.env.get('JINSHU_STORE_READ_ONLY')=='1':
        details['index_persistence']='skipped_readonly'
    else:
        try:
            payload=await asyncio.to_thread(idx.serialize,head['release'],max_compressed=MAX_SHARED_INDEX)
            snapshot=await write_index_snapshot(ref,key,payload,head['release'])
            idx._snapshot_details=snapshot
            details.update(snapshot,index_persistence='saved')
        except Exception:
            # Derived-index persistence must not change the immutable reference
            # archive or make an otherwise valid query fail. Failure is visible.
            details['index_persistence']='unavailable_memory_only'
    details['index_load_ms']=round((time.perf_counter()-started)*1000,3)
    return idx


def records(head):
    return [d|dict(status='active_reference',version=head['release'],origin='shared_reference',
                  department='shared',author=head['author'],reviewer=None,
                  review_note='用户授权恢复的学习参考，不代表机构制度审核',
                  published_at=head['published_at'],embedding='page_bm25',chunks=[],chunk_count=None)
            for d in head['catalog']]


async def search(store,query,who,limit=4):
    result=await search_with_diagnostics(store,query,who,limit)
    return result['sources'],result['mode']


async def search_with_diagnostics(store,query,who,limit=4):
    started=time.perf_counter()
    if not who:return {'sources':[],'mode':'login_required','diagnostics':{'status':'login_required','hits':0,'total_ms':0}}
    ref=ReferenceStore(store);head=await ref.get('head')
    if not head:return {'sources':[],'mode':'not_imported','diagnostics':{'status':'not_imported','hits':0,'total_ms':round((time.perf_counter()-started)*1000,3)}}
    load_details={};idx=await loaded(ref,head,load_details)
    result=await asyncio.to_thread(idx.search_with_diagnostics,query,limit)
    sources=[r|dict(version=head['release'],origin='shared_reference',department='shared',
                    authority='用户授权恢复的学习参考；非现行机构制度',external_allowed=True) for r in result['sources']]
    diagnostics=result['diagnostics']|load_details|{'total_ms':round((time.perf_counter()-started)*1000,3)}
    return {'sources':sources,'mode':'shared_reference_page_bm25_alias','diagnostics':diagnostics}


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
        result=await search_with_diagnostics(store,q,actor,6)
        return result|{'model_called':False}

    @app.get('/api/library/reference/{did}/page/{page}')
    async def page(did:str,page:int,request:Request,c=Depends(authorize)):
        await who(request);head=await ref.get('head')
        if not head:raise HTTPException(404,'未找到资料')
        idx=await loaded(ref,head);doc=idx.docs.get(did)
        row=next((p for p in doc['pages'] if p['page']==page),None) if doc else None
        if not row:raise HTTPException(404,'未找到原文页码')
        return {'id':did,'title':doc['title'],'version':head['release'],'pages':[p['page'] for p in doc['pages']],**row}
