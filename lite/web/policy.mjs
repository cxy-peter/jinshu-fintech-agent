/** Local policy governance, not server authorization or a semantic-accuracy guarantee. */
import {Index} from './core.mjs';
import {answerQuestion, verifyReferences} from './assurance.mjs';
import {scoreCase} from './benchmarking.mjs';
import {evidencePreview} from './readability.mjs';
export function canonical(value) {
  if (Array.isArray(value)) return value.map(canonical);
  if (value && typeof value === 'object') return Object.fromEntries(Object.keys(value).sort().filter(k=>value[k]!==undefined).map(k=>[k,canonical(value[k])]));
  return value;
}
export async function digest(value) {
  const bytes=new TextEncoder().encode(JSON.stringify(canonical(value)));
  return [...new Uint8Array(await crypto.subtle.digest('SHA-256', bytes))].map(b=>b.toString(16).padStart(2,'0')).join('');
}
export function config(value={}) {
  const topK=value.topK??5, terms=value.terms??'';
  if (!Number.isInteger(topK)||topK<1||topK>8||typeof terms!=='string'||terms.length>100) throw Error('候选仅允许top-k 1–8及100字以内的检索词');
  if (Object.keys(value).some(k=>!['topK','terms'].includes(k))) throw Error('禁止新增工具、代码或未知策略字段');
  return {topK,terms:terms.trim()};
}
export function currentPolicy(state,flow) {
  const head=state.policyHeads?.[flow];
  return head?structuredClone(head):{version:'base-'+flow,config:{topK:5,terms:''}};
}
export function runQuestion(query,rows,{flow=null,last='',policy=null}={}) {
  return answerQuestion(query,new Index(rows),{flow,last,topK:policy?.topK??5,hints:policy?.terms?[policy.terms]:[]});
}
const sourceSet=rows=>[...rows].sort((a,b)=>a.id.localeCompare(b.id));
const snapshotCases=traces=>traces.slice(-20).map(t=>({id:t.id,query:t.query,flow:t.flow,last:t.previousQuestion||'',manual:!!t.manualFlow}));
async function fingerprints(candidate,state,rows,traces,gold,engineHash) {
  if (!/^[a-f0-9]{64}$/.test(engineHash||'')) throw Error('缺少构建评测器指纹，请使用构建后的版本');
  return {config:await digest(config(candidate.config)),corpus:await digest(sourceSet(rows)),cases:await digest({traces:snapshotCases(traces),gold}),engine:engineHash,baseline:await digest(currentPolicy(state,candidate.flow))};
}
export async function evaluateCandidate(candidate,state,rows,traces,gold,engineHash) {
  const cfg=config(candidate.config),base=currentPolicy(state,candidate.flow);
  const relevant=snapshotCases(traces).filter(t=>t.flow===candidate.flow);
  if (!relevant.length) throw Error('至少需要一条本工作流的实际历史问题');
  const pairs=[];let improved=0,regressed=0,hardFailures=0;
  const ix=new Index(rows);
  for (const c of gold) {
    const baseline=runQuestion(c.question,rows,{last:c.previous||'',policy:null});
    // Policies change retrieval only; no model/route/financial formula changes are allowed.
    const before=baseline.flow===candidate.flow?runQuestion(c.question,rows,{last:c.previous||'',policy:base.config}):baseline;
    const after=baseline.flow===candidate.flow?runQuestion(c.question,rows,{last:c.previous||'',policy:cfg}):baseline;
    const b=scoreCase(c,before,ix),a=scoreCase(c,after,ix);
    improved+=Number(!b.pass&&a.pass);regressed+=Number(b.pass&&!a.pass);
    if (after.references.length&&!verifyReferences(after.references,ix))hardFailures++;
    if(c.expect_abstain&&after.sources.length)hardFailures++;
    pairs.push({id:c.id,kind:'labeled_development',question:c.question,before:b.pass,after:a.pass,beforeIds:b.retrieved_ids,afterIds:a.retrieved_ids,missingKeys:a.missing_keys,beforePreview:evidencePreview(before).map(x=>x.display).join('\n\n')||before.answer,afterPreview:evidencePreview(after).map(x=>x.display).join('\n\n')||after.answer});
  }
  for (const t of relevant) {
    const opts={flow:t.manual?t.flow:null,last:t.last};
    const b=runQuestion(t.query,rows,{...opts,policy:base.config}),a=runQuestion(t.query,rows,{...opts,policy:cfg});
    const safe=(!a.references.length||verifyReferences(a.references,ix))&&a.flow===b.flow&&!(b.mode==='no_evidence'&&a.sources.length);
    hardFailures+=Number(!safe);
    pairs.push({id:t.id,kind:'unlabeled_requires_review',question:t.query,beforeAnswer:b.answer,afterAnswer:a.answer,beforePreview:evidencePreview(b).map(x=>x.display).join('\n\n')||b.answer,afterPreview:evidencePreview(a).map(x=>x.display).join('\n\n')||a.answer,beforeIds:b.sources.map(x=>x.id),afterIds:a.sources.map(x=>x.id),contractPassed:safe});
  }
  return {at:new Date().toISOString(),passed:gold.length>0&&regressed===0&&hardFailures===0,pairs,improved,regressed,hardFailures,labeled:gold.length,unlabeled:relevant.length,
    fingerprints:await fingerprints(candidate,state,rows,traces,gold,engineHash),scope:'同批开发题与历史任务的检索/引用合同；未标注历史问题须人工复核，不代表语义准确率或线上A/B。'};
}
export async function proposePolicy(state,flow,value,{rows,traces,gold,engineHash,origin='feedback'}={}) {
  const c={id:'policy-'+crypto.randomUUID(),flow,config:config(value),baseVersion:currentPolicy(state,flow).version,status:'pending',origin,history:[],at:new Date().toISOString()};
  c.evaluation=await evaluateCandidate(c,state,rows,traces,gold,engineHash);c.status=c.evaluation.passed?'ready_for_review':'failed';return c;
}
export async function revalidatePolicy(c,state,ctx) {
  if(['active','rolled_back','replaced'].includes(c.status))throw Error('已发布或已回滚候选不能改写');
  if(currentPolicy(state,c.flow).version!==c.baseVersion)throw Error('基线已变化，请提出新候选');
  const e=await evaluateCandidate(c,state,ctx.rows,ctx.traces,ctx.gold,ctx.engineHash);
  c.history=[...c.history,c.evaluation].slice(-5);c.evaluation=e;c.status=e.passed?'ready_for_review':'failed';return c;
}
export async function publishPolicy(c,state,ctx,confirmed=false) {
  if(!confirmed)throw Error('需先查看配对问答并明确确认发布');
  if(c.status!=='ready_for_review'||!c.evaluation?.passed)throw Error('候选未通过验收');
  if(currentPolicy(state,c.flow).version!==c.baseVersion)throw Error('基线已变化，请重新生成候选');
  const cfgHash=await digest(config(c.config));
  const expected=JSON.stringify(canonical(c.evaluation.fingerprints));
  const actual=await evaluateCandidate(c,state,ctx.rows,ctx.traces,ctx.gold,ctx.engineHash);
  if(!actual.passed||JSON.stringify(canonical(actual.fingerprints))!==expected)throw Error('资料、样本、配置或评测代码已变化：请先重验收');
  if(await digest(config(c.config))!==cfgHash||currentPolicy(state,c.flow).version!==c.baseVersion)throw Error('发布期间候选或基线变化，已停止');
  c.previous=currentPolicy(state,c.flow);state.policyHeads??={};
  for(const old of state.candidates||[])if(old.flow===c.flow&&old.status==='active')old.status='replaced';
  state.policyHeads[c.flow]={version:c.id,config:structuredClone(c.config)};c.status='active';c.publishedAt=new Date().toISOString();return c;
}
export function rollbackPolicy(c,state) {
  if(c.status!=='active'||currentPolicy(state,c.flow).version!==c.id)throw Error('只能回滚当前生效版本');
  state.policyHeads[c.flow]=structuredClone(c.previous);c.status='rolled_back';c.rolledBackAt=new Date().toISOString();
  const previous=state.candidates.find(x=>x.id===c.previous.version);if(previous)previous.status='active';return c;
}
