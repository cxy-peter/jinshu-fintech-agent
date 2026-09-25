import test from 'node:test';import assert from 'node:assert/strict';import handler from '../api/answer.mjs';
// No network calls: all providers below are explicit controlled fixtures.
function response(){return{code:200,headers:{},setHeader(k,v){this.headers[k]=v},status(n){this.code=n;return this},json(v){this.body=v;return this}}}
const envKeys=['LITE_AI_ENABLED','LITE_ACCESS_CODE','CHAT_API_KEY','CHAT_BASE_URL','CHAT_MODEL'];
async function call(patch={},provider=null,env={}){const old=Object.fromEntries(envKeys.map(k=>[k,process.env[k]])),fetch=globalThis.fetch;Object.assign(process.env,{LITE_AI_ENABLED:'1',LITE_ACCESS_CODE:'test-access',CHAT_API_KEY:'fixture-not-real',CHAT_BASE_URL:'https://fixture.invalid',CHAT_MODEL:'controlled-fixture'},env);let calls=0;
 globalThis.fetch=async(...args)=>{calls++;if(!provider)throw Error('unexpected provider call');return provider(...args)};
 try{const req={method:'POST',headers:{'x-access-code':'test-access'},body:{question:'什么是信用中介',consent:true,sources:[{id:1,title:'模拟资料',content:'信用中介连接资金供需。'}]},...patch},res=response();await handler(req,res);return{...res,calls};}finally{globalThis.fetch=fetch;for(const[k,v]of Object.entries(old))if(v===undefined)delete process.env[k];else process.env[k]=v}}
test('model disabled is explicit 503 with zero provider calls',async()=>{const r=await call({},null,{LITE_AI_ENABLED:'0'});assert.equal(r.code,503);assert.equal(r.calls,0)});
test('model access code and upstream key remain separate',async()=>{const r=await call({headers:{'x-access-code':'wrong'}});assert.equal(r.code,401);assert.equal(r.calls,0)});
test('model consent is required',async()=>assert.equal((await call({body:{question:'q',sources:[],consent:false}})).code,422));
test('model method restricted',async()=>assert.equal((await call({method:'GET'})).code,405));
test('invalid request JSON rejected',async()=>assert.equal((await call({body:'{' })).code,400));
test('controlled model answer preserves original prompt and budget',async()=>{const r=await call({},async(_,opts)=>{const payload=JSON.parse(opts.body);assert.equal(payload.max_tokens,800);assert.equal(payload.temperature,0);assert.ok(payload.messages[0].content.includes('不执行工具'));assert.ok(opts.signal);return{ok:true,json:async()=>({choices:[{message:{content:'信用中介连接资金供需。【来源1】'}}],model:'controlled-fixture'})}});assert.equal(r.code,200);assert.equal(r.body.verification,'reference_ids_only_not_semantic_review');assert.equal(r.calls,1)});
for(const answer of ['没有引用','不正确的编号【来源2】'])test('invalid model citation rejected '+answer,async()=>{const r=await call({},async()=>({ok:true,json:async()=>({choices:[{message:{content:answer}}]})}));assert.equal(r.code,422)});
test('upstream error preserves fallback contract',async()=>assert.equal((await call({},async()=>({ok:false}))).code,502));
test('upstream timeout is not a fake success',async()=>assert.equal((await call({},async()=>{throw Error('controlled timeout')})).code,502));
