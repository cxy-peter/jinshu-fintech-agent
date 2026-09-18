"""Local-only corpus preparation with explicit origin, date and authority.
Outputs content under private_corpus/ (gitignored). No OCR or remote calls.
Archive inputs are extracted as data, never executed.
"""
from __future__ import annotations
import argparse, collections, ctypes as C, hashlib, json, re
from pathlib import Path
from .document_service import NativePDFParser
from .ingestion import FinancialParser, TableAwareChunker
from app.pipeline.parser import ParsedDocument, Block
SUPPORTED={'.pdf','.docx','.md','.txt','.html'}

def unpack_rar(source:Path,target:Path):
    import ctypes.util
    name=ctypes.util.find_library('archive')
    if not name:raise RuntimeError('Install libarchive13, or extract RAR manually and pass a directory')
    lib=C.CDLL(name)
    lib.archive_read_new.restype=C.c_void_p
    for method in ['archive_read_support_filter_all','archive_read_support_format_all','archive_read_free']:
        getattr(lib,method).argtypes=[C.c_void_p]
    lib.archive_read_open_filename.argtypes=[C.c_void_p,C.c_char_p,C.c_size_t]
    lib.archive_read_next_header.argtypes=[C.c_void_p,C.POINTER(C.c_void_p)]
    lib.archive_entry_pathname.argtypes=[C.c_void_p];lib.archive_entry_pathname.restype=C.c_char_p
    lib.archive_entry_size.argtypes=[C.c_void_p];lib.archive_entry_size.restype=C.c_longlong
    lib.archive_read_data.argtypes=[C.c_void_p,C.c_void_p,C.c_size_t];lib.archive_read_data.restype=C.c_longlong
    a=lib.archive_read_new();lib.archive_read_support_filter_all(a);lib.archive_read_support_format_all(a)
    if lib.archive_read_open_filename(a,str(source).encode(),65536)<0:raise ValueError('Cannot open archive')
    count=0;total=0
    try:
        entry=C.c_void_p()
        while True:
            status=lib.archive_read_next_header(a,C.byref(entry))
            if status==1:break
            if status<0:raise ValueError('RAR parsing failed')
            relative=Path(lib.archive_entry_pathname(entry).decode('utf-8'))
            if relative.is_absolute() or '..' in relative.parts:raise ValueError('Unsafe archive path')
            if relative.suffix.lower() not in SUPPORTED:continue
            size=lib.archive_entry_size(entry)
            if size>100_000_000:raise ValueError('Document exceeds 100MB')
            total+=size;count+=1
            if total>1_000_000_000 or count>2000:raise ValueError('Archive exceeds corpus budget')
            dest=target/relative;dest.parent.mkdir(parents=True,exist_ok=True)
            with dest.open('wb') as output:
                buffer=C.create_string_buffer(65536)
                while True:
                    n=lib.archive_read_data(a,buffer,len(buffer))
                    if n==0:break
                    if n<0:raise ValueError('Archive data decoding failed')
                    output.write(buffer.raw[:n])
    finally:lib.archive_read_free(a)
    return count

class CorpusParser(FinancialParser):
    """Fast native text mode for bulk research PDFs; table layout not asserted."""
    def _parse_pdf(self,path):
        import fitz
        blocks=[];raw=[];blank=0
        with fitz.open(path) as doc:
            for page_number,page in enumerate(doc,1):
                text=page.get_text(sort=True);raw.append(text)
                if not text.strip():blank+=1
                for block in page.get_text('blocks',sort=True):
                    value=block[4].strip()
                    if value:blocks.append(Block('paragraph',0,value,page_number))
            total=len(doc)
        if not any(t.strip() for t in raw):raise ValueError('image_only_needs_manual_transcription')
        return ParsedDocument(path.stem,blocks,'\n'.join(raw),total,{'blank_text_pages':blank,'table_mode':'native_text_only_not_layout_verified'})

def bounded_chunks(parsed,max_chars=360,overlap=45):
    results=[];groups=[];buffer=[];page=None;indices=[]
    def flush():
        if buffer:groups.append(('\n'.join(buffer),page,list(indices)))
        buffer.clear();indices.clear()
    for index,block in enumerate(parsed.blocks):
        if not block.text.strip():continue
        if buffer and (block.page!=page or sum(map(len,buffer))+len(block.text)>max_chars):flush()
        page=block.page;buffer.append(block.text);indices.append(index)
        if sum(map(len,buffer))>=max_chars:flush()
    flush()
    for parent,(text,page,blocks) in enumerate(groups):
        for start in range(0,len(text),max_chars-overlap):
            piece=text[start:start+max_chars]
            if not piece.strip():continue
            results.append({'content':piece,'section_path':[parsed.title,f'物理页 {page}'],
                'metadata':{'page':page,'blocks':blocks,'char_start':start,'char_end':min(start+max_chars,len(text)),
                            'parent_id':f'p{page}-group{parent}','table_layout_verified':False}})
            if start+max_chars>=len(text):break
    return results

