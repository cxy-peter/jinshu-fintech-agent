/** Extractive presentation only: no newly generated financial claims. */
import {tokens} from './core.mjs';
export function evidencePreview(answer) {
  const refs=answer.references||[],terms=[...new Set(tokens(answer.query||''))].filter(x=>x.length>1);
  const ranked=[];
  for(const ref of refs){const paragraphs=ref.quote.split(/\n\s*\n/).map(s=>s.trim()).filter(Boolean);
    for(const quote of paragraphs){const score=terms.reduce((n,t)=>n+Number(quote.toLowerCase().includes(t.toLowerCase())),0);ranked.push({ref,quote,score});}}
  ranked.sort((a,b)=>b.score-a.score);
  const selected=[],seen=new Set();for(const item of ranked){if(seen.has(item.quote))continue;seen.add(item.quote);selected.push({...item,display:item.quote.length>620?item.quote.slice(0,620)+'…（节选，完整条件请展开原文）':item.quote});if(selected.length===2)break;}
  return selected;
}
export function nextAction(answer) {
  if(!answer.sources?.length)return '请补充相关资料或明确任务范围；未找到依据不等于该事项被禁止。';
  if(answer.tool)return '下面的工具结果使用模拟默认参数。处理自己的任务，请到业务工具确认输入，再执行、复核和导出。';
  return '先核对来源及适用范围；需要更易读的文字草稿时，可自愿授权调用已配置模型。原文仍作为核对依据。';
}
