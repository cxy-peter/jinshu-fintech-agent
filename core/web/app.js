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
function tab(name) { for(const b of document.querySelectorAll('.nav-button'))b.classList.toggle('selected',b.dataset.tab===name); for(const section of document.querySelectorAll('main > section.tab'))section.hidden=section.id!==name+'-tab'; window.workspaceBridge?.onTab(name); notice(''); }
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
function sourceLocation(source){return source.location_kind==='logical_text_section'?'文本段 '+source.page:'原文第 '+source.page+' 页';}
function renderAnswer(data,node) {
  node.querySelector('.retrieval-progress')?.remove();
  node.classList.remove('pending');node.querySelector('.message-body').textContent=data.answer;
  for(const warning of data.warnings||[])node.append(text('div',warning,'warning'));
  if(data.sources?.length){const details=document.createElement('details');details.append(text('summary',`本次检索片段 · ${data.sources.length} 条（不等于事实已全部核验）`));for(const source of data.sources){details.append(text('p',`[${source.source_id}] ${source.title}${source.page?' · '+sourceLocation(source):''}${source.origin==='personal_local'?' · 个人资料':''}`),text('p',source.text));if(source.origin==='shared_reference'){const open=text('button','查看共享原文');open.onclick=()=>window.workspaceBridge?.openReference(source.doc_id,source.page).catch(e=>notice(e.message));details.append(open);} if(source.origin==='personal_local'&&source.chunk_id){const open=text('button','查看本机原文');open.onclick=()=>window.personalBridge?.open(source.chunk_id,source.page);details.append(open);}}node.append(details);}
  if(data.sources?.some(s=>s.origin==='private_cloud'||s.origin==='local_folder')){const links=text('div','','document-actions');for(const s of data.sources.filter(s=>['private_cloud','local_folder'].includes(s.origin))){const b=text('button',`查看 ${s.title} · ${s.location_kind==='logical_text_section'?'文本段':'第'}${s.page}${s.location_kind==='logical_text_section'?'':'页'}`);b.onclick=()=>window.dataSources?.openSource(s).catch(e=>notice(e.message));links.append(b);}node.append(links);}
  window.businessBridge?.renderSuggestions(node,data.business_suggestions);
  const trace=document.createElement('details');trace.append(text('summary',`执行记录 · 检索 ${data.retrieval?.elapsed_ms??'—'}ms · ${data.model_call.model} ${data.model_call.latency_ms}ms`),text('pre',JSON.stringify({trace_id:data.trace_id,retrieval:data.retrieval,model:data.model_call,verification:data.verification,trace:data.trace},null,2)));node.append(trace);
  const actions=text('div','','message-actions');const save=text('button','导出回答与执行记录');save.onclick=()=>download(data,'jinshu-answer-'+data.trace_id+'.json');actions.append(save);node.append(actions);
  $('model-status').textContent=data.model_call.status==='not_called'?'本次无足够依据，未调用模型':data.model_call.inference_verified?'本次已收到 DeepSeek 实际响应':'本次为 HTTP 协议模拟测试（不计为真实调用）';
  $('messages').scrollTop=$('messages').scrollHeight;
}
async function streamedAnswer(snapshot, controller, pending, current){
  const response=await fetch('/api/chat/stream',{method:'POST',headers:headers(),body:JSON.stringify(snapshot),signal:controller.signal});
  if(!response.ok){const d=await response.json();throw Error(d.error?.message||'请求失败');}
  const reader=response.body.getReader(),decoder=new TextDecoder();let buffer='',answer=null;
  while(true){const {value,done}=await reader.read();buffer+=decoder.decode(value||new Uint8Array(),{stream:!done});let at;
    while((at=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,at);buffer=buffer.slice(at+2);if(!frame.startsWith('data: '))continue;const event=JSON.parse(frame.slice(6));
      if(current!==generation)continue;
      if(event.event==='error')throw Error(event.message);
      if(event.event==='answer')answer=event.data;
      if(event.event==='retrieval'){
        pending.querySelector('.message-body').textContent=event.sources.length?`已找到 ${event.sources.length} 个资料片段，正在组织有引用的回答…`:'未找到充分匹配的正文，正在检查检索范围…';
        const card=text('div','','retrieval-progress');card.append(text('p',`检索耗时 ${event.diagnostics.elapsed_ms}ms · 此阶段未调用模型`,'muted'));
        for(const s of event.sources.slice(0,3))card.append(text('p',`${s.title}${s.page?' · '+sourceLocation(s):''}`),text('blockquote',s.text.slice(0,220)));
        pending.append(card);$('request-state').textContent='原文已返回；模型完成后显示经引用检查的答案。';
      }
    }
    if(done)break;
  }
  if(!answer)throw Error('回答连接中断；未生成替代答案，请重试。');return answer;
}
$('chat-form').onsubmit=async event=>{
  event.preventDefault();if(active)return;
  const query=$('query').value.trim();if(!query)return;
  if(!$('consent').checked){notice('发送前，请先确认本次内容可以交给 DeepSeek。');$('consent').focus();return;}
  const current=++generation, controller=new AbortController();active=controller;
  const snapshot={...(window.workspaceBridge?.chatFields()||{}),...(window.dataSources?.chatFields()||{}),query,history:history.slice(-8),documents:documents.map(d=>({...d})),include_examples:$('include-examples').checked,consent:true};
  message('user',query);const pending=message('assistant','正在检索本次资料并请求模型…','pending');
  $('send').disabled=true;$('cancel').hidden=false;$('request-state').textContent='请求处理中，可以停止等待。';$('query').value='';notice('');
  const timeout=setTimeout(()=>controller.abort('timeout'),95000);
  try {await window.workspaceReady;await window.dataSources?.ready;Object.assign(snapshot,window.dataSources?.chatFields()||{});snapshot.personal_passages=await window.personalBridge?.search(query,history)||[];if(current!==generation||controller.signal.aborted)return;const answer=await streamedAnswer(snapshot,controller,pending,current);if(current!==generation)return;renderAnswer(answer,pending);window.workspaceBridge?.answered(answer,pending);history.push({role:'user',content:query.slice(0,1500)},{role:'assistant',content:answer.answer.slice(0,1500)});history=history.slice(-8);}
  catch(error){if(current!==generation)return;pending.classList.remove('pending');pending.classList.add('error');$('model-status').textContent='本次未获得模型回答，请查看错误提示';pending.querySelector('.message-body').textContent=controller.signal.aborted?'已停止等待；服务端调用可能已发送并产生费用。':error.message;}
  finally {clearTimeout(timeout);if(current===generation){active=null;$('send').disabled=false;$('cancel').hidden=true;$('request-state').textContent='可保存与恢复对话；新对话不会继承旧问题。';}}
};
let composing=false;
$('query').addEventListener('compositionstart',()=>{composing=true;});
$('query').addEventListener('compositionend',()=>{composing=false;});
$('query').addEventListener('keydown',event=>{
  if(event.key!=='Enter'||event.shiftKey||event.isComposing||composing||event.keyCode===229)return;
  event.preventDefault();if(!active&&!event.repeat)$('chat-form').requestSubmit();
});
$('cancel').onclick=()=>active?.abort();
$('clear-chat').onclick=()=>{window.workspaceBridge?.newChat();generation++;active?.abort();active=null;history=[];$('messages').replaceChildren(text('div','本次对话已清空；资料栏内容仍保留。','muted'));$('send').disabled=false;$('cancel').hidden=true;$('request-state').textContent='可保存与恢复对话；新对话不会继承旧问题。';};
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
