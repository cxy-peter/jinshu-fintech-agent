/** V6 evidence contract. Lexical answers are quoted source assembly, not LLM inference. */
import {answerQuestion as baseAnswer,route as baseRoute,rewrite,norm} from './core.mjs';
export const VERSION='7.0.0';
export function normalizeQuery(q){
 const additions=[];
 if(/三大报表|资产[、，和\s]*负债[、，和\s]*权益/.test(q))additions.push('三表 勾稽');
 if(/买不起|购买能力|购买力下降|钱变多.*东西/.test(q))additions.push('货币幻觉 通货膨胀 购买力');
 if(/风险.{0,8}(卖给|转给|转移|消灭)|卖给.{0,10}风险/.test(q))additions.push('金融市场 风险转移');
 return q+(additions.length?' '+additions.join(' '):'');
}
export function route(q,index,lastFlow=null){
 const expanded=normalizeQuery(q),r=baseRoute(expanded,index,lastFlow);
 if(/(基金|基金经理)/.test(q)&&/(亏损|保本|承担|风险|专业管理)/.test(q)&&!/(FOF|fof|研报|基金池|配置|组合)/.test(q))return{...r,flow:'finance_learning',reason:'基金基本概念与风险承担：查学习资料，不作为组合研究任务',mode:'rules_and_lexical'};
 if(/三表|三大报表/.test(q)&&/周报/.test(q))return {...r,flow:'statements',flows:['statements','weekly_report'],reason:'拆分三表核对与周报质检两个资料子任务；分别保留依据',mode:'bounded_multi_workflow'};
 return {...r,normalized_query:expanded};
}
export function scopeCheck(q){
 if(/(明天|未来|下周).{0,18}(股票|基金|涨|跌|回报)|(?:股票|基金).{0,18}(一定涨|保证涨|准确预测)/.test(q))return '现有资料只能解释金融概念，不能确定未来价格或保证收益。';
 if(/(我的|本人|我个人|个人).{0,12}(账户|提现|余额)/.test(q)&&/(现在|实时|到账|已经|余额)/.test(q))return '知识库没有你的账户实时状态，当前未连接授权账户查询；不能确认到账或余额。';
 if(/(本公司|我们公司).{0,28}(尚未提供|没上传|真实利润|真实收入)|尚未提供.{0,30}财务/.test(q))return '当前未提供该公司的相应原始财务报表，不能据学习资料编造真实经营数字。';
 return null;
}
function bibliography(r){
 const own=r.id.startsWith('learn-');
 return {title:r.title,document_title:own?'金枢金融基础学习提要':r.title,source:r.source||'用户上传资料',
  source_kind:own?'project_learning_summary':r.synthetic?'synthetic_document':'uploaded_document',
  page:r.page??null,version:r.version??1,doc_id:r.doc_id,chunk_id:r.id,
  reference_url:r.reference_url||null,
  provenance_note:own?'以下逐字引用的是当前提要条目，不冒充黄达教材或115页笔记的逐字原文；原笔记需本人导入后查阅。':r.synthetic?'项目模拟材料，不是机构正式政策。':'以下为上传资料的提取原文，保留原措辞；不保证源文件观点正确或适用于当前。'};
}
function excerpt(content,query,maxChars=1800){
 if(content.length<=maxChars)return{quote:content,start:0,end:content.length};
 const terms=norm(query).match(/[\u3400-\u9fff]{2,8}|[a-z0-9]{2,}/g)||[];let bestAt=0,best=-1;
 for(let at=0;at<content.length;at+=220){const segment=norm(content.slice(at,at+maxChars));const s=terms.reduce((n,t)=>n+Number(segment.includes(t)),0);if(s>best){best=s;bestAt=at;}}
 return{quote:content.slice(bestAt,bestAt+maxChars),start:bestAt,end:Math.min(content.length,bestAt+maxChars)};
}
export function makeReferences(sources,index,query){
 const rows=new Map(index.rows.map(r=>[r.id,r]));const seen=new Set(),references=[];
 for(const hit of sources){for(const id of (hit.source_chunk_ids||[hit.id])){
  const r=rows.get(id);if(!r||r.status!=='active'||seen.has(id))continue;seen.add(id);
  const e=excerpt(r.content,query);references.push({...bibliography(r),...e,id:references.length+1,exact_quote:r.content.slice(e.start,e.end)===e.quote});
 }}
 return references;
}
export function verifyReferences(refs,index){const rows=new Map(index.rows.map(r=>[r.id,r]));return refs.length>0&&refs.every(r=>{const original=rows.get(r.chunk_id);return original?.status==='active'&&original.doc_id===r.doc_id&&original.content.slice(r.start,r.end)===r.quote;});}
export function answerQuestion(q,index,{flow=null,last='',topK=5,hints=[]}={}){
 const original=q,denied=scopeCheck(q),rw=rewrite(q,last),routing=route(rw.followup?last+' '+q:q,index);
 if(denied)return{query:q,flow:flow||routing.flow,route:routing,answer:denied,sources:[],references:[],mode:'no_evidence',verified:false,abstained:true,scope_reason:denied,stages:[{node:'Intent',status:'scope_not_supported',implementation:'capability_rule'}]};
 let flows=flow?[flow]:(routing.flows||[routing.flow]);flows=flows.filter(Boolean);
 const expanded=normalizeQuery(q);let a=baseAnswer(expanded,index,{flow:flows[0],last,topK,hints});
 if(flows.length>1){
  const per=flows.map(f=>baseAnswer(expanded,index,{flow:f,last,topK:Math.max(1,Math.floor(topK/flows.length)),hints}));
  const unique=new Map();per.forEach(x=>x.sources.forEach(s=>unique.set(s.id,s)));a.sources=[...unique.values()].slice(0,topK);
  a.subtasks=per.map(x=>({flow:x.flow,evidence_ids:x.sources.map(y=>y.id),status:x.sources.length?'completed':'no_evidence'}));
 }
 const refs=makeReferences(a.sources,index,original),verified=verifyReferences(refs,index);
 a={...a,query:original,flows,route:{...routing,flow:flows[0]},references:refs,verified,topK,version:VERSION,
  verification_scope:'引用逐字匹配、来源身份与活动状态检查；不是模型语义正确率或金融事实审定',
  answer:refs.length?'依据检索到的资料，相关原文如下（原文整理，未调用生成模型）：\n\n'+refs.map(r=>`【来源${r.id}】${r.document_title} — ${r.title}${r.page?'，第'+r.page+'页':''}，版本${r.version}\n原文摘录：\n${r.quote}\n出处：${r.source}\n${r.provenance_note}`).join('\n\n'):a.answer};
 if(a.rewritten)a.rewritten.original=original;
 return a;
}