def prepare(inputs,out:Path):
    out.mkdir(parents=True,exist_ok=True);rawdir=out/'raw';rawdir.mkdir(exist_ok=True)
    files=[]
    for source in inputs:
        p=Path(source)
        if p.suffix.lower()=='.rar':
            folder=rawdir/p.stem;unpack_rar(p,folder);files.extend(sorted(folder.rglob('*.pdf')))
        elif p.is_dir():files.extend(sorted(x for x in p.rglob('*') if x.suffix.lower() in SUPPORTED))
        elif p.suffix.lower() in SUPPORTED:files.append(p)
    manifest=[];seen={};count=0
    with (out/'chunks.jsonl').open('w',encoding='utf-8') as chunks:
        for p in files:
            digest=hashlib.sha256(p.read_bytes()).hexdigest();did='source_'+digest[:24]
            if digest in seen:
                manifest.append({'file':p.name,'sha256':digest,'status':'duplicate','duplicate_of':seen[digest]});continue
            seen[digest]=p.name
            kind='learning_reference' if '背诵' in p.name or '笔记' in p.name else 'research_reference'
            dates=re.findall(r'(20\d{2})[-_]?(0[1-9]|1[0-2])[-_]?(0[1-9]|[12]\d|3[01])',p.name)
            source_date='-'.join(dates[0]) if dates else None
            entry={'id':did,'file':p.name,'sha256':digest,'source_kind':kind,'source_date':source_date,
                'date_basis':'filename_unverified' if dates else 'unknown','dept_id':'dept_wealth','sensitivity':'internal',
                'external_allowed':False,'review_status':'pending_review','publish_to_github':False}
            try:
                parsed=CorpusParser().parse(p);pieces=bounded_chunks(parsed)
                for i,piece in enumerate(pieces):
                    row=piece|{'_id':f'{did}:{i}','doc_id':did,'chunk_index':i,'dept_id':'dept_wealth',
                        'source_file':p.name,'source_sha256':digest,'source_kind':kind,'source_date':source_date,
                        'content_hash':hashlib.sha256(piece['content'].encode()).hexdigest()}
                    chunks.write(json.dumps(row,ensure_ascii=False)+'\n')
                entry.update(status='parsed',pages=parsed.page_count,chunks=len(pieces),parser='native_page_blocks',**parsed.meta);count+=len(pieces)
            except Exception as exc:entry.update(status='needs_review',error=str(exc))
            manifest.append(entry)
    summary={'input_documents':len(files),'unique_parsed':sum(r['status']=='parsed' for r in manifest),'duplicates':sum(r['status']=='duplicate' for r in manifest),
             'failed':sum(r['status']=='needs_review' for r in manifest),'pages':sum(r.get('pages',0) for r in manifest),'chunks':count,
             'vectors_built':False,'review_status':'pending_review','public_body_uploaded':False,'documents':manifest}
    (out/'manifest.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2))
    return summary

async def import_reviewed_pack(runtime,root:Path,review_file:Path):
    approvals=json.loads(review_file.read_text()); entries=json.loads((root/'manifest.json').read_text())['documents']
    byid={e['id']:e for e in entries if e.get('status')=='parsed'};grouped=collections.defaultdict(list)
    for line in (root/'chunks.jsonl').read_text().splitlines():
        row=json.loads(line);grouped[row['doc_id']].append(row)
    result=[]
    for a in approvals:
        if not a.get('approved'):continue
        if a.get('uploader')==a.get('reviewer') or not a.get('reviewer'):raise ValueError('独立审核人缺失')
        e=byid[a['id']];did=e['id']
        if await runtime.c.store.get_document(did):
            result.append({'id':did,'status':'already_imported'});continue
        doc={'_id':did,'dept_id':e['dept_id'],'topic_key':'dept_wealth:'+did,'version':'1','title':e['file'],
            'status':'pending_review','source':{'file_name':e['file'],'file_hash':e['sha256'],'uploaded_by':a['uploader']},
            'source_kind':e['source_kind'],'source_date':e['source_date'],'synthetic':False,'review_required':True,
            'manual_sensitivity':e['sensitivity'],'detection':{'suggested_level':e['sensitivity']},'sensitivity':e['sensitivity'],
            'external_allowed':False,'allowed_depts':[e['dept_id']],'chunk_count':len(grouped[did])}
        await runtime.c.store.insert_document(doc);await runtime.c.store.insert_chunks(grouped[did])
        published=await runtime.c.documents.review_and_publish(did,a['reviewer'],[e['dept_id']],
            a.get('final_sensitivity','internal'),external_allowed=bool(a.get('external_allowed',False)),reason=a.get('reason','本地资料审核'))
        result.append({'id':did,'status':published['status'],'vector_status':published['vector_status']})
    return result

def main():
    p=argparse.ArgumentParser();p.add_argument('inputs',nargs='+');p.add_argument('--out',type=Path,default=Path('private_corpus'))
    args=p.parse_args();report=prepare(args.inputs,args.out)
    print(json.dumps({k:v for k,v in report.items() if k!='documents'},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
