/* Server-authoritative task UI. No business calculation, approval or checkpoint in the browser. */
(() => {
  'use strict';
  const $ = id => document.getElementById(id);
  const node = (tag, value, cls) => { const e = document.createElement(tag); if (value !== undefined) e.textContent = value; if (cls) e.className = cls; return e; };
  const names = {validate:'输入与口径检查',weekly_report:'周报质检',wealth_benchmark:'同业对标',verify:'结果规则校验',report:'复核包汇总'};
  const states = {pending:'待执行',running:'执行中',succeeded:'已完成',failed:'失败待处理',attention:'需要处理',blocked:'硬校验未通过',needs_review:'等待独立复核',approved:'已复核，可导出草稿',rejected:'复核退回'};
  let catalog = [], run = null, dirty = false, busy = false, editEpoch = 0, requestId = crypto.randomUUID();
  let capturedCreate = null;
  const message = text => { $('wf-message').textContent = text; };
  function headers() { const h = {'Content-Type':'application/json'}; const code = $('access-code').value.trim(); if (code) h.Authorization = 'Bearer '+code; return h; }
  async function api(url, method='GET', data) {
    const r = await fetch(url, {method, headers:headers(), cache:'no-store', body:data === undefined ? undefined : JSON.stringify(data)});
    const d = await r.json(); if (!r.ok) throw Error(d.error?.message || d.detail || `请求失败 ${r.status}`); return d;
  }
  function action(label, fn) { const b = node('button',label); b.type='button'; b.onclick=async()=>{b.disabled=true; try{await fn();}catch(e){message(e.message);}finally{b.disabled=false;}}; return b; }
  function payload() {return {workflow:$('wf-type').value,values:JSON.parse($('wf-values').value||'{}'),use_examples:$('wf-examples').checked,sources:$('wf-examples').checked?null:JSON.parse($('wf-sources').value||'null')};}
  function changed() {dirty=true;editEpoch++;capturedCreate=null;requestId=crypto.randomUUID();render();}
  function reset() {run=null;dirty=false;capturedCreate=null;requestId=crypto.randomUUID();editEpoch++;$('wf-values').value='{}';$('wf-sources').value='';$('wf-examples').checked=false;render();}
  function schema() {const c=catalog.find(x=>x.id===$('wf-type').value);if(!c)return;$('wf-schema').textContent=`数据：${c.required_sources.join('、')}。参数：${c.required_values.join('、')||'无额外参数'}。先保存快照，再逐批执行。`;}
  function render() {
    const out=$('wf-result');out.replaceChildren();
    $('wf-advance').disabled=busy||!run||dirty||['needs_review','approved','rejected','blocked'].includes(run?.status);
    $('wf-save').disabled=busy;
    if(!run){out.append(node('p','保存任务后显示服务器步骤与恢复状态。'));return;}
    out.append(node('h2',`任务 ${run.id.slice(0,8)} · v${run.revision}`),node('p',`状态：${states[run.status]||run.status} · 提交者：${run.author}`));
    if(dirty)out.append(node('p','输入已改，尚未保存。旧结果不能复核或导出。','warning'));
    if(run.payload.synthetic)out.append(node('p','合成示例：用于演示和验收，不代表公司数据或真实经营效果。','warning'));
    const table=node('table'),head=node('tr');for(const x of ['步骤','状态','尝试次数','本次耗时','复用'])head.append(node('th',x));table.append(head);
    for(const [key,n] of Object.entries(run.nodes)){const tr=node('tr');for(const x of [names[key]||key,states[n.status]||n.status,n.attempts,n.duration_ms==null?'—':n.duration_ms+' ms',n.reused?'沿用未改变结果':'—'])tr.append(node('td',String(x)));table.append(tr);if(n.error)out.append(node('p',`${names[key]||key}：${n.error}`,'warning'));}
    const wrap=node('div',undefined,'wf-table');wrap.append(table);out.append(wrap);
    if(run.quality){out.append(node('h3',`${run.quality.label} · ${run.quality.description}`));for(const w of [...run.quality.warnings,...run.quality.failures])out.append(node('p',`${w.tool}：${typeof w.detail==='string'?w.detail:JSON.stringify(w.detail)}`));}
    for(const [key,n] of Object.entries(run.nodes)){if(n.result){const d=node('details');d.append(node('summary',`${names[key]||key} · 查看结果`),node('pre',JSON.stringify(n.result,null,2)));out.append(d);}}
    const history=node('details');history.append(node('summary','执行事件、检查点与复核凭据'),node('pre',JSON.stringify({input_hash:run.input_hash,recipe_version:run.recipe_version,approval:run.approval,events:run.events},null,2)));out.append(history);
    if(run.status==='needs_review'&&!dirty){const reason=node('input');reason.placeholder='独立复核意见（由另一账号填写）';reason.maxLength=500;out.append(reason);for(const [label,decision] of [['确认当前版本','approve'],['退回修改','reject']])out.append(action(label,async()=>{const expected=editEpoch,id=run.id,revision=run.revision,opinion=reason.value.trim();if(!opinion)throw Error('请先填写当前任务的复核意见。');const r=await api(`/api/workflows/${id}/review`,'POST',{revision,decision,reason:opinion});if(expected===editEpoch){run=r;render();}await refresh();}));out.append(node('p','提交者不能自审。演示时可在页面底部切换审核账号；复核不等于真实业务授权。','muted'));}
    if(run.status==='approved'&&!dirty){for(const format of ['json','csv'])out.append(action(`下载复核包 ${format.toUpperCase()}`,async()=>{const expected=editEpoch;const r=await fetch(`/api/workflows/${run.id}/export?revision=${run.revision}&format=${format}`,{headers:headers()});if(!r.ok){const d=await r.json();throw Error(d.error?.message||'导出失败');}const blob=await r.blob();if(expected!==editEpoch||dirty)throw Error('输入已变化，旧下载未采用');const a=node('a');a.href=URL.createObjectURL(blob);a.download=`jinshu-${run.id}-v${run.revision}.${format}`;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}));}
  }
  async function load(id){
    if(busy){message('正在处理当前操作，请完成后再切换任务。');return;}
    const expected=++editEpoch;busy=true;run=null;dirty=false;capturedCreate=null;render();
    $('wf-result').replaceChildren(node('p','正在读取服务器任务，请稍后填写复核意见。'));
    try{const r=await api('/api/workflows/'+id);if(expected!==editEpoch)return;run=r;
      $('wf-type').value=r.workflow;$('wf-values').value=JSON.stringify(r.payload.values,null,2);
      $('wf-sources').value=JSON.stringify(r.payload.sources,null,2);$('wf-examples').checked=r.payload.synthetic;schema();
    }finally{busy=false;render();}
  }
  async function refresh(){
    const m=await api('/api/workflow-metrics');$('wf-metrics').textContent=`本人保留任务 ${m.submitted} · 待审 ${m.awaiting_review} · 获审 ${m.approved} · 阻断 ${m.blocked} · 执行尝试 ${m.step_attempts} · 当前版本复用步骤 ${m.reused_steps_current_revision}。不代表任务正确率。`;
    const rows=await api('/api/workflows');const target=$('wf-history');target.replaceChildren();for(const r of rows)target.append(action(`${r.workflow} · v${r.revision} · ${states[r.status]||r.status}`,()=>load(r.id)));
    $('wf-queue').replaceChildren();
    try{for(const r of await api('/api/workflows?queue=true'))$('wf-queue').append(action(`${r.author} · ${r.workflow} · v${r.revision}`,()=>load(r.id)));}catch{/* Non-reviewer accounts cannot read the queue. */}
  }
  $('wf-type').onchange=()=>{reset();schema();};
  $('wf-values').oninput=changed;$('wf-sources').oninput=()=>{$('wf-examples').checked=false;changed();};$('wf-examples').onchange=changed;
  $('wf-example').onclick=()=>{const c=catalog.find(x=>x.id===$('wf-type').value);if(!c)return;$('wf-values').value=JSON.stringify(c.example.values,null,2);$('wf-sources').value=JSON.stringify(c.example.sources,null,2);$('wf-examples').checked=true;changed();message('示例已填入，尚未提交；只有保存时才上传到任务存储。');};
  $('wf-new').onclick=()=>{reset();schema();message('已开始新任务。');};
  $('wf-refresh').onclick=()=>refresh().then(()=>message('已刷新本人任务与有权访问的复核队列。')).catch(e=>message(e.message));
  $('wf-save').onclick=async()=>{
    busy=true;render();const expected=editEpoch;
    try{const p=payload();const body=JSON.stringify(p);
      if(!run&&capturedCreate!==body){requestId=crypto.randomUUID();capturedCreate=body;}
      const r=run?await api('/api/workflows/'+run.id,'PUT',{...p,revision:run.revision}):await api('/api/workflows','POST',{...p,request_id:requestId});
      if(expected===editEpoch){run=r;dirty=false;render();message('当前输入已保存，旧复核已失效；点击执行一个批次。');}else message('旧输入已保存为任务，当前输入另有修改，请刷新任务后核对。');
      await refresh();
    }catch(e){message(e instanceof SyntaxError?'JSON格式不正确，请检查输入。':e.message);}finally{busy=false;render();}
  };
  $('wf-advance').onclick=async()=>{
    if(!run||dirty)return;const expected=editEpoch,id=run.id,revision=run.revision;busy=true;render();
    try{const r=await api(`/api/workflows/${id}/advance`,'POST',{revision});if(expected===editEpoch){run=r;render();message(r.status==='pending'?'本批已保存，可继续下一批。':states[r.status]||r.status);}await refresh();}
    catch(e){message(e.message+'；已保存步骤保留，重新加载任务可查看。');}finally{busy=false;render();}
  };
  async function init(){try{catalog=await api('/api/workflows/catalog');for(const c of catalog){const o=node('option',c.name);o.value=c.id;$('wf-type').append(o);}schema();render();}catch(e){message(e.message);}}
  init();
})();
