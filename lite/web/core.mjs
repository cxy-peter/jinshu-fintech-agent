import {retrievalPlan} from './constraints.mjs';
/** Browser-first lexical retrieval. No embeddings or learned inference are simulated. */
export const FLOWS = {
 finance_learning:['金融基础学习','知识','货币 利率 汇率 商业银行 信用创造 支付中介 金融学 概念 区别 名词解释 通胀 债券 央行'],
 fund_research:['基金与FOF研究','知识','基金 fof etf 组合 配置 研报 基金经理'],
 wealth_benchmark:['理财产品对标','理财','对标 净值 回撤 比较产品 可比产品 排名'],
 issuance:['发行排期','发行','排期 募集 成立日 到期日 顺延'],
 weekly_report:['周报清洗与质检','发行','周报 缺数 千分位 前导零 重复行 清洗'],
 material_fill:['发行材料生成','发行','生成word 生成材料 材料填充 发行材料'],
 onboarding:['开户字段时点','风控','开户 kyc iban 入金前 时点 视频核验'],
 kep:['案件邮件核查','风控','kep 案件 邮件 参考号 核查 送达'],
 strategy:['特征策略预检','风控','特征 阈值 策略 计数 success 去重 t+1'],
 statements:['模拟三表核对','发行','三表 资产负债表 利润表 现金流量表 勾稽'],
 service:['客服与转人工','客服','客服 工单 转人工 提现 退款 faq']
};
export const ALIASES = {银行职能:'商业银行 信用中介 支付中介 信用创造 金融服务',银行怎么赚钱:'商业银行 资产业务 负债业务 中间业务',钱生钱:'信用创造 派生存款',银根:'货币供给 货币政策',物价上涨:'通货膨胀',钱不值钱:'通货膨胀 购买力',无风险:'风险',开户前:'开户 决策时点',节假日:'非工作日 顺延',分散投资:'投资组合 风险分散',支付和清算:'支付清算系统',市盈率:'资本化',rag:'检索增强生成',embedding:'向量 编码',分词:'词项 关键词 BM25'};
const STOP = new Set('的 了 吗 呢 和 与 是 在 有 我 你 它 这 那 一个 什么 怎么 如何 为什么 请 一下 帮我 介绍 解释 说说 可以 以及'.split(' '));
export function norm(s){return String(s??'').normalize('NFKC').toLowerCase().replace(/\s+/g,' ').trim()}
const segmenter=typeof Intl.Segmenter==='function'?new Intl.Segmenter('zh',{granularity:'word'}):null;
export function tokens(s){s=norm(s);const out=segmenter?[...segmenter.segment(s)].filter(x=>x.isWordLike).map(x=>x.segment):s.match(/[a-z0-9_.-]+|[\u3400-\u9fff]/g)||[];
 for(const run of s.match(/[\u3400-\u9fff]{2,}/g)||[])for(let i=0;i<run.length-1;i++)out.push(run.slice(i,i+2));
 return out.filter(t=>!STOP.has(t)&&t.trim());}
