/** Additive overlay: retain upstream prompts, but bound/cancel execution and select only final text. */
import { Agent, type AgentTool } from '@earendil-works/pi-agent-core';
import type { AgentRuntime,AgentType,AgentExecutionResult } from './agents.upstream.js';
export type { AgentRuntime,AgentType,AgentExecutionResult } from './agents.upstream.js';
export {INTENT_PROMPT,REWRITER_PROMPT,ANSWER_PROMPT,VERIFIER_PROMPT} from './agents.upstream.js';
export async function runAgent(runtime:AgentRuntime,systemPrompt:string,prompt:string,tools:AgentTool[]=[],timeoutMs=30000):Promise<string>{
 if(!Number.isFinite(timeoutMs)||timeoutMs<1||timeoutMs>120000)throw new Error('invalid execution deadline');
 const agent=new Agent({initialState:{systemPrompt,model:runtime.model,tools},streamFn:runtime.streamFn});
 let timer:ReturnType<typeof setTimeout>|undefined;let expired=false;
 const deadline=new Promise<never>((_,reject)=>{timer=setTimeout(()=>{expired=true;agent.abort();reject(new Error('pi execution deadline exceeded; abort requested'));},timeoutMs);});
 try{
  await Promise.race([agent.prompt(prompt),deadline]);
  if(expired||agent.state.errorMessage)throw new Error(agent.state.errorMessage||'deadline exceeded');
  const message=[...agent.state.messages].reverse().find(m=>m.role==='assistant');
  if(!message||message.role!=='assistant')throw new Error('missing final assistant message');
  if(message.stopReason==='aborted'||message.stopReason==='error')throw new Error('assistant did not complete');
  const text=message.content.filter(c=>c.type==='text').map(c=>c.text).join('').trim();
  if(!text)throw new Error('empty final response');return text;
 }finally{if(timer)clearTimeout(timer);if(expired)agent.abort();}
}
export function extractJson(raw:string):unknown{
 const s=raw.trim().replace(/^```(?:json)?\s*/,'').replace(/\s*```$/,'');
 if(!s.startsWith('{')&&!s.startsWith('['))throw new Error('expected one JSON value');
 const parsed=JSON.parse(s);if(parsed===null||typeof parsed!=='object')throw new Error('expected object or array');return parsed;
}
export async function runAgentJson(runtime:AgentRuntime,systemPrompt:string,prompt:string,tools:AgentTool[]=[],timeoutMs=30000):Promise<unknown>{return extractJson(await runAgent(runtime,systemPrompt,prompt,tools,timeoutMs));}
export async function executeAgent(runtime:AgentRuntime,agentType:AgentType,systemPrompt:string,prompt:string,outputMode:'text'|'json',allowedTools:string[]=[],timeoutMs=30000):Promise<AgentExecutionResult>{
 const started=Date.now(),tools=runtime.tools.filter(t=>allowedTools.includes(t.name));
 const output=outputMode==='json'?await runAgentJson(runtime,systemPrompt,prompt,tools,timeoutMs):await runAgent(runtime,systemPrompt,prompt,tools,timeoutMs);
 return{agentType,output,outputMode,latencyMs:Date.now()-started};
}
