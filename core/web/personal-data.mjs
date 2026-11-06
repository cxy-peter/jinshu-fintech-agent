// Preserve V7 pack/page compatibility; retrieval now uses the same bounded
// aliases and body-evidence gate as the server reference library.
import {chunksFromPages,isContents} from './legacy/core.mjs';
import {retrievalTokens,queryPlan,evidenceMatch,normalize,resolveFollowup} from './retrieval-query.mjs';

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
  return new PersonalIndex(documents.filter(d=>d.status==='active'&&(!d.synthetic||includeExamples)).flatMap(d=>d.rows));
}

class PersonalIndex {
  constructor(rows) {
    this.rows=rows;this.postings=new Map();this.lengths=[];this.headings=[];
    rows.forEach((row,i)=>{
      const terms=retrievalTokens(row.content),tf=new Map();this.lengths.push(terms.length);
      const first=(row.content.split(/\n/).find(s=>s.trim())||'').trim();
      const heading=/^(?:#{1,6}\s|第[一二三四五六七八九十百0-9]+[章节]|\d+[.、]\s*[^\d\s]|[一二三四五六七八九十]+、)/.test(first);
      this.headings.push(new Set(retrievalTokens(heading&&first.length<=100?first:'')));
      terms.forEach(t=>tf.set(t,(tf.get(t)||0)+1));
      for(const [term,freq] of tf){if(!this.postings.has(term))this.postings.set(term,[]);this.postings.get(term).push([i,freq]);}
    });
    this.avg=this.lengths.reduce((a,b)=>a+b,0)/Math.max(1,rows.length)||1;
  }
  search(query,{limit=5}={}) {
    const plan=queryPlan(query),scores=new Map(),covered=new Map(),total=this.rows.length;
    for(const term of [...plan.terms].sort()) {
      const hits=this.postings.get(term)||[],idf=Math.log(1+(total-hits.length+.5)/(hits.length+.5));
      for(const [i,tf] of hits){scores.set(i,(scores.get(i)||0)+idf*tf*2.2/(tf+1.2*(.25+.75*this.lengths[i]/this.avg))*(plan.anchors.has(term)?1.8:1));if(!covered.has(i))covered.set(i,new Set());covered.get(i).add(term);}
    }
    const out=[];
    for(const [i,raw] of [...scores].sort((a,b)=>b[1]-a[1]||a[0]-b[0]).slice(0,Math.max(200,limit*30))) {
      const row=this.rows[i],evidence=evidenceMatch(plan,row.content,covered.get(i));if(!evidence.accepted)continue;
      if((row.is_contents??isContents(row.content))&&!/目录|目次|table of contents|哪一章|哪一页/i.test(query))continue;
      if(plan.terms.has('concept_function')&&this.headings[i].has('concept_function')) {
        const topic=[...plan.terms].filter(t=>t!=='concept_function');
        if(topic.length&&!topic.some(t=>this.headings[i].has(t)))continue;
      }
      let score=raw;
      if(isContents(row.content))score*=.18;
      if(plan.definition) {
        if((row.content.match(/\d/g)||[]).length/Math.max(1,row.content.length)>.12)score*=.3;
        if(/什么是|本质上|核心思想|是指|定义|指的是|是一种|称为|refers to/i.test(row.content))score*=1.8;
      }
      const phrase=normalize(plan.focus).replace(/ /g,'');
      if(phrase.length>=3&&phrase.length<=30&&normalize(row.content).replace(/ /g,'').includes(phrase))score*=1.35;
      const headingCoverage=[...plan.terms].filter(t=>this.headings[i].has(t)).length/Math.max(1,plan.terms.size);
      if(headingCoverage>=(plan.comparison ? .45 : .7))score*=plan.comparison ? 3 : 1.8;
      score*=1+.2*evidence.coverage;
      out.push({...row,score,query_focus:plan.focus,query_aliases:plan.matched_aliases,evidence_match:evidence});
    }
    return out.sort((a,b)=>b.score-a.score||a.id.localeCompare(b.id)).slice(0,limit);
  }
}

export function selectedPassages(index,query,history=[]) {
  // Each selected passage keeps its actual page. No heading/ordinal invented.
  const resolved=resolveFollowup(query,history),perDoc=new Map(),seen=new Set();
  return index.search(resolved.query,{limit:40}).filter(r=>{
    if(seen.has(r.content))return false;seen.add(r.content);
    const n=perDoc.get(r.doc_id)||0;perDoc.set(r.doc_id,n+1);return n<2;
  }).slice(0,6)
    .map(r=>({title:r.title,text:r.content.slice(0,1200),page:Number.isInteger(r.page)?r.page:null,
      chunk_id:r.id.slice(0,160),origin:'personal_local'}));
}
