/** Evaluation reads labels; the answer engine never reads this module or benchmark labels. */
import {Index} from './core.mjs';
import {answerQuestion,verifyReferences} from './assurance.mjs';
export function scoreCase(c,a,index){
 const ids=a.sources.map(s=>s.id),hitIds=c.gold_ids.filter(id=>ids.includes(id)),quotes=(a.references||[]).map(r=>r.quote).join('\n');
 const keyHits=c.key_points.filter(k=>quotes.includes(k)),routeOK=!c.expected_routes.length?true:c.expected_routes.every(f=>(a.flows||[a.flow]).includes(f));
 const quoted=(a.references||[]).length>0&&verifyReferences(a.references,index)&&a.references.every(r=>a.answer.includes(r.quote)&&a.answer.includes(`【来源${r.id}】`));
 const allSources=c.gold_ids.every(id=>ids.includes(id));
 const abstained=!a.sources.length&&['no_evidence','clarification'].includes(a.mode);
 return{id:c.id,question:c.question,category:c.category,gold_ids:c.gold_ids,retrieved_ids:ids,route:a.flow,flows:a.flows||[a.flow],route_pass:routeOK,
  hit:c.gold_ids.length?Number(hitIds.length>0):null,recall:c.gold_ids.length?hitIds.length/c.gold_ids.length:null,
  mrr:c.gold_ids.length?(hitIds.length?1/(ids.findIndex(id=>c.gold_ids.includes(id))+1):0):null,
  key_coverage:c.key_points.length?keyHits.length/c.key_points.length:null,missing_keys:c.key_points.filter(k=>!keyHits.includes(k)),
  quote_verified:quoted,abstained,pass:c.expect_abstain?abstained:routeOK&&allSources&&keyHits.length===c.key_points.length&&quoted,
  answer:a.answer,references:a.references||[],mode:a.mode};
}
export function summarize(rows){const positive=rows.filter(r=>r.hit!==null),negative=rows.filter(r=>r.hit===null),mean=key=>positive.reduce((n,r)=>n+r[key],0)/positive.length;
 return{total:rows.length,passed:rows.filter(r=>r.pass).length,answerable:positive.length,hit_at_5:mean('hit'),labeled_recall_at_5:mean('recall'),mrr_at_5:mean('mrr'),
  quoted_answer_count:positive.filter(r=>r.quote_verified).length,correct_abstentions:negative.filter(r=>r.abstained).length,unanswerable:negative.length,
  criterion_passed:rows.filter(r=>r.pass).length/rows.length>=.95&&positive.every(r=>r.quote_verified)&&negative.every(r=>r.abstained),
  scope:'自编100题开发验收，标签为指定来源而非穷尽相关性；关键点字符串覆盖与引用逐字验证不等于独立人工金融正确率，也非LLM生成准确率'};}
export function evaluate(cases,rows){const ix=new Index(rows),results=cases.rows.map(c=>scoreCase(c,answerQuestion(c.question,ix,{last:c.previous||''}),ix));return{summary:summarize(results),rows:results};}
