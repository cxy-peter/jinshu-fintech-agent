"""Review-first native PDF ingestion, added without replacing the original Indexer.
Uploaded sensitivity and local hints remain separate from the reviewer's final decision.
"""
from __future__ import annotations
import os
import asyncio,hashlib,uuid,re
from datetime import datetime,timezone,date
from pathlib import Path
from app.pipeline.parser import Block,ParsedDocument
from .ingestion import FinancialParser,TableAwareChunker
from .context import access
LEVELS={'public':0,'internal':1,'restricted':2,'sensitive':3}

def detect_sensitivity(text):
    rules=[('internal',r'内部|不对外|内部流程'),('restricted',r'风控策略|阈值|账户个案|投诉处理'),
           ('sensitive',r'身份证|银行卡号|[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}|(?<!\d)1[3-9]\d{9}(?!\d)')]
    hits=[{'suggested_level':level,'reason':pattern} for level,pattern in rules if re.search(pattern,text)]
    return {'suggested_level':max((h['suggested_level'] for h in hits),key=LEVELS.get,default='public'),
            'signals':hits,'method':'local rules, advisory only; not a trained sensitivity classifier'}

def can_read(doc,who):
    if who is None:return True
    level=doc.get('sensitivity','internal')
    return LEVELS.get(level,3)<=LEVELS.get(who.get('clearance','internal'),1) and bool(set(doc.get('allowed_depts') or [doc['dept_id']])&set(who.get('departments',[])))

class NativePDFParser(FinancialParser):
    def _parse_pdf(self,path):
        import fitz
        blocks=[];texts=[]
        with fitz.open(path) as doc:
            if doc.is_encrypted:raise ValueError('PDF需先解密后上传')
            for page_no,page in enumerate(doc,1):
                text=page.get_text();texts.append(text)
                tables=list(page.find_tables().tables);boxes=[fitz.Rect(t.bbox) for t in tables]
                items=[]
                for table in tables:
                    rows=table.extract()
                    if not rows:continue
                    clean=lambda c:str(c or '').replace('\n',' ').replace('|','／')
                    md='|'+'|'.join(clean(c) for c in rows[0])+'|\n|'+'|'.join('---' for _ in rows[0])+'|\n'
                    md+='\n'.join('|'+'|'.join(clean(c) for c in row)+'|' for row in rows[1:])
                    items.append((table.bbox[1],Block('table',0,md,page_no)))
                for b in page.get_text('dict')['blocks']:
                    if 'lines' not in b:continue
                    r=fitz.Rect(b['bbox'])
                    if any((r&t).get_area()>r.get_area()*.4 for t in boxes):continue
                    spans=[s for line in b['lines'] for s in line['spans']]
                    content='\n'.join(''.join(s['text'] for s in line['spans']) for line in b['lines']).strip()
                    if not content or content.startswith('金枢模拟样例 /'):continue
                    size=max((s['size'] for s in spans),default=10)
                    kind='heading' if size>=13 else 'paragraph'
                    items.append((r.y0,Block(kind,1 if size>=17 else 2 if kind=='heading' else 0,content,page_no)))
                blocks.extend(b for _,b in sorted(items,key=lambda i:i[0]))
            count=len(doc)
        if not any(t.strip() for t in texts):raise ValueError('未取得原生文字；扫描件待人工处理，未自动执行OCR')
        title=next((b.text for b in blocks if b.type=='heading'),path.stem)
        return ParsedDocument(title,blocks,'\n'.join(texts),count)

