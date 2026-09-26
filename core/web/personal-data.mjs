// Reuse V7 Chinese BM25, heading boost and contents-page penalty unchanged.
import {Index, chunksFromPages, tokens} from './legacy/core.mjs';

export function normalizePack(value) {
  const input = value.documents || value.docs;
  if (!Array.isArray(input) || input.length > 1000) throw Error('资料包需含 documents/docs 数组，最多1000份。');
  const seen=new Set(), documents=[];let chars=0, count=0;
  for (const d of input) {
    if (!d || typeof d.title!=='string' || !d.title.trim()) throw Error('资料缺少标题。');
    const title=d.title.slice(0,120),id=String(d.id||d.sha256||title).slice(0,120);
    if(seen.has(id))continue;seen.add(id);
    const status=d.status==='active'?'active':'pending_review';
    let rows;
    if(Array.isArray(d.pages)&&d.pages.length) {
      if(d.pages.length>10000)throw Error('单份资料页数过多。');
      const pages=d.pages.map((p,i)=>({page:Number.isInteger(p?.page)&&p.page>0?p.page:i+1,text:typeof p==='string'?p:String(p?.text||'')}));
      chars+=pages.reduce((n,p)=>n+p.text.length,0);
      if(chars>40000000)throw Error('资料正文超过4000万字，请分批导入。');
      rows=chunksFromPages(pages,{id,title,flow:'all',status});
    } else if(Array.isArray(d.chunks)) {
      rows=d.chunks.map((c,i)=>({id:id+':'+i,doc_id:id,title,flow:'all',status,
        content:String(c.content||c.text||''),page:c.page||c.metadata?.page||null,
        start:c.start,end:c.end}));
      chars+=rows.reduce((n,r)=>n+r.content.length,0);
    } else throw Error('资料没有分页正文或切片。');
    if(chars>40000000||(count+=rows.length)>60000||rows.some(r=>r.content.length>12000))throw Error('资料包过大或切片过长。');
    documents.push({id,title,status,synthetic:!!d.synthetic,rows,sha256:String(d.sha256||'').slice(0,64)});
  }
  return documents;
}

export function makeIndex(documents, includeExamples=false) {
  return new Index(documents.filter(d=>d.status==='active'&&(!d.synthetic||includeExamples)).flatMap(d=>d.rows));
}

export function selectedPassages(index,query) {
  // Each selected passage keeps its actual page. No heading/ordinal invented.
  const focus=query.replace(/请问|请帮我|帮我|介绍一下|解释一下|是什么|有什么|有哪些|怎么|如何|为什么|什么|一下/g,' ');
  const wanted=[...new Set(tokens(focus))].filter(t=>t.length>1);
  if(!wanted.length)return [];
  const perDoc=new Map();
  return index.search(focus,{limit:40}).filter(r=>{
    const actual=new Set(tokens(r.content+' '+r.title));
    const coverage=wanted.filter(t=>actual.has(t)).length/wanted.length;
    // Sparse keyword overlap and broken formula glyphs are not useful evidence.
    return coverage>=0.45&&(r.content.match(/�/g)||[]).length/Math.max(r.content.length,1)<0.08;
  }).filter(r=>{const n=perDoc.get(r.doc_id)||0;perDoc.set(r.doc_id,n+1);return n<2;}).slice(0,6)
    .map(r=>({title:r.title,text:r.content.slice(0,1200),page:Number.isInteger(r.page)?r.page:null,
      chunk_id:r.id.slice(0,160),origin:'personal_local'}));
}
