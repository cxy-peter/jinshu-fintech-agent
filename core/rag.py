"""Material-first RAG. Restores V8 clause/table boundaries, active-head refill,
BM25 + semantic candidates, RRF and inspectable reranking without importing the
enterprise service graph at web startup. Hash vectors are never semantic evidence.
"""
from __future__ import annotations
import asyncio
import hashlib
import math
import os
import re
from collections import Counter
from datetime import date
from functools import lru_cache
from pathlib import Path
from .knowledge import terms

MODEL_DIR = Path(__file__).parent / 'models' / 'bge-small-zh'
MODEL_ID = 'Xenova/bge-small-zh-v1.5@75c43b069aac4d136ba6bc1122f995fedcfd2781'


def digest(value):
    return hashlib.sha256(value.encode('utf-8')).hexdigest()


def chunk_text(text, title=''):
    """Clause/heading boundaries and repeated table headers (V8's financial patch).
    One oversized row stays intact; offsets/hashes point back to original text.
    """
    chunks, section, buffer, table = [], title, [], []
    def emit(lines, is_table=False):
        body = '\n'.join(lines).strip()
        if body:
            chunks.append(dict(text=body, section=section, table=is_table,
                               hash=digest(body), index=len(chunks)))
    def flush_table():
        if table:
            header = table[:2] if len(table)>1 and re.fullmatch(r'[| :\-]+',table[1]) else table[:1]
            for i in range(len(header), len(table), 8):
                emit(header + table[i:i+8], True)
            if len(table)==len(header): emit(table, True)
            table.clear()
    def flush():
        if buffer: emit(buffer); buffer.clear()
    for line in text.splitlines():
        if line.strip().startswith('|'):
            flush(); table.append(line); continue
        flush_table()
        if re.match(r'^#{1,6}\s',line):
            flush(); section=line.lstrip('# ').strip(); continue
        if re.match(r'^(第[一二三四五六七八九十百0-9]+[章节条款]|\d+[.、])',line): flush()
        if sum(map(len,buffer))+len(line)>600: flush()
        # Long paragraphs split on punctuation, then bounded chunks, not mid-table.
        while len(line)>900:
            at=max(line.rfind('。',0,600),line.rfind('；',0,600),line.rfind('. ',0,600))
            at=at+1 if at>200 else 600
            emit([line[:at]]); line=line[at:]
        buffer.append(line)
    flush(); flush_table()
    return chunks


@lru_cache(maxsize=1)
def _encoder():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    options=ort.SessionOptions(); options.intra_op_num_threads=2; options.inter_op_num_threads=1
    session=ort.InferenceSession(str(MODEL_DIR/'model_quantized.onnx'), options, providers=['CPUExecutionProvider'])
    tokenizer=Tokenizer.from_file(str(MODEL_DIR/'tokenizer.json'))
    tokenizer.enable_truncation(max_length=512); tokenizer.enable_padding(length=None)
    return session,tokenizer


def embed(texts):
    import numpy as np
    session,tokenizer=_encoder()
    out=[]
    for start in range(0,len(texts),8):
        encoded=tokenizer.encode_batch(texts[start:start+8])
        arrays={'input_ids':np.array([x.ids for x in encoded],dtype=np.int64),
                'attention_mask':np.array([x.attention_mask for x in encoded],dtype=np.int64),
                'token_type_ids':np.array([x.type_ids for x in encoded],dtype=np.int64)}
        vectors=session.run(None,{x.name:arrays[x.name] for x in session.get_inputs()})[0][:,0,:]
        vectors=vectors/np.maximum(np.linalg.norm(vectors,axis=1,keepdims=True),1e-12)
        out.extend([[round(float(v),7) for v in row] for row in vectors])
    return out


def encoder_available():
    return (MODEL_DIR/'model_quantized.onnx').exists() and (MODEL_DIR/'tokenizer.json').exists()


async def index_chunks(chunks, enabled=True):
    if not enabled or not encoder_available():
        return chunks, 'bm25_only'
    try:
        vectors=await asyncio.wait_for(asyncio.to_thread(embed,[c['section']+'\n'+c['text'] for c in chunks]),30)
        return [c|{'vector':v,'embedding_model':MODEL_ID} for c,v in zip(chunks,vectors)], MODEL_ID
    except Exception:
        return chunks,'embedding_unavailable_bm25_only'


def active_documents(state, department='all'):
    now=date.today().isoformat()
    return [d for d in state['documents'].values() if d['status']=='active'
            and (department=='all' or d['department'] in ('shared',department))
            and (not d.get('expires') or d['expires']>=now)
            and (not d.get('effective') or d['effective']<=now)]