class ReviewedDocumentService:
    def __init__(self,indexer):
        self.indexer=indexer;self.store=indexer.store;self.parser=NativePDFParser();self.lock=asyncio.Lock()
    async def stage_file(self,path,dept_id,actor,topic,version=1,manual_sensitivity='internal',effective_date=None):
        if manual_sensitivity not in LEVELS:raise ValueError('未知敏感级别')
        if effective_date:date.fromisoformat(effective_date)
        path=Path(path);raw=path.read_bytes();digest=hashlib.sha256(raw).hexdigest()
        parsed=self.parser.parse(path)
        hints=detect_sensitivity(parsed.text)
        clean=self.indexer.cleaner.clean(parsed);pieces=self.indexer.chunker.chunk(clean)
        if not pieces:raise ValueError('没有有效内容，请补充可读取的资料')
        key=dept_id+':'+topic
        for old in await self.store.list_documents(dept_id=dept_id):
            if old.get('topic_key')==key and old.get('version')==str(version):raise ValueError('该主题版本已存在')
        did='doc_'+uuid.uuid4().hex[:16]
        doc={'_id':did,'dept_id':dept_id,'topic_key':key,'title':clean.title,'version':str(version),
             'status':'pending_review','vector_status':'not_indexed','effective_date':effective_date,
             'source':{'file_name':path.name,'file_hash':digest,'uploaded_by':actor},
             'created_at':datetime.now(timezone.utc).isoformat(),'review_required':True,
             'manual_sensitivity':manual_sensitivity,'detection':hints,'sensitivity':manual_sensitivity,
             'allowed_depts':[dept_id],'external_allowed':False,'chunk_count':len(pieces),
             'parser':'native_pdf_table_aware' if path.suffix.lower()=='.pdf' else 'original_text_parser',
             'synthetic':'模拟' in clean.title,'page_count':parsed.page_count}
        await self.store.insert_document(doc)
        await self.store.insert_chunks([c|{'_id':f'{did}:{i}','doc_id':did,'dept_id':dept_id,'chunk_index':i,
             'embedding_id':f'{did}:{i}','document_version':str(version),'content_hash':hashlib.sha256(c['content'].encode()).hexdigest()}
             for i,c in enumerate(pieces)])
        return await self.store.get_document(did)
    async def review_and_publish(self,did,actor,departments,final_sensitivity,allowed_depts=None,external_allowed=False,reason=''):
        if final_sensitivity not in LEVELS:raise ValueError('未知敏感级别')
        async with self.lock:
            d=await self.store.get_document(did)
            if not d or d['dept_id'] not in departments:raise PermissionError('不属于审核部门')
            if d['source']['uploaded_by']==actor:raise PermissionError('请由另一位人员审核')
            if d['status'] not in {'pending_review','index_failed'}:raise ValueError('当前状态不允许审核发布')
            if not reason.strip():raise ValueError('请记录审核理由')
            requested=allowed_depts or [d['dept_id']]
            if not set(requested)<=set(departments):raise PermissionError('超出审核人的部门范围')
            if external_allowed and LEVELS[final_sensitivity]>=2:raise ValueError('受限和敏感材料不向外部模型发送')
            reviewed={'sensitivity':final_sensitivity,'allowed_depts':requested,'external_allowed':external_allowed,
                      'review_decision':{'actor':actor,'reason':reason,'manual':d['manual_sensitivity'],'suggested':d['detection']['suggested_level']}}
            await self.store.update_document(did,reviewed)
            pieces=await self.store.list_chunks_by_doc(did);warnings=[]
            vector_ok=False
            from .live import local_models
            if self.indexer.embeddings.provider=='hash' or local_models() or external_allowed:
                try:
                    vectors=await asyncio.wait_for(self.indexer.embeddings.embed([c['content'] for c in pieces]),timeout=float(os.getenv('INDEX_TIMEOUT','180')))
                    if len(vectors)!=len(pieces):raise ValueError('向量数量不符')
                    for c,v in zip(pieces,vectors):await self.indexer.vector_store.add(c['_id'],v,{'doc_id':did,'dept_id':d['dept_id'],'chunk_index':c['chunk_index']})
                    vector_ok=True
                except Exception:
                    warnings.append('向量化/向量写入失败，发布为BM25可用；保留向量重建状态。')
                    try:await self.indexer.vector_store.delete_by_doc(did)
                    except Exception:warnings.append('向量清理未确认；事实库有效状态仍是最终依据。')
            else:warnings.append('资料未允许外部向量化，仅建立本地关键词索引。')
            await self.store.update_document(did,{'status':'pending_review','vector_status':'ready' if vector_ok else 'bm25_only','index_warnings':warnings})
            result=await self.indexer.publish(did,actor,departments)
            return result
