import test from 'node:test';import assert from 'node:assert/strict';import {readFileSync} from 'node:fs';import {Index} from '../web/core.mjs';import {answerQuestion,scopeCheck,verifyReferences} from '../web/assurance.mjs';
const rows=JSON.parse(readFileSync(new URL('../web/knowledge.json',import.meta.url))),ix=new Index(rows);
test('references point to verbatim current source',()=>{const a=answerQuestion('商业银行四个职能是什么',ix);assert.ok(verifyReferences(a.references,ix));assert.ok(a.answer.includes('原文摘录'));assert.ok(a.references.every(r=>a.answer.includes(r.quote)))});
test('capability question is not an account-state request',()=>{assert.equal(scopeCheck('客服知识库能直接告诉我具体账户的实时状态吗？'),null);assert.ok(scopeCheck('现在我个人账户的提现是否已经到账？'))});
test('financial and weekly subtasks retain both sources',()=>{const a=answerQuestion('核查三表勾稽之后，还需要做周报缺数的哪些检查？',ix);assert.deepEqual(a.flows,['statements','weekly_report']);assert.ok(a.references.some(r=>r.chunk_id==='sim-financial'));assert.ok(a.references.some(r=>r.chunk_id==='sim-weekly'))});
test('unprovided financial figures not fabricated',()=>assert.equal(answerQuestion('请列出本公司尚未提供的2027年财务报表真实利润。',ix).mode,'no_evidence'));
test('quote mutation detected',()=>{const a=answerQuestion('支付中介',ix);a.references[0].quote+=' fabricated';assert.equal(verifyReferences(a.references,ix),false)});