def candidates(documents):
    rows=[]
    for d in documents:
        for c in d['chunks']:
            if digest(c['text'])!=c['hash']: continue
            rows.append(c|{'chunk_id':d['id']+':'+str(c['index']), 'doc_id':d['id'],
                'title':d['title'], 'version':d['version'], 'origin':d.get('origin','reviewed_library'),
                'department':d['department'], 'source_url':d.get('source_url',''),
                'external_allowed':d.get('external_allowed',False)})
    return rows


def rank(query, rows, query_vector=None, top_k=4):
    if not rows: return []
    q=terms(query); docs=[terms(r['title']+' '+r['section']+' '+r['text']) for r in rows]
    avg=sum(sum(c.values()) for c in docs)/len(docs) or 1
    df=Counter(t for d in docs for t in d)
    bm=[]; dense=[]
    for i,(r,c) in enumerate(zip(rows,docs)):
        score=sum(math.log(1+(len(rows)-df[t]+.5)/(df[t]+.5))*c[t]*2.5/(c[t]+1.5*(.25+.75*sum(c.values())/avg)) for t in q if c[t])
        if score>0: bm.append((i,score))
        if query_vector is not None and r.get('embedding_model')==MODEL_ID and len(r.get('vector',[]))==len(query_vector):
            sim=sum(a*b for a,b in zip(query_vector,r['vector']))
            if sim>.35: dense.append((i,sim))
    fused={}; routes={}; raw={}
    for name,hits in [('bm25',bm),('semantic',dense)]:
        for pos,(i,score) in enumerate(sorted(hits,key=lambda x:-x[1])[:40]):
            fused[i]=fused.get(i,0)+1/(61+pos); routes.setdefault(i,[]).append(name); raw.setdefault(i,{})[name]=score
    # Deterministic reranker retained from V8: lexical coverage and clause match.
    # This score is not a model confidence or human correctness percentage.
    for i in fused:
        coverage=len(set(q)&set(docs[i]))/max(len(q),1)
        fused[i]+=.02*coverage
    selected=sorted(fused,key=lambda i:(-fused[i],rows[i]['chunk_id']))[:top_k]
    return [{k:v for k,v in rows[i].items() if k not in ('vector','embedding_model')}|
            {'source_id':f'S{j+1}', 'score':round(fused[i],6),'retrieval_routes':routes[i],
             'route_scores':raw[i], 'reranker':'clause_coverage_rules'} for j,i in enumerate(selected)]


async def search(query, documents, top_k=4, semantic=True, env=None):
    rows=candidates(documents); vector=None; mode='bm25'
    if semantic and encoder_available() and any(r.get('vector') for r in rows):
        try:
            vector=(await asyncio.wait_for(asyncio.to_thread(embed,['为这个句子生成表示以用于检索相关文章：'+query]),12))[0]
            mode='bm25+bge_semantic+rrf'
        except Exception: mode='embedding_failed_bm25'
    if vector is not None and env:
        from .optional_services import milvus_candidates
        hits,vector_mode=await milvus_candidates(env,vector,[r['chunk_id'] for r in rows])
        mode+=';'+vector_mode
        if hits is not None:
            # Candidate filter affects only the vector branch, not BM25.
            rows=[r if r['chunk_id'] in hits else {k:v for k,v in r.items() if k!='vector'} for r in rows]
    return rank(query,rows,vector,top_k),mode


def source_graph(documents, sources):
    """Provenance graph, not a fabricated Neo4j installation."""
    nodes=[];edges=[]
    for d in documents:
        nodes.append({'id':d['id'],'kind':'document','label':d['title'],'version':d['version']})
        if d.get('replaces'):
            edges.append({'from':d['id'],'to':d['replaces'],'kind':'supersedes'})
    for s in sources:
        if not any(n['id']==s['doc_id'] for n in nodes):
            nodes.append({'id':s['doc_id'],'kind':'document','label':s['title'],'version':s['version'],'origin':s.get('origin')})
        nodes.append({'id':s['chunk_id'],'kind':'chunk','label':s['section']})
        edges.append({'from':s['doc_id'],'to':s['chunk_id'],'kind':'contains'})
        edges.append({'from':'answer','to':s['chunk_id'],'kind':'retrieved'})
    return {'nodes':nodes,'edges':edges,'scope':'资料版本、条款与回答引用关系；不声称已部署 Neo4j'}
