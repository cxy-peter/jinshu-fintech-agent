// The browser and Python use this same bounded vocabulary. It creates matching
// terms only, never source text, a factual answer, or institutional authority.
import lexicon from './retrieval-lexicon.json' with {type:'json'};

export const RETRIEVAL_VERSION=lexicon.version;
const stop=new Set(lexicon.stop_words),strict=new Set(lexicon.strict_anchors),han='\\u3400-\\u9fff';
export function normalize(text) {
  return String(text??'').normalize('NFKC').toLowerCase()
    .replace(/(?<=[a-z])-\s*\n\s*(?=[a-z])/g,'')
    .replace(new RegExp('(?<=['+han+'])\\s*[\\r\\n]+\\s*(?=['+han+'])','g'),'')
    .replace(/\s+/g,' ').trim();
}
const aliasByForm=new Map(lexicon.aliases.flatMap(a=>a.forms.map(f=>[normalize(f),a])));
const escaped=s=>s.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
const formPattern=form=>(/^[a-z0-9]/.test(form)?'(?<![a-z0-9_])':'')+
  escaped(form).replace(/ /g,'\\s+')+(/[a-z0-9.]$/.test(form)?'(?![a-z0-9_])':'');
const aliasPattern=[...aliasByForm.keys()].sort((a,b)=>b.length-a.length).map(formPattern).join('|');
const aliases=()=>new RegExp(aliasPattern,'gi');
const formats=lexicon.format_patterns.map(p=>new RegExp(p,'gi'));
const questions=lexicon.question_patterns.map(p=>new RegExp(p,'gi'));
const aliasItem=match=>aliasByForm.get(match.replace(/\s+/g,' '));

export function baseTokens(text) {
  const result=[];
  for(const part of normalize(text).match(new RegExp('[a-z0-9_]{2,}|['+han+']+','g'))||[]) {
    if(/^[a-z0-9_]/.test(part)) {if(!stop.has(part))result.push(part);}
    else if(part.length===1) {if(!stop.has(part))result.push(part);}
    else for(let i=0;i<part.length-1;i++) {
      const pair=part.slice(i,i+2);
      if(!stop.has(pair)&&!stop.has(part[i])&&!stop.has(part[i+1]))result.push(pair);
    }
  }
  return result;
}
export function retrievalTokens(text) {
  const result=baseTokens(text);
  for(const match of normalize(text).matchAll(aliases()))result.push('concept_'+aliasItem(match[0]).id);
  return result;
}
export function focusQuery(query) {
  let value=normalize(query);
  for(const pattern of formats)value=value.replace(pattern,' ');
  value=value.replace(/[，。！？；：、,!?;:\s]+$/g,'');
  for(const pattern of questions)value=value.replace(pattern,' ');
  return value.replace(/[，。！？；：、,!?;:\[\]（）()]+/g,' ').replace(/\s+/g,' ').trim();
}
export function queryPlan(query) {
  const focus=focusQuery(query),matched=[...new Set([...focus.matchAll(aliases())].map(m=>aliasItem(m[0]).id))];
  const canonical=focus.replace(aliases(),m=>' concept_'+aliasItem(m).id+' ');
  const wanted=new Set(baseTokens(canonical));
  const identifiers=[...wanted].filter(t=>!t.startsWith('concept_')&&/[a-z]/.test(t)&&/\d/.test(t)).sort();
  const unknown=[...new Set((String(query).normalize('NFKC').match(/(?<![A-Za-z0-9_])[A-Z]{2,12}(?![A-Za-z0-9_])/g)||[]).map(t=>t.toLowerCase()))].filter(t=>wanted.has(t));
  return {original:query,focus,terms:wanted,anchors:new Set([...matched.map(x=>'concept_'+x),...unknown]),identifiers,
    required_anchors:new Set([...matched.filter(x=>strict.has(x)).map(x=>'concept_'+x),...unknown]),
    matched_aliases:matched,comparison:/(?:与|和).*(?:区别|差异|不同)|\bvs\b|\bversus\b/i.test(query),
    definition:/是什么|什么是|定义|含义|意思|what is|what are|definition/i.test(query)};
}
export function evidenceMatch(plan,text,tokenSet=null) {
  const actual=tokenSet||new Set(retrievalTokens(text)),hits=[...plan.terms].filter(t=>actual.has(t));
  const anchors=[...plan.anchors].filter(t=>actual.has(t)),coverage=hits.length/Math.max(1,plan.terms.size);
  const lexical=hits.length>0&&coverage>=.45&&(plan.terms.size<3||hits.length>=2);
  let accepted=plan.terms.size>0&&plan.identifiers.every(t=>actual.has(t))&&(plan.required_anchors.size?[...plan.required_anchors].some(t=>actual.has(t)):lexical);
  if((String(text).match(/�/g)||[]).length/Math.max(1,text.length)>.08)accepted=false;
  return {accepted,coverage:Math.round(coverage*10000)/10000,matched_terms:hits.sort(),matched_anchors:anchors.sort(),scope:'topic_related_not_answer_verification'};
}
export function resolveFollowup(query,history=[]) {
  const follow=/^(?:那(?:么)?(?:它|这个|那个|这些|些)?|它|这个|那个|这些|上述|上面|继续|然后|还有呢|再(?:具体|详细)|what about (?:it|that)|and (?:its|their))/.test(normalize(query));
  const standalone={query,mode:'current_question',used_history:false};
  if(!follow||query.length>180)return standalone;
  const current=queryPlan(query);
  const explicitPronoun=/^(?:那(?:么)?)?(?:它|这个|那个|这些)(?:的|怎么|如何|有|该|会|能|呢|为什么|还|要|所|是|和|与|[？?])/.test(normalize(query));
  if((current.required_anchors.size||current.identifiers.length)&&!explicitPronoun)return standalone;
  let prior='';
  for(const message of history.slice(-8).toReversed()) {
    if(message?.role!=='user')continue;
    const candidate=String(message.content||'').slice(0,600);
    if(!candidate.trim()||/^(?:那它|它|这个|那个|这些|继续|还有呢)/.test(normalize(candidate)))continue;
    prior=focusQuery(candidate).slice(0,240);if(prior)break;
  }
  return prior?{query:prior+'\n追问：'+query,mode:'explicit_followup_last_user',used_history:true}:standalone;
}
