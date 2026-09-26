"""Bounded native parsing. Archives are read in memory, never extracted or executed."""
from __future__ import annotations
import csv,io,json,zipfile
from pathlib import PurePosixPath,Path
from jinshu.document_service import NativePDFParser
from app.pipeline.parser import ParsedDocument,Block
LIMIT=3_500_000
def check_container(raw,name):
 ext=Path(name).suffix.lower()
 if ext not in {'.txt','.md','.csv','.json','.docx','.pdf','.zip'}:raise ValueError('支持TXT/MD/CSV/分页JSON/DOCX/原生PDF/分页JSON ZIP')
 if len(raw)>LIMIT:raise ValueError('文件超过3.5MB')
 if ext=='.pdf':
  import fitz
  with fitz.open(stream=raw,filetype='pdf') as d:
   if d.is_encrypted or len(d)>500:raise ValueError('PDF需未加密且不超过500页')
 if ext in {'.docx','.zip'}:
  with zipfile.ZipFile(io.BytesIO(raw)) as z:
   infos=z.infolist()
   if len(infos)>500 or sum(i.file_size for i in infos)>15_000_000:raise ValueError('压缩包解压内容超限')
   for i in infos:
    p=PurePosixPath(i.filename)
    if p.is_absolute() or '..' in p.parts or '\\' in i.filename or i.flag_bits&1:raise ValueError('压缩包路径或加密方式不允许')
    if i.file_size>8_000_000 or i.file_size>max(1,i.compress_size)*200:raise ValueError('压缩包单项或压缩比超限')
    if (i.external_attr>>16)&0o170000==0o120000:raise ValueError('压缩包不接受符号链接')
   if ext=='.docx' and 'word/document.xml' not in z.namelist():raise ValueError('不是有效Word文件')
   if ext=='.zip' and any(not i.is_dir() and not i.filename.lower().endswith('.json') for i in infos):raise ValueError('ZIP仅接收分页JSON；其他文件请分别上传')
 return ext

def page_blocks(data):
 pages=data.get('pages') if isinstance(data,dict) else data
 if not isinstance(pages,list) or not pages or len(pages)>500:raise ValueError('JSON需要pages数组（1至500页）')
 out=[];seen=set();total=0
 for n,page in enumerate(pages,1):
  page={'page':n,'text':page} if isinstance(page,str) else page
  if not isinstance(page,dict):raise ValueError('分页条目需要text和page')
  text=page.get('text');number=page.get('page',n)
  if not isinstance(text,str) or isinstance(number,bool) or not isinstance(number,int) or number<1 or number in seen:raise ValueError('页码不唯一或文字无效')
  total+=len(text)
  if total>1_000_000:raise ValueError('提取文字超过100万字符')
  seen.add(number);out.append(Block('paragraph',0,text,number))
 return out

class UnifiedParser(NativePDFParser):
 def parse(self,path):
  path=Path(path);raw=path.read_bytes();ext=check_container(raw,path.name)
  if ext=='.json':blocks=page_blocks(json.loads(raw))
  elif ext=='.zip':
   blocks=[]
   with zipfile.ZipFile(io.BytesIO(raw)) as z:
    for i in z.infolist():
     if not i.is_dir():
      for b in page_blocks(json.loads(z.read(i))):b.extra['archive_member']=i.filename;blocks.append(b)
   if len(blocks)>500 or sum(len(b.text) for b in blocks)>1_000_000:raise ValueError('分页ZIP内容超限')
  elif ext=='.csv':
   records=list(csv.reader(io.StringIO(raw.decode('utf-8-sig')),strict=True))
   if not records or len(records)>5001 or not records[0] or len(set(records[0]))!=len(records[0]):raise ValueError('CSV表头或行数不合法')
   if any(len(row)!=len(records[0]) for row in records):raise ValueError('CSV列数不一致')
   clean=lambda x:x.replace('|','／').replace('\n',' ')
   md=['|'+'|'.join(map(clean,row))+'|' for row in records];md.insert(1,'|'+'|'.join('---' for _ in records[0])+'|');blocks=[Block('table',0,'\n'.join(md),1)]
  else:
   doc=super().parse(path)
   if len(doc.text)>1_000_000:raise ValueError('提取文字超过100万字符')
   return doc
  return ParsedDocument(path.stem,blocks,'\n'.join(b.text for b in blocks),len({b.page for b in blocks}))
