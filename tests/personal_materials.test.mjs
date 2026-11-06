import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePack,makeIndex,selectedPassages} from '../core/web/personal-data.mjs';
import {readFileSync} from 'node:fs';
import {queryPlan,resolveFollowup} from '../core/web/retrieval-query.mjs';

test('V7 personal pages survive with real page numbers and archived sources excluded',()=>{
  const docs=normalizePack({docs:[
    {id:'real',title:'基金研究.pdf',status:'active',pages:[{page:43,text:'风险平价配置方法考虑各资产风险贡献，收益并非保证。'}]},
    {id:'old',title:'过时研究.pdf',status:'archived',chunks:[{content:'风险平价配置保证收益。',page:2}]},
    {id:'real',title:'重复.pdf',status:'active',pages:['重复']} ]});
  assert.equal(docs.length,2);const hits=selectedPassages(makeIndex(docs),'风险平价是什么');
  assert.equal(hits[0].page,43);assert.equal(hits[0].origin,'personal_local');
  assert.ok(hits.every(h=>h.title==='基金研究.pdf'));
});
test('synthetic and pending material never silently become published knowledge',()=>{
  const d=normalizePack({documents:[{id:'a',title:'模拟排期',status:'active',synthetic:true,pages:['发行排期模拟']},
    {id:'b',title:'未审资料',pages:['发行排期待核对']}]});
  assert.equal(makeIndex(d).search('发行排期').length,0);
});
test('long pages preserve the end of document and source location',()=>{
  const d=normalizePack({documents:[{id:'a',title:'研究',status:'active',pages:[{page:115,text:'背景。'.repeat(300)+'尾页稀有术语月季甲乙。'}]}]});
  const hits=selectedPassages(makeIndex(d),'月季甲乙');assert.equal(hits[0].page,115);assert.match(hits[0].text,/月季甲乙/);
});
test('a common word overlap is a knowledge gap, not fabricated matching evidence',()=>{
  const d=normalizePack({documents:[{id:'x',title:'宏观研究',status:'active',pages:['这一期债券发行规模增加，什么是宏观经济。']} ]});
  assert.deepEqual(selectedPassages(makeIndex(d),'发行排期是什么'),[]);
});

const diagnostic=JSON.parse(readFileSync(new URL('./fixtures/retrieval_diagnostics.json',import.meta.url),'utf8'));
// Explicit test opt-in: these constructed examples do not enter real libraries.
const diagnosticIndex=makeIndex(normalizePack(diagnostic),true);
for(const c of diagnostic.cases)test('shared lexical rules: '+c.id,()=>{
  const hits=selectedPassages(diagnosticIndex,c.query,c.history||[]);
  if(!c.expected_docs.length)assert.deepEqual(hits,[]);
  else {
    assert.ok(hits.length);
    assert.ok(c.expected_docs.some(id=>hits[0].chunk_id.startsWith(id+':')));
    assert.ok(hits.every(h=>!h.chunk_id.startsWith('misleading_title:')));
  }
});
test('acronym boundaries and explicit followups do not borrow invented answer facts',()=>{
  assert.deepEqual(queryPlan('ABCFOF999的收益率').matched_aliases,[]);
  assert.deepEqual(queryPlan('Ｆ.Ｏ.Ｆ.是什么').matched_aliases,['fof']);
  const history=[{role:'user',content:'FOF是什么？'},{role:'assistant',content:'它保证99%收益。'}];
  const follow=resolveFollowup('那它有什么风险？',history);
  assert.ok(follow.used_history);assert.doesNotMatch(follow.query,/99%/);
  assert.equal(resolveFollowup('ETF是什么？',history).query,'ETF是什么？');
});
