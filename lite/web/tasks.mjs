/** Versioned local tool tasks. Approval applies only to the exact current result. */
import {digest} from './policy.mjs';
export const STATUS={draft:'待执行',running:'处理中',failed:'执行失败',needs_review:'待人工复核',incomplete:'缺少必要数据',approved:'已确认本版结果',exported:'已生成本版导出文件'};
export function newTask(flow,params) {return {id:'task-'+crypto.randomUUID(),flow,params:structuredClone(params),inputVersion:1,requestVersion:0,status:'draft',result:null,approval:null,exports:[],createdAt:new Date().toISOString()};}
export function editTask(task,params) {
  if(JSON.stringify(task.params)===JSON.stringify(params))return task;
  task.params=structuredClone(params);task.inputVersion++;task.requestVersion++;task.status='draft';task.result=null;task.approval=null;task.inputHash=null;return task;
}
export async function runTask(task,executor,fixtures) {
  const request=++task.requestVersion,version=task.inputVersion,params=structuredClone(task.params);
  task.status='running';task.approval=null;task.result=null;task.error=null;
  const inputHash=await digest({flow:task.flow,params,fixtures});
  try {
    const result=await executor(task.flow,params,fixtures);
    if(task.requestVersion!==request||task.inputVersion!==version)return {stale:true};
    const resultHash=await digest(result);
    if(task.requestVersion!==request||task.inputVersion!==version)return {stale:true};
    task.result=result;task.inputHash=inputHash;task.resultHash=resultHash;
    task.status=result.status==='incomplete_needs_review'?'incomplete':'needs_review';task.completedAt=new Date().toISOString();return {stale:false,result};
  }catch(error){if(task.requestVersion!==request||task.inputVersion!==version)return{stale:true};task.status='failed';task.error=error.message;throw error;}
}
export async function approveTask(task,confirmed) {
  if(!confirmed)throw Error('请先核对输入、异常与结果，再确认本版结果');
  if(task.status!=='needs_review'||!task.result||task.result.status==='incomplete_needs_review')throw Error('当前结果尚不可确认');
  if(task.result.passed===false)throw Error('结果检查未通过，不能确认为可交付');
  const version=task.inputVersion,request=task.requestVersion,resultHash=await digest(task.result);
  if(version!==task.inputVersion||request!==task.requestVersion||resultHash!==task.resultHash)throw Error('结果已变化，需重新执行');
  task.approval={inputVersion:version,resultHash,at:new Date().toISOString(),scope:'single_browser_confirmation_not_enterprise_approval'};task.status='approved';return task;
}
export async function prepareExport(task,format) {
  if(!['csv','json','docx'].includes(format))throw Error('未知导出格式');
  const request=task.requestVersion,version=task.inputVersion;
  if(!['approved','exported'].includes(task.status)||task.approval?.inputVersion!==version||await digest(task.result)!==task.approval?.resultHash)throw Error('先复核并确认当前版本，输入变化后必须重跑');
  if(request!==task.requestVersion||version!==task.inputVersion)throw Error('准备导出时输入变化，请重新执行');
  return {taskId:task.id,flow:task.flow,format,inputVersion:version,requestVersion:request,inputHash:task.inputHash,resultHash:task.resultHash,result:structuredClone(task.result),approval:structuredClone(task.approval)};
}
export async function completeExport(task,ticket) {
  const current=await prepareExport(task,ticket.format);
  if(current.taskId!==ticket.taskId||current.requestVersion!==ticket.requestVersion||current.resultHash!==ticket.resultHash||current.inputVersion!==ticket.inputVersion)throw Error('文件生成期间任务发生变化，已停止导出');
  task.exports.push({format:ticket.format,inputVersion:ticket.inputVersion,at:new Date().toISOString(),scope:'file_prepared_not_download_confirmed'});task.status='exported';return ticket.result;
}
// Compatibility helper for function-level callers; UI uses the two-phase path above.
export async function recordExport(task,format) {return completeExport(task,await prepareExport(task,format));}
export function recordOutcome(state,id,value,note='') {
  if(!['resolved','unresolved','needs_review'].includes(value))throw Error('未知反馈状态');
  state.outcomes??=[];let row=state.outcomes.find(x=>x.id===id);
  if(!row){row={id};state.outcomes.push(row);}Object.assign(row,{value,note:String(note).slice(0,1000),at:new Date().toISOString()});return row;
}
export function outcomeMetrics(state) {
  const ids=new Set([...(state.traces||[]),...(state.tasks||[])].map(x=>x.id));
  const feedback=(state.outcomes||[]).filter(x=>ids.has(x.id));
  const resolved=feedback.filter(x=>x.value==='resolved').length;
  return{tasks:ids.size,feedback:feedback.length,resolved,coverage:ids.size?feedback.length/ids.size:null,confirmedResolutionRate:feedback.length?resolved/feedback.length:null,scope:'仅当前浏览器保留记录；未反馈为未知，下载不计为解决。'};
}
