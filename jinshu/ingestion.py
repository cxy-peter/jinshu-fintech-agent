"""Original Parser/Cleaner/Chunker retained; add explicit draft/second-review/version head."""
import asyncio,hashlib,uuid
from datetime import datetime,timezone,date
from pathlib import Path
from app.pipeline.indexer import Indexer
from app.pipeline.chunker import Chunker
from app.pipeline.parser import Block,DocumentParser

class FinancialParser(DocumentParser):
 def _parse_markdown(self,path):
  doc=super()._parse_markdown(path)
  import re
  for b in doc.blocks:
   lines=b.text.splitlines()
   if b.type=='paragraph' and len(lines)>=2 and lines[0].strip().startswith('|') and re.fullmatch(r'[| :\-]+',lines[1].strip()):b.type='table'
  headings=[b.text for b in doc.blocks if b.type=='heading' and b.level==1]
  if headings:doc.title=headings[0]
  return doc

class TableAwareChunker(Chunker):
 def _chunk_section(self,section):
  # Reuse original narrative splitting. Tables repeat header; never split a financial row.
  out=[];plain=[]
  def flush():
   if plain:out.extend(super(TableAwareChunker,self)._chunk_section(section|{'blocks':list(plain)}));plain.clear()
  for b in section['blocks']:
   if b.type!='table':plain.append(b);continue
   flush();lines=b.text.splitlines()
   header=lines[:2] if len(lines)>1 and set(lines[1].replace('|','').strip())<={'-',':',' '} else lines[:1]
   body=lines[len(header):]
   for start in range(0,len(body),8):
    text='\n'.join(header+body[start:start+8]);out.append({'section_path':section['path'],'section_title':section['title'],'content':text,'char_count':len(text),'metadata':{'page':b.page,'has_table':True,'source_row_start':start+len(header)+1}})
  flush();return out

class DraftIndexer(Indexer):
 def __init__(self,*a,**k):super().__init__(*a,**k);self.parser=FinancialParser();self.chunker=TableAwareChunker();self.publish_lock=asyncio.Lock()
 async def ingest(self,file_path,dept_id,uploaded_by='system',topic=None,version=1,effective_date=None,expiry_date=None):
  path=Path(file_path);body=path.read_bytes();digest=hashlib.sha256(body).hexdigest();parsed=self.parser.parse(path);clean=self.cleaner.clean(parsed);pieces=self.chunker.chunk(clean)
  if not pieces:raise ValueError('没有有效切片')
  topic=topic or clean.title;key=dept_id+':'+topic
  for old in await self.store.list_documents(dept_id=dept_id):
   if old.get('source',{}).get('file_hash')==digest:raise ValueError('同部门内容重复')
   if old.get('topic_key')==key and old.get('version')==str(version):raise ValueError('主题与版本重复')
  did='doc_'+uuid.uuid4().hex[:16]
  doc={'_id':did,'dept_id':dept_id,'topic_key':key,'title':clean.title,'version':str(version),'status':'indexing','vector_status':'pending','effective_date':effective_date,'expiry_date':expiry_date,'source':{'file_name':path.name,'file_hash':digest,'uploaded_by':uploaded_by},'created_at':datetime.now(timezone.utc).isoformat(),'synthetic':True}
  await self.store.insert_document(doc)
  try:
   vectors=await self.embeddings.embed([c['content'] for c in pieces]);stored=[]
   if len(vectors)!=len(pieces):raise ValueError('Embedding数量不匹配')
   for i,(c,v) in enumerate(zip(pieces,vectors)):
    cid=f'{did}:{i}';row=c|{'_id':cid,'doc_id':did,'dept_id':dept_id,'chunk_index':i,'embedding_id':cid,'document_version':str(version)}
    stored.append(row);await self.vector_store.add(cid,v,{'doc_id':did,'dept_id':dept_id,'chunk_index':i})
   await self.store.insert_chunks(stored)
   await self.store.update_document(did,{'status':'pending_review','vector_status':'ready','chunk_count':len(stored)})
  except Exception:
   await self.vector_store.delete_by_doc(did);await self.store.delete_chunks_by_doc(did);await self.store.update_document(did,{'status':'failed'});raise
  return await self.store.get_document(did)
 async def publish(self,did,actor,allowed_depts):
  async with self.publish_lock:
   d=await self.store.get_document(did)
   if not d or d['dept_id'] not in allowed_depts:raise PermissionError('文档不在授权部门')
   if d['source']['uploaded_by']==actor:raise PermissionError('不允许自审发布')
   if d['status']!='pending_review':raise ValueError('只发布已入库的待审核版本')
   now=date.today().isoformat()
   if d.get('effective_date') and d['effective_date']>now:raise ValueError('尚未生效')
   if d.get('expiry_date') and d['expiry_date']<now:raise ValueError('已失效')
   old=await self.store.get('document_heads',d['topic_key'])
   if old and float(old['version'])>=float(d['version']):raise ValueError('版本回退需显式审批，不自动覆盖')
   # Head is authoritative; Mongo replacement is one-document atomic. Cross-store cleanup can retry.
   await self.store.update_document(did,{'status':'active','reviewed_by':actor})
   await self.store.upsert('document_heads',{'_id':d['topic_key'],'doc_id':did,'version':d['version']})
   for c in await self.store.list_chunks_by_doc(did):self.bm25.remove(c['_id']);self.bm25.add(c)
   if old:
    await self.store.update_document(old['doc_id'],{'status':'archived','superseded_by':did})
    try:await self._remove_from_runtime_indexes(old['doc_id'])
    except Exception as exc:
     await self.store.upsert('index_cleanup_pending',{'_id':old['doc_id'],'status':'pending','error':type(exc).__name__})
     await self.store.update_document(did,{'cleanup_warning':'旧索引清理待重试；回填仍以document_heads及active状态为准'})
    if self.organization_memory:await self.organization_memory.invalidate_document(old['doc_id'],'document_superseded')
   await self.store.upsert('publish_audit',{'_id':uuid.uuid4().hex,'doc_id':did,'actor':actor,'previous':old,'created_at':datetime.now(timezone.utc).isoformat()})
  return await self.store.get_document(did)
