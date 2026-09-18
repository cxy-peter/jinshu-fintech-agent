/** Real pi runtime with a deterministic test stream. Not live model acceptance. */
import assert from 'node:assert/strict';
import {AssistantMessageEventStream} from '@earendil-works/pi-ai';
import {runAgent,executeAgent,extractJson} from './dist/agents.js';
const model={api:'openai-completions',provider:'fixture',id:'fixture',name:'fixture',reasoning:false,input:['text'],cost:{input:0,output:0,cacheRead:0,cacheWrite:0},contextWindow:2048,maxTokens:100};
const message=text=>({role:'assistant',content:[{type:'text',text}],api:model.api,provider:model.provider,model:model.id,stopReason:'stop',usage:{input:1,output:1,cacheRead:0,cacheWrite:0,totalTokens:2,cost:{input:0,output:0,cacheRead:0,cacheWrite:0,total:0}},timestamp:Date.now()});
let calls=0;
const runtime={model,tools:[],streamFn:()=>{calls++;const s=new AssistantMessageEventStream();queueMicrotask(()=>s.push({type:'done',reason:'stop',message:message('【来源1】保留待提交草稿。')}));return s;}};
const r=await executeAgent(runtime,'answer','fixture','fixture','text',[],1000);assert.equal(r.output,'【来源1】保留待提交草稿。');assert.equal(calls,1);
assert.deepEqual(extractJson('```json\n{"passed":true}\n```'),{passed:true});assert.throws(()=>extractJson('prefix {"passed":true}'));assert.throws(()=>extractJson('{"x":1} {"y":2}'));
let aborted=false;
const slow={...runtime,streamFn:(_m,_c,options)=>{const s=new AssistantMessageEventStream();options.signal.addEventListener('abort',()=>{aborted=true;s.push({type:'error',reason:'aborted',error:{...message(''),stopReason:'aborted',errorMessage:'fixture aborted'}});});return s;}};
await assert.rejects(()=>runAgent(slow,'s','p',[],25),/deadline/);await new Promise(r=>setTimeout(r,20));assert.equal(aborted,true);
console.log(JSON.stringify({checks:{actual_pi_agent_with_fixture_stream:true,final_message_selected:true,json_value_contract:true,timeout_requests_abort:true},live_model:false,note:'Contract test of real package; synthetic provider output is not LLM generation.'}));
