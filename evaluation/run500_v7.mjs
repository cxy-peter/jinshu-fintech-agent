import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {Index,propose,replayCandidate,chunksFromPages,answerQuestion as baseAnswer,tokens,norm} from '../lite/web/core.mjs';
import {answerQuestion,makeReferences,verifyReferences} from '../lite/web/assurance.mjs';
import {scoreCase} from '../lite/web/benchmarking.mjs';
import {execute} from '../lite/web/tools.mjs';
const load=p=>JSON.parse(readFileSync(new URL(p,import.meta.url)));
const corpus=load('../lite/web/knowledge.json'),fixture=load('../lite/web/fixtures.json'),cases=load('questions300.json'),toolcases=load('tools100.json');
const ix=new Index(corpus),records=[];
const digest=p=>createHash('sha256').update(readFileSync(new URL(p,import.meta.url))).digest('hex');
const near=(a,b)=>typeof b==='number'?typeof a==='number'&&Math.abs(a-b)<=1e-9*(1+Math.abs(b)):a===b;
function subset(obj,target){return Object.entries(target).every(([k,v])=>near(obj?.[k],v))}
function record(id,category,passed,input,actual,expected,meta={}){records.push({id,category,passed,input,actual,expected,...meta});}
function groupScore(rows){return{n:rows.length,passed:rows.filter(x=>x.passed).length,pass_rate:rows.length?rows.filter(x=>x.passed).length/rows.length:null}}
for(const c of cases.rows){
 let a,score;try{a=answerQuestion(c.question,ix,{last:c.previous||''});score=scoreCase(c,a,ix);}
 catch(e){score={pass:false,error:e.message};a={answer:'',sources:[]}}
 record(c.id,'qa',score.pass,{question:c.question,previous:c.previous},score,{gold_ids:c.gold_ids,routes:c.expected_routes,keys:c.key_points,abstain:c.expect_abstain},{suite:c.suite,family:c.family,subtype:c.category});
}
for(const c of toolcases.rows){
 const data=structuredClone(fixture);if(c.fixture)Object.assign(data,c.fixture);
 let actual,error,ok=false;try{actual=execute(c.tool,c.params,data)}catch(e){error=e.message;}
 const e=c.expect;
 if(e.error)ok=!!error;
 else if(e.must_not_pass)ok=!!error||actual?.passed===false;
 else if(!error){ok=true;
  if(e.rows_subset)ok=actual.rows.length===e.rows_subset.length&&e.rows_subset.every((r,i)=>subset(actual.rows[i],r));
  if(e.row_count!==undefined)ok=ok&&actual.rows.length===e.row_count;
  if(e.title)ok=ok&&actual.material_preview.标题===e.title;
  if(e.stage!==undefined)ok=ok&&actual.decision_stage===e.stage&&actual.rows.every(x=>x.available_now===(Number(x.available_stage)<=e.stage));
  if(e.candidate_subset)ok=ok&&subset(actual.candidate,e.candidate_subset);
  if(e.passed!==undefined)ok=ok&&actual.passed===e.passed;
 }
 record(c.id,'tools',ok,{tool:c.tool,params:c.params,fixture_override:c.fixture},{result:actual,error},e,{subtype:c.tool,suite:c.case_type});
}
// 60 parameterized evidence/state checks: 6 corpora x 10 contracts. These are not 60 new user questions.
for(let f=0;f<6;f++){
 const id='ref-'+f,topic=['甲银行','乙机构','丙事业部','丁研究组','戊运营部','己财务部'][f],text=topic+'处理顺序为：核对资料、记录结果、人工复核。参考值REF'+f+'。';
 const rows=chunksFromPages([{page:24,text},{page:25,text:topic+'的补充说明：复核后保存记录，不能省略。'}],{id,title:topic+'操作规范',flow:'finance_learning',status:'active'});
 const index=new Index(rows),a=answerQuestion(topic+'处理顺序',index,{flow:'finance_learning',topK:1});
 const checks=[];
 checks.push(['引用逐字一致',()=>verifyReferences(a.references,index),true]);
 checks.push(['版本与文档身份保留',()=>a.references.every(x=>x.doc_id===id&&x.version===1),true]);
 checks.push(['跨页补全保留第25页',()=>a.references.some(x=>x.page===25),true]);
 checks.push(['篡改摘录被发现',()=>{const refs=structuredClone(a.references);refs[0].quote+='不存在的新增内容';return verifyReferences(refs,index)},false]);
 checks.push(['错误文档id被发现',()=>{const refs=structuredClone(a.references);refs[0].doc_id='other';return verifyReferences(refs,index)},false]);
 checks.push(['错位offset被发现',()=>{const refs=structuredClone(a.references);refs[0].start=1;return verifyReferences(refs,index)},false]);
 checks.push(['停用后新问题无引用',()=>{const archived=rows.map(x=>({...x,status:'archived'}));return answerQuestion(topic+'处理顺序',new Index(archived),{flow:'finance_learning'}).sources.length},0]);
 checks.push(['停用后旧引用校验失败',()=>verifyReferences(a.references,new Index(rows.map(x=>({...x,status:'archived'})))),false]);
 checks.push(['待审资料不进入检索',()=>new Index(rows.map(x=>({...x,status:'pending_review'}))).search(topic).length,0]);
 checks.push(['非本工作流资料不返回',()=>index.search(topic,{flow:'service'}).length,0]);
 checks.forEach(([name,fn,expected],j)=>{let actual,error;try{actual=fn()}catch(e){error=e.message}record(`E${String(f*10+j+1).padStart(3,'0')}`,'evidence_state',!error&&actual===expected,{topic,test:name},{value:actual,error},expected,{subtype:name,suite:'parameterized_contract',family:'evidence-fixture-'+f});});
}
// 40 actual function-level Loop checks: 8 workflows x 5 checks. UI approval/remote gray deployments not simulated as facts.
const flows=['wealth_benchmark','issuance','weekly_report','material_fill','onboarding','kep','strategy','statements'];
for(let f=0;f<flows.length;f++){
 const flow=flows[f],query='模拟业务处理',rs=Array.from({length:9},(_,i)=>({id:`${flow}-${i}`,doc_id:`${flow}-doc-${i}`,title:'模拟业务',content:`模拟业务处理需要保存第${i}项记录。`,flow,status:'active',source:'合成Loop回归材料',version:1}));
 const feedback={id:'f-'+f,flow,trace_id:'tr-'+f,terms:'记录',category:'retrieval'};
 const candidate=propose([feedback]),hist=[{id:feedback.trace_id,query,flow}],replay=replayCandidate(candidate,hist,rs),index=new Index(rs);
 const before=baseAnswer(query,index,{flow,topK:5});const after=baseAnswer(query+' '+candidate.terms,index,{flow,topK:candidate.topK});const reverted=baseAnswer(query,index,{flow,topK:5});
 const checks=[['候选待确认且参数有界',()=>candidate.status==='pending'&&candidate.topK===8,true],['Trace反馈与工作流绑定',()=>candidate.source_trace===feedback.trace_id&&candidate.flow===flow,true],['历史来源保留回放',()=>replay.passed&&replay.pairs.length===1,true],['应用候选改变检索输出上限',()=>before.sources.length===5&&after.sources.length===8,true],['恢复基线查询和参数得到原排序',()=>JSON.stringify(reverted.sources.map(x=>x.id))===JSON.stringify(before.sources.map(x=>x.id)),true]];
 checks.forEach(([name,fn,expected],j)=>{let actual,error;try{actual=fn()}catch(e){error=e.message}record(`L${String(f*5+j+1).padStart(3,'0')}`,'loop',!error&&actual===expected,{flow,test:name},{value:actual,error,candidate,before_ids:before.sources.map(x=>x.id),after_ids:after.sources.map(x=>x.id),reverted_ids:reverted.sources.map(x=>x.id)},expected,{suite:'parameterized_function_contract',subtype:name,family:flow});});
}
if(records.length!==500)throw Error('Wrong count '+records.length);
// Ranker ablation: same tokens, BM25 formula, candidate scope and rewrite; remove title/heading/TOC adjustments only.
class RawBM25 extends Index{search(q,{flow=null,limit=5}={}){const ts=[...new Set(tokens(q))],scores=new Map(),N=this.rows.length;for(const t of ts){const hits=this.postings.get(t)||[],idf=Math.log(1+(N-hits.length+.5)/(hits.length+.5));for(const[i,tf]of hits){const r=this.rows[i];if(r.status!=='active'||flow&&(r.flow!==flow&&r.flow!=='all'))continue;const s=idf*tf*2.2/(tf+1.2*(.25+.75*this.lengths[i]/this.avg));scores.set(i,(scores.get(i)||0)+s)}}return[...scores].map(([i,score])=>({...this.rows[i],score})).sort((a,b)=>b.score-a.score).slice(0,limit)}}
const ablations={};for(const[name,idx,k]of[['V7_current_topk5',ix,5],['no_rank_adjustments',new RawBM25(corpus),5],['topk8_only',ix,8]]){
 const scored=cases.rows.map(c=>scoreCase(c,answerQuestion(c.question,idx,{last:c.previous||'',topK:k}),idx));
 const positives=scored.filter(x=>x.hit!==null);ablations[name]={n:scored.length,passed:scored.filter(x=>x.pass).length,hit_rate:positives.reduce((s,x)=>s+x.hit,0)/positives.length,labeled_recall:positives.reduce((s,x)=>s+x.recall,0)/positives.length,mrr:positives.reduce((s,x)=>s+x.mrr,0)/positives.length,total_reference_chars:scored.reduce((s,x)=>s+(x.references||[]).reduce((t,r)=>t+r.quote.length,0),0),note:'Same 300 development/challenge cases; retrieval/quote engine only. topk8 metric is at 8, not Recall@5. No LLM inference.'};
}
const groups=Object.fromEntries(['qa','tools','evidence_state','loop'].map(k=>[k,groupScore(records.filter(x=>x.category===k))]));
const summary={suite:'Jinshu-V7-PE500-original-labels',executed_at_utc:new Date().toISOString(),runtime:'Node '+process.version,source:'V7 local run on unchanged PE500 labels; legacy 40 Loop function contracts retained, V7 governance tested separately; no paid model calls',counts:groups,qa_subsets:Object.fromEntries(['legacy_regression','new_capability'].map(k=>[k,groupScore(records.filter(x=>x.category==='qa'&&x.suite===k))])),question_sha256:digest('questions300.json'),toolcases_sha256:digest('tools100.json'),corpus_source_records:corpus.length,question_family_keys:new Set(cases.rows.map(c=>c.family)).size,family_note:'family keys include multi-source combinations and unanswerable labels; not independent semantic domains',distinct_questions:300,parameterized_cases:200,ablation:ablations,total:groupScore(records),human_graded_answers:0,live_model_calls:0,real_users:0,new_failures_retained:true};
mkdirSync(new URL('../evidence/v7/eval500/',import.meta.url),{recursive:true});writeFileSync(new URL('../evidence/v7/eval500/results500.json',import.meta.url),JSON.stringify({summary,rows:records},null,2));writeFileSync(new URL('../evidence/v7/eval500/summary.json',import.meta.url),JSON.stringify(summary,null,2));writeFileSync(new URL('../evidence/v7/eval500/failures.json',import.meta.url),JSON.stringify(records.filter(x=>!x.passed),null,2));console.log(JSON.stringify(summary,null,2));
