import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizePack,makeIndex,selectedPassages} from '../core/web/personal-data.mjs';

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
