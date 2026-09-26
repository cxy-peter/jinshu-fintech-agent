'use strict';
const $ = id => document.getElementById(id);
let state = null, history = [], documents = [], active = null, generation = 0;
let tools = [], toolRevision = 0, result = null;
const notice = message => { $('notice').textContent = message; $('notice').hidden = !message; };
function headers() { const h={'Content-Type':'application/json'}; const code=$('access-code').value.trim(); if(code)h.Authorization='Bearer '+code; return h; }
async function api(url, options={}) {
  const response = await fetch(url, {...options, headers:{...headers(), ...(options.headers||{})}, cache:'no-store'});
  let data;
  try { data = await response.json(); } catch { throw new Error('服务未返回 JSON。请检查 Vercel 构建和运行日志。'); }
  if (!response.ok) throw new Error(data.error?.message || ('请求失败：HTTP '+response.status));
  return data;
}
function text(tag, value, className) {const element=document.createElement(tag);element.textContent=value;if(className)element.className=className;return element;}
function download(value,name,type='application/json') {const blob=new Blob([typeof value==='string'?value:JSON.stringify(value,null,2)],{type}); const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
function tab(name) { for(const b of document.querySelectorAll('.nav-button'))b.classList.toggle('selected',b.dataset.tab===name); for(const id of ['chat','tools','status'])$(id+'-tab').hidden=id!==name; notice(''); }
for(const b of document.querySelectorAll('[data-tab]'))b.onclick=()=>tab(b.dataset.tab);
function statusRows(s) {
  $('status-details').replaceChildren();
  const rows=[['运行版本', 'V'+s.version+' · '+s.mode+' · '+s.entrypoint],['模型',s.model.provider+' / '+(s.model.model||'未指定')],['配置状态',s.model.configured?'已配置，实际调用需单独验证':'待配置'],['缺少变量',s.model.missing.join(', ')||'无'],['无效变量',s.model.invalid.join(', ')||'无'],['访问方式',s.model.access_required?'需要工作台访问码':'开放聊天（请注意额度）'],['验证环境',s.test_transport?'HTTP协议模拟测试，不是真实 DeepSeek':'真实服务端模型通道；当前页面尚不证明连通']];
  for(const [k,v] of rows){const row=text('div','', 'status-row');row.append(text('span',k),text('span',v));$('status-details').append(row);}
  for(const warning of s.model.warnings)$('status-details').append(text('p',warning,'muted'));
}
async function refreshStatus() {
  try {state=await api('/api/status');$('runtime-badge').textContent='V'+state.version+' · 本地与线上同一运行入口';$('model-status').textContent=state.test_transport?'HTTP 模拟测试环境 · 非真实 DeepSeek':state.model.configured?'DeepSeek 配置已就绪 · 等待实际调用':'DeepSeek 待配置 · 业务工具可直接使用';$('access-panel').hidden=!state.model.access_required;statusRows(state);}
  catch(error){$('model-status').textContent='服务状态读取失败';notice(error.message);}
}
$('refresh-status').onclick=refreshStatus;
function message(role,content,kind='') {
  $('welcome')?.remove();const wrapper=text('article','', 'message '+role+' '+kind);wrapper.append(text('div',role==='user'?'你':'金枢','message-label'),text('div',content,'message-body'));$('messages').append(wrapper);$('messages').scrollTop=$('messages').scrollHeight;return wrapper;
}
function renderAnswer(data,node) {
  node.classList.remove('pending');node.querySelector('.message-body').textContent=data.answer;
  for(const warning of data.warnings||[])node.append(text('div',warning,'warning'));
  if(data.sources?.length){const details=document.createElement('details');details.append(text('summary',`本次检索片段 · ${data.sources.length} 条（不等于事实已全部核验）`));for(const source of data.sources)details.append(text('p',`[${source.source_id}] ${source.title}`),text('p',source.text));node.append(details);}
  const trace=document.createElement('details');trace.append(text('summary',`执行记录 · ${data.model_call.model} · ${data.model_call.latency_ms}ms`),text('pre',JSON.stringify({trace_id:data.trace_id,model:data.model_call,verification:data.verification,trace:data.trace},null,2)));node.append(trace);
  const actions=text('div','','message-actions');const save=text('button','导出回答与执行记录');save.onclick=()=>download(data,'jinshu-answer-'+data.trace_id+'.json');actions.append(save);node.append(actions);
  $('model-status').textContent=data.model_call.inference_verified?'本次已收到 DeepSeek 实际响应':'本次为 HTTP 协议模拟测试（不计为真实调用）';
  $('messages').scrollTop=$('messages').scrollHeight;
}
$('chat-form').onsubmit=async event=>{
  event.preventDefault();if(active)return;
  const query=$('query').value.trim();if(!query)return;
  if(!$('consent').checked){notice('发送前，请先确认本次内容可以交给 DeepSeek。');$('consent').focus();return;}
  const current=++generation, controller=new AbortController();active=controller;
  const snapshot={query,history:history.slice(-8),documents:documents.map(d=>({...d})),include_examples:$('include-examples').checked,consent:true};
  message('user',query);const pending=message('assistant','正在检索本次资料并请求模型…','pending');
  $('send').disabled=true;$('cancel').hidden=false;$('request-state').textContent='请求处理中，可以停止等待。';$('query').value='';notice('');
  const timeout=setTimeout(()=>controller.abort('timeout'),95000);
  try {const answer=await api('/api/chat',{method:'POST',body:JSON.stringify(snapshot),signal:controller.signal});if(current!==generation)return;renderAnswer(answer,pending);history.push({role:'user',content:query.slice(0,1500)},{role:'assistant',content:answer.answer.slice(0,1500)});history=history.slice(-8);}
  catch(error){if(current!==generation)return;pending.classList.remove('pending');pending.classList.add('error');$('model-status').textContent='本次未获得模型回答，请查看错误提示';pending.querySelector('.message-body').textContent=controller.signal.aborted?'已停止等待；服务端调用可能已发送并产生费用。':error.message;}
  finally {clearTimeout(timeout);if(current===generation){active=null;$('send').disabled=false;$('cancel').hidden=true;$('request-state').textContent='对话只保留在当前页面，刷新后清空。';}}
};
$('cancel').onclick=()=>active?.abort();
$('clear-chat').onclick=()=>{generation++;active?.abort();active=null;history=[];$('messages').replaceChildren(text('div','本次对话已清空；资料栏内容仍保留。','muted'));$('send').disabled=false;$('cancel').hidden=true;$('request-state').textContent='对话只保留在当前页面，刷新后清空。';};
for(const b of document.querySelectorAll('[data-question]'))b.onclick=()=>{$('query').value=b.dataset.question;$('query').focus();};
function renderDocuments() { $('documents').replaceChildren();documents.forEach((d,i)=>{const row=text('div','','doc-item');row.append(text('span',d.title+' · '+d.text.length+'字'));const remove=text('button','移除');remove.onclick=()=>{documents.splice(i,1);renderDocuments();};row.append(remove);$('documents').append(row);});$('doc-count').textContent=documents.length+' / 3'; }
$('add-doc').onclick=()=>{const title=$('doc-title').value.trim(),body=$('doc-text').value.trim();if(!title||!body){notice('请填写资料标题和内容。');return;}if(documents.length>=3||body.length>12000||documents.reduce((n,d)=>n+d.text.length,0)+body.length>20000){notice('资料最多3份，每份12000字，合计20000字。');return;}documents.push({title,text:body});$('doc-title').value='';$('doc-text').value='';notice('');renderDocuments();};
$('doc-file').onchange=async()=>{const file=$('doc-file').files[0];if(!file)return;try{if(!/\.(txt|md|csv|json)$/i.test(file.name)||file.size>60000)throw Error('只支持不超过60KB的文本/Markdown/CSV/JSON文件。PDF与Word请先复制文字。');const body=await file.text();if(body.length>12000)throw Error('单份资料最多12000字，请拆分。');$('doc-title').value=file.name.slice(0,120);$('doc-text').value=body;}catch(e){notice(e.message);}finally{$('doc-file').value='';}};
$('model-check').onclick=async()=>{if(!$('check-consent').checked){notice('请先同意发送一次公开的模型连接测试。');return;}$('model-check').disabled=true;$('check-result').textContent='正在调用配置的模型…';try{const result=await api('/api/model-check',{method:'POST',body:JSON.stringify({consent:true})});$('check-result').textContent=JSON.stringify(result,null,2);$('model-status').textContent=result.inference_verified?'连接测试收到 DeepSeek 实际响应':'连接测试使用 HTTP 模拟端点';}catch(e){$('check-result').textContent=e.message;$('model-status').textContent='模型连接测试失败';}finally{$('model-check').disabled=false;}};
function invalidateTool(){toolRevision++;result=null;$('reviewed').checked=false;$('reviewed').disabled=true;$('export-json').disabled=true;$('export-csv').disabled=true;$('result-note').textContent='参数或数据已修改，请重新运行。';}
function toolSchema(){const entry=tools.find(t=>t.id===$('tool-select').value);$('tool-schema').textContent=entry?`参数：${entry.required_values.join('、')||'无额外参数'}；数据文件：${entry.required_sources.join('、')}`:'';}
$('tool-select').onchange=()=>{invalidateTool();$('tool-values').value='{}';$('tool-sources').value='';$('tool-examples').checked=false;toolSchema();};
$('tool-values').oninput=invalidateTool;$('tool-sources').oninput=()=>{$('tool-examples').checked=false;invalidateTool();};$('tool-examples').onchange=invalidateTool;
$('load-example').onclick=async()=>{const name=$('tool-select').value;invalidateTool();const revision=toolRevision;try{const data=await api('/api/tools/'+name+'/example');if(revision!==toolRevision)return;$('tool-values').value=JSON.stringify(data.values,null,2);$('tool-sources').value=JSON.stringify(data.sources,null,2);$('tool-examples').checked=true;notice('已加载合成示例，尚未执行。示例不是你的真实业务数据。');}catch(e){notice(e.message);}};
$('run-tool').onclick=async()=>{invalidateTool();const revision=toolRevision;$('run-tool').disabled=true;notice('');try{const payload={values:JSON.parse($('tool-values').value),use_examples:$('tool-examples').checked};if(!payload.use_examples)payload.sources=JSON.parse($('tool-sources').value||'null');const data=await api('/api/tools/'+$('tool-select').value,{method:'POST',body:JSON.stringify(payload)});if(revision!==toolRevision){notice('输入已经改变，旧请求的结果未采用。');return;}result=data;$('tool-result').textContent=JSON.stringify(data,null,2);$('result-note').textContent=data.synthetic?'这是合成数据计算结果，请复核后导出。':'这是本次用户数据的计算结果，请复核后导出。';$('reviewed').disabled=false;}catch(e){$('tool-result').textContent=e.message;notice(e instanceof SyntaxError?'JSON格式不正确，请检查逗号和引号。':e.message);}finally{$('run-tool').disabled=false;}};
$('reviewed').onchange=()=>{const allowed=$('reviewed').checked&&result;$('export-json').disabled=!allowed;$('export-csv').disabled=!allowed;};
async function exportTool(format){if(!result||!$('reviewed').checked)return;try{const response=await fetch('/api/export',{method:'POST',headers:headers(),body:JSON.stringify({result,reviewed:true,format})});if(!response.ok){const data=await response.json();throw Error(data.error?.message||'导出失败');}download(await response.text(),'jinshu-result.'+format,format==='csv'?'text/csv':'application/json');}catch(e){notice(e.message);}}
$('export-json').onclick=()=>exportTool('json');$('export-csv').onclick=()=>exportTool('csv');
async function init(){await refreshStatus();try{tools=await api('/api/tools');for(const entry of tools){const option=text('option',entry.name);option.value=entry.id;$('tool-select').append(option);}toolSchema();}catch(e){notice(e.message);}}
init();