export function rewrite(q,last=''){
 const follow=/^(那|它|这个|然后|再|有什么|具体)[^。！？?]{0,18}[？?]?$/.test(q.trim());
 let text=follow&&last?last+'；追问：'+q:q;const terms=[];
 for(const [a,b] of Object.entries(ALIASES))if(norm(text).includes(a)){terms.push(b)}
 return {original:q,expanded:text+' '+terms.join(' '),followup:!!(follow&&last),aliases:terms};
}
/** Detect dot-leader contents pages without discarding them from full-document viewing. */
export function isContents(text){return (String(text).match(/(?:\.{4,}|…{2,})\s*\d+/g)||[]).length>=3;}
function queryPhrase(query){return norm(query).replace(/^(请)?(解释一下|解释|介绍一下|介绍|什么是)/,'').replace(/(是什么|有哪些|是什么含义|什么意思|怎么办|如何处理)[？?。]*$/,'').replace(/[？?。]/g,'').trim();}
function headingBonus(content,query){const q=queryPhrase(query);if(q.length<3)return 0;return String(content).split(/\n/).some(line=>{const n=norm(line).replace(/^[\d.、（）()一二三四五六七八九十#\s]+/,'');return n.length<=60&&n.includes(q)})?12:0;}
export class Index {
 constructor(rows){this.rows=rows;this.postings=new Map();this.lengths=[];let length=0;
 rows.forEach((r,i)=>{const ts=tokens(r.title+' '+r.content),f=new Map();ts.forEach(t=>f.set(t,(f.get(t)||0)+1));this.lengths[i]=ts.length;length+=ts.length;for(const[t,n]of f){if(!this.postings.has(t))this.postings.set(t,[]);this.postings.get(t).push([i,n]);}});this.avg=length/Math.max(rows.length,1)||1;}
 search(query,{flow=null,limit=5}={}){
 const ts=[...new Set(tokens(query))],scores=new Map(),N=this.rows.length;
 for(const t of ts){const hits=this.postings.get(t)||[],idf=Math.log(1+(N-hits.length+.5)/(hits.length+.5));for(const[i,tf]of hits){const r=this.rows[i];if(r.status!=='active'||flow&&(r.flow!==flow&&r.flow!=='all'))continue;const score=idf*tf*2.2/(tf+1.2*(.25+.75*this.lengths[i]/this.avg));scores.set(i,(scores.get(i)||0)+score);}}
 return [...scores].map(([i,s])=>{const r=this.rows[i];let bonus=0;for(const term of ts)if(term.length>1&&norm(r.title).includes(term))bonus+=1.5;const contents=r.is_contents??isContents(r.content);const penalty=contents&&!/目录|目次/.test(query)?.18:1;return {...r,is_contents:contents,score:(s+bonus+headingBonus(r.content,query))*penalty}}).sort((a,b)=>b.score-a.score).slice(0,limit);
 }
}
export function route(q,index,lastFlow=null){
 const z=norm(q),all=Object.entries(FLOWS).map(([id,v])=>{const hits=v[2].split(' ').filter(t=>z.includes(t));return{id,title:v[0],score:hits.reduce((s,t)=>s+(t.length>2?4:2),0),terms:hits}});
 if(/^(那|它|这个|然后|再说)/.test(z)&&lastFlow&&FLOWS[lastFlow])return{flow:lastFlow,mode:'context_rule',candidates:[],reason:'沿用上一轮已选择的工作流'};
 for(const r of all)if(r.id==='material_fill'&&r.terms.length)r.score+=10;
 const lexical=index.search(q,{limit:4});
 for(const hit of lexical){const r=all.find(x=>x.id===hit.flow);if(r)r.score+=Math.min(3,hit.score/12)}
 all.sort((a,b)=>b.score-a.score);
 const top=all[0];return{flow:top.score>=1?top.id:null,mode:'rules_and_lexical',reason:top.score>=1?'术语规则与资料词项匹配（非模型概率）':'未发现明确资料或任务，请补充问题或手选工作流',candidates:all.slice(0,3)};
}
export function chunksFromPages(pages,{id,title,flow='finance_learning',status='pending_review',source='上传资料',version=1}={}){
 const out=[];pages.forEach((p,pi)=>{const text=typeof p==='string'?p:p.text;const is_contents=isContents(text);let at=0;
 while(at<text.length){let end=Math.min(at+650,text.length);if(end<text.length){const cut=Math.max(text.lastIndexOf('。',end),text.lastIndexOf('\n',end));if(cut>at+220)end=cut+1;}const content=text.slice(at,end).trim();if(content)out.push({id:id+':'+out.length,doc_id:id,title,flow,status,source,page:typeof p==='string'?pi+1:(p.page||pi+1),version,content,is_contents,start:at,end});if(end===text.length)break;at=Math.max(end-60,at+1);}});return out;
}
/** Keep ranked IDs; identify neighboring source chunks separately. Not semantic chunking. */
export function readingEvidence(hits,index,flow){
 return hits.map(hit=>{
  if(hit.start===undefined||hit.is_contents)return hit;
  const siblings=index.rows.filter(r=>r.doc_id===hit.doc_id&&r.status==='active'&&(r.flow===flow||r.flow==='all'));
  const at=siblings.findIndex(r=>r.id===hit.id);const chosen=[hit];
  // At most one previous and two following chunks; never cross documents or more than one page.
  for(const offset of [-1,1,2]){const row=siblings[at+offset];if(row&&!isContents(row.content)&&!row.is_contents&&Math.abs((row.page??0)-(hit.page??0))<=1)chosen.push(row);}
  chosen.sort((a,b)=>(a.page??0)-(b.page??0)||(a.start??0)-(b.start??0));
  return {...hit,source_chunk_ids:chosen.map(r=>r.id),source_pages:[...new Set(chosen.map(r=>r.page))],content:chosen.map(r=>`【原文第${r.page??'未标'}页 · 片段${r.id}】\n${r.content}`).join('\n\n'),context_expansion:'adjacent_chunks_not_additional_ranked_hits'};
 });
}
export function answerQuestion(q,index,{flow=null,last='',topK=5,hints=[]}={}){
 const started=performance.now(),rw=rewrite(q,last);const routing=flow?{flow,mode:'manual',reason:'用户明确选择'}:route(rw.followup?last:q,index);flow=routing.flow;
 if(!flow)return{query:q,route:routing,answer:routing.reason,sources:[],verified:false,mode:'clarification',stages:[{node:'Intent',status:'needs_clarification',implementation:'rules'}]};
 const plan=retrievalPlan(q,hints);rw.retrieval_plan=plan;
 const hits=index.search(rw.expanded+' '+plan.accepted.join(' '),{flow,limit:topK});const sourceTerms=[...new Set(tokens(rw.followup?last+' '+q:q))].filter(t=>t.length>1&&!['什么','如何','怎么','为什么','金融','问题'].includes(t));
 const direct=hits.some(h=>sourceTerms.some(t=>norm(h.content+' '+h.title).includes(t)));
 const sources=direct?readingEvidence(hits,index,flow):[];
 let answer=sources.length?'依据当前资料，相关内容如下（检索整理，未调用生成模型）：\n\n'+sources.map((h,i)=>`【来源${i+1}】${h.title}${h.page?' · 第'+h.page+'页':''}\n${h.content}`).join('\n\n'):'当前资料中未找到足够的直接依据。请补充资料、改写问题或转人工；不编造规定和账户状态。';
 if(answer.length>12000)answer=answer.slice(0,12000)+'\n\n回答预览达到长度上限，请在来源面板展开完整文档。';
 return{query:q,rewritten:rw,route:routing,flow,sources,answer,mode:sources.length?'lexical_extractive':'no_evidence',verified:!!sources.length,verification_scope:'仅检查活动来源与原文引用，不是模型语义正确率',topK,elapsed_ms:Math.round((performance.now()-started)*100)/100,stages:['Intent','Rewrite','Retrieval','Answer','Verify'].map(node=>({node,status:node==='Verify'&&!sources.length?'no_evidence':'completed',implementation:node==='Answer'?'source_assembly':'local_rules'}))};
}
export function metrics(ids,gold,k=5){const relevant=new Set(gold),top=[...new Set(ids)].slice(0,k),h=top.filter(x=>relevant.has(x));if(!relevant.size)return{hit:null,recall:null,mrr:null};return{hit:Number(h.length>0),recall:h.length/relevant.size,mrr:top.some(x=>relevant.has(x))?1/(top.findIndex(x=>relevant.has(x))+1):0}}
export function bucket(id){let h=2166136261;for(const c of id)h=Math.imul(h^c.charCodeAt(0),16777619);return(h>>>0)/4294967296}
export function propose(feedback,baseTop=5){if(!feedback.length)throw Error('先对任务提交反馈');const f=feedback[feedback.length-1];return{id:'candidate-'+f.id,flow:f.flow,status:'pending',topK:Math.min(8,baseTop+3),terms:String(f.terms||'').slice(0,100),cause:f.category,source_trace:f.trace_id,mode:'rule_proposal',created_at:new Date().toISOString()}}
export function replayCandidate(candidate,traces,rows){const index=new Index(rows);const selected=traces.filter(t=>t.flow===candidate.flow).slice(-20),pairs=[];for(const t of selected){const before=index.search(t.query,{flow:t.flow,limit:5}),after=index.search(t.query+' '+candidate.terms,{flow:t.flow,limit:candidate.topK});pairs.push({trace_id:t.id,baseline:before.map(x=>x.id),candidate:after.map(x=>x.id),sources_retained:before.every(x=>after.some(y=>y.id===x.id))})}return{pairs,passed:pairs.length>0&&pairs.every(x=>x.sources_retained),scope:'历史来源保留检查，不是人工质量提升或统计A/B实验'}}
