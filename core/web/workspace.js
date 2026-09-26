'use strict';
// Additive V10 workspace; preserves the V9 request cancellation and tool revisions.
(() => {
  let workspace=null,current=null,library=[],ops=null,epoch=0;
  const by=id=>document.getElementById(id);
  const el=(tag,value='',cls='')=>text(tag,value,cls);
  const request=(url,data,method='POST')=>api(url,{method,body:JSON.stringify(data)});
  const report=e=>notice(e.message);
  function button(label,action,cls=''){const b=el('button',label,cls);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action();}catch(e){report(e);}finally{b.disabled=false;}};return b;}
  function card(title){const c=el('article','','card');c.append(el('h3',title));return c;}
  function details(label,value){const d=el('details');d.append(el('summary',label),el('pre',typeof value==='string'?value:JSON.stringify(value,null,2)));return d;}
  function pct(n){return n===null||n===undefined?'暂无样本':(n*100).toFixed(1)+'%';}
  async function bootstrap(){
    workspace=await api('/api/workspace/bootstrap');
    by('workspace-account').textContent=workspace.actor?`${workspace.actor.name} · ${workspace.actor.username} · ${workspace.actor.role}`:'资料审核与运营账号 · 点击展开';
    by('ws-logout').hidden=!workspace.actor;
    by('ws-accounts').replaceChildren();
    for(const a of workspace.accounts){by('ws-accounts').append(button(`${a.name}：${a.username} / ${a.password}`,()=>{by('ws-user').value=a.username;by('ws-pass').value=a.password;}));}
    by('conversation-list').replaceChildren();
    for(const c of workspace.conversations.sort((a,b)=>b.updated_at.localeCompare(a.updated_at))){
      const row=el('div','','history-item');row.append(button(c.title,()=>loadConversation(c.id)),button('删除',async()=>{await api('/api/conversations/'+c.id,{method:'DELETE'});if(current?.id===c.id){by('clear-chat').click();}await bootstrap();}));by('conversation-list').append(row);
    }
    if(!workspace.conversations.length)by('conversation-list').append(el('p','保存后的对话显示在这里。','muted'));
    by('architecture-services').replaceChildren();
    const services=[['持久化',workspace.store],['语义 Embedding',workspace.semantic.configured?'CPU BGE-small-zh，首次索引后记录实际结果':'模型权重未准备，当前使用 BM25'],...Object.entries(workspace.optional).map(([k,v])=>[k,v?'已配置，是否调用以 Trace 为准':'未配置 · 可选接入'])];
    for(const [name,status] of services){const row=el('div','','status-row');row.append(el('strong',name),el('span',status));by('architecture-services').append(row);}
    const selected=by('chat-workflow').value;by('chat-workflow').replaceChildren();for(const [value,label] of Object.entries({general:'一般咨询',...workspace.workflows})){const o=el('option',label);o.value=value;by('chat-workflow').append(o);}by('chat-workflow').value=selected;
    renderMemory();
  }
  async function loadConversation(id){
    const token=++epoch;
    generation++;active?.abort();active=null;by('send').disabled=false;by('cancel').hidden=true;
    const row=await api('/api/conversations/'+id);if(token!==epoch)return;
    current=row;history=row.turns.slice(-8).map(t=>({role:t.role,content:t.content.slice(0,1500)}));by('messages').replaceChildren();
    for(const t of row.turns){const n=message(t.role,t.content);if(t.role==='assistant'){renderAnswer({answer:t.content,sources:t.sources,trace_id:t.trace_id,trace:t.trace,verification:t.verification,model_call:t.model_call},n);feedbackForm(n,t.trace_id,row.id);}}
    tab('chat');renderMemory();
  }
  async function libraryLoad(){
    const data=await api('/api/library');library=data.documents;
    by('library-list').replaceChildren(el('h2',`资料版本 · ${library.length}`));
    if(!library.length)by('library-list').append(el('p','还没有可用的共享资料。登录资料编辑后提交，另一账号审核通过才进入问答。'));
    for(const d of library){
      const c=card(d.title),badges=el('p',`${gName(d.department)} · v${d.version} · ${d.status} · ${d.chunks.length}条款 · ID ${d.id}`,'muted');
      c.append(badges,el('p',`索引：${d.embedding}；提交：${d.author}${d.reviewer?'；审核：'+d.reviewer:''}`,'muted'));
      if(d.source_url){const a=el('a','打开原始来源 ↗');a.href=d.source_url;a.target='_blank';a.rel='noopener';c.append(a);}
      c.append(details('正文与切片',d.chunks));
      if(d.status==='pending'&&workspace?.actor?.role==='reviewer'){
        const reason=el('input');reason.placeholder='审核意见（必填）';reason.maxLength=500;
        const label=el('label'),allow=el('input');allow.type='checkbox';label.append(allow,document.createTextNode('允许本演示资料对所有访客可见并发送 DeepSeek'));
        c.append(reason,label,button('确认发布',async()=>{await request(`/api/library/${d.id}/review`,{decision:'approve',reason:reason.value,external_allowed:allow.checked});await libraryLoad();notice('资料已发布，新问题会检索当前版本。');}),button('退回',async()=>{await request(`/api/library/${d.id}/review`,{decision:'reject',reason:reason.value,external_allowed:false});await libraryLoad();}));
      }
      by('library-list').append(c);
    }
  }
  function gName(id){return workspace?.department_options[id]||id;}
  function feedbackForm(node,traceId,conversationId){
    const box=el('details','','feedback-box');box.append(el('summary','这次是否解决？提交问题与上下文复核'));
    const form=el('form'),resolved=el('select'),category=el('select'),note=el('textarea'),target=el('input'),consent=el('input');
    for(const [v,l] of [['yes','已解决'],['no','未解决 / 有误']]){const o=el('option',l);o.value=v;resolved.append(o);}
    for(const [v,l] of [['retrieval','召回遗漏'],['intent','理解或流程错误'],['generation','回答与资料不符'],['knowledge_gap','知识缺口']]){const o=el('option',l);o.value=v;category.append(o);}
    note.placeholder='具体哪里不对，期望怎么改？';note.rows=2;note.maxLength=1000;target.placeholder='正确资料 ID（可选，逗号分隔；用于回放标注）';consent.type='checkbox';
    const label=el('label');label.append(consent,document.createTextNode('将本轮和最近上下文提供给运营复核'));
    const submit=el('button','提交反馈');submit.type='submit';const status=el('p','','muted');status.setAttribute('role','status');
    form.append(resolved,category,note,target,label,submit,status);form.onsubmit=async e=>{e.preventDefault();submit.disabled=true;try{await request('/api/feedback',{conversation_id:conversationId,trace_id:traceId,resolved:resolved.value==='yes',category:category.value,note:note.value,expected_docs:target.value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),share_context:consent.checked});status.textContent='已关联这条回答与上下文。重复提交会更新同一条反馈。';}catch(e){status.textContent=e.message;}finally{submit.disabled=false;}};box.append(form);node.append(box);
  }
  async function opsLoad(){
    ops=await api('/api/operations');by('ops-metrics').replaceChildren();
    for(const [label,value] of [['已保存回答',ops.metrics.answered_turns],['已反馈问题',ops.metrics.feedback_count],['明确解决率',pct(ops.metrics.resolution)],['反馈覆盖率',pct(ops.metrics.feedback_coverage)]]){const c=card(label);c.append(el('strong',String(value),'metric-number'));by('ops-metrics').append(c);}
    by('ops-alerts').replaceChildren(...ops.alerts.map(a=>el('p',a.message,'warning danger')));
    by('feedback-list').replaceChildren();
    if(!ops.feedback.length)by('feedback-list').append(el('p','暂无已授权分享的反馈。请在保存的回答下提交。'));
    for(const f of ops.feedback.slice().reverse()){
      const c=card(f.query);const pick=el('input');pick.type='checkbox';pick.dataset.feedback=f.id;
      const label=el('label');label.append(pick,document.createTextNode(`选为回放样本 · ${f.resolved?'已解决':'未解决'} · ${f.category}`));
      c.append(label,el('p',f.note||'无补充说明'),details('定位原始对话、回答与引用',{context:f.context,sources:f.sources,expected_docs:f.expected_docs}));by('feedback-list').append(c);
    }
    by('skill-list').replaceChildren();
    if(!ops.skills.length)by('skill-list').append(card('暂无候选：先在反馈与策略中选择问题、创建 Skill。'));
    for(const s of ops.skills){const c=card(`Skill ${s.id.slice(0,8)} · ${s.status} · ${s.rollout}%`);c.append(el('p',`top-k=${s.top_k}；扩展词：${s.terms.join('、')||'无'}；结构：${s.template}`),details('回放证据、样本绑定与分组指标',{replay:s.replay,metrics:s.metrics}));
      for(const [action,label] of [['replay','运行回放'],['canary','独立审核 → 5%灰度'],['promote','检查指标并扩量'],['rollback','回滚策略']])c.append(button(label,async()=>{await request('/api/skills/'+s.id,{action});await opsLoad();}));by('skill-list').append(c);}
  }
  async function recordsLoad(){
    await bootstrap();by('records-list').replaceChildren();by('experience-list').replaceChildren();
    const rows=await Promise.all(workspace.conversations.slice(-10).map(c=>api('/api/conversations/'+c.id)));
    for(const row of rows)for(const t of row.turns.filter(t=>t.role==='assistant')){
      const c=card(row.title),stages=el('div','','stage-flow');for(const stage of t.trace)stages.append(el('span',stage.stage));
      c.append(stages,details('完整执行记录',{trace_id:t.trace_id,trace:t.trace,sources:t.sources}),button('打开上下文',()=>loadConversation(row.id)));by('records-list').append(c);
      const ex=card(row.title);ex.append(el('p',`${t.model_call.model} · ${t.model_call.latency_ms}ms · ${t.model_call.usage?.total_tokens??'未返回'} tokens`),el('p',`来源 ${t.sources.length} 条；校验：${t.verification.status}`),details('本轮回答',t.content));by('experience-list').append(ex);
    }
    if(!rows.length){by('records-list').append(card('暂无保存的执行记录'));by('experience-list').append(card('暂无体验记录'));}
  }
  function renderMemory(){
    by('memory-summary').replaceChildren();for(const [title,body] of [
      ['工作记忆','最近8条消息；当前对话使用，其他对话不自动混入。'],
      ['情景记忆',current?`当前：${current.title}；版本 ${current.revision}，可从左侧恢复或删除。`:'请选择或保存一个对话。'],
      ['个人偏好','只保存你同意的语言与回答结构，不从聊天推断敏感画像。'],
      ['组织知识','已独立审核的有效资料及来源版本；未审草稿、过期文档不作为依据。'],
      ['程序记忆','经过回放与审核的 Skill，仅改变检索与回答组织；重要发布始终有人确认。']]){by('memory-summary').append(el('h3',title),el('p',body));}
    const p=current?.preferences||{};by('memory-language').value=p.language||'zh';by('memory-format').value=p.format||'direct';by('memory-consent').checked=!!p.remember;
  }
  window.workspaceBridge={
    chatFields:()=>({use_library:by('use-library').checked,persist:by('persist-chat').checked,conversation_id:current?.id||'',conversation_revision:current?.revision||0,department:by('chat-department').value,workflow:by('chat-workflow').value,reranker:by('chat-reranker').value}),
    async answered(answer,node){
      if(answer.conversation_id){current={...(current||{}),id:answer.conversation_id,revision:answer.conversation_revision,title:current?.title||'当前对话'};feedbackForm(node,answer.trace_id,current.id);try{await bootstrap();}catch(e){report(e);}}
      if(answer.graph)node.append(details('资料版本与引用关系图',answer.graph));
    },
    newChat(){epoch++;current=null;renderMemory();},
    onTab(name){if(name==='library')libraryLoad().catch(report);if(name==='operations'||name==='replay')opsLoad().catch(report);if(name==='records'||name==='experience')recordsLoad().catch(report);if(name==='memory')renderMemory();}
  };
  by('ws-login').onclick=async()=>{try{await request('/api/workspace/login',{username:by('ws-user').value,password:by('ws-pass').value});by('ws-pass').value='';by('ws-auth-message').textContent='登录成功';await bootstrap();await libraryLoad();}catch(e){by('ws-auth-message').textContent=e.message;}};
  by('ws-logout').onclick=async()=>{try{await request('/api/workspace/logout',{});await bootstrap();by('ws-auth-message').textContent='已退出';ops=null;for(const id of ['feedback-list','skill-list','ops-metrics','ops-alerts'])by(id).replaceChildren();await libraryLoad();}catch(e){report(e);}};
  by('library-refresh').onclick=()=>libraryLoad().catch(report);by('ops-refresh').onclick=()=>opsLoad().catch(report);by('replay-refresh').onclick=()=>opsLoad().catch(report);
  by('library-form').onsubmit=async event=>{event.preventDefault();by('lib-submit').disabled=true;try{const data=await request('/api/library',{title:by('lib-title').value,text:by('lib-text').value,topic:by('lib-topic').value,department:by('lib-department').value,version:Number(by('lib-version').value),source_url:by('lib-url').value,effective:by('lib-effective').value,expires:by('lib-expires').value});notice(`已提交 ${data.chunk_count} 条款，索引：${data.embedding}。等待独立审核。`);await libraryLoad();}catch(e){report(e);}finally{by('lib-submit').disabled=false;}};
  by('lib-file').onchange=async()=>{const f=by('lib-file').files[0];if(!f)return;try{let content;if(/\.(pdf|docx)$/i.test(f.name)){if(f.size>65000)throw Error('原生文件解析限65KB，大文件请提取正文。');const bytes=new Uint8Array(await f.arrayBuffer());let binary='';for(const n of bytes)binary+=String.fromCharCode(n);const parsed=await request('/api/library/parse/file',{name:f.name,data:btoa(binary)});content=parsed.text;notice(parsed.notice);}else{if(f.size>80000)throw Error('文本过大，请拆分。');content=await f.text();}if(content.length>20000)throw Error('最多20000字，请拆分。');by('lib-title').value=f.name;by('lib-text').value=content;}catch(e){report(e);}finally{by('lib-file').value='';}};
  by('lib-example').onclick=()=>{by('lib-title').value='发行排期复核示例（合成）';by('lib-topic').value='synthetic-issuance';by('lib-department').value='dept_release';by('lib-text').value='# 发行排期复核示例\n以下为项目合成演示，不是真实机构制度。\n第一条 发行排期需要提供募集开始日、产品期限、周或双周发行频率与节假日日历。\n第二条 募集结束日或成立日遇到非交易日时，应依据已确认的产品条款与日历顺延；不能仅凭模型知识确认实际成立日。\n第三条 生成募集、成立和到期日期后，标记冲突与差异，由业务人员复核。输入有修改时原结果与导出确认立即失效。\n第四条 本工具只生成材料预览，不向真实系统报送。';};
  by('skill-form').onsubmit=async e=>{e.preventDefault();try{const ids=[...document.querySelectorAll('[data-feedback]:checked')].map(x=>x.dataset.feedback);await request('/api/skills',{feedback_ids:ids,terms:by('skill-terms').value.split(/[,，]/).map(s=>s.trim()).filter(Boolean),top_k:Number(by('skill-topk').value),template:by('skill-template').value});await opsLoad();tab('replay');}catch(e){report(e);}};
  by('memory-form').onsubmit=async e=>{e.preventDefault();if(!current){notice('请先保存一个对话。');return;}try{current.preferences=await request('/api/conversations/'+current.id+'/preferences',{language:by('memory-language').value,format:by('memory-format').value,remember:by('memory-consent').checked});notice('偏好已更新。');}catch(e){report(e);}};
  bootstrap().then(()=>{for(const [id,name] of Object.entries(workspace.department_options)){const o=el('option',name);o.value=id;by('lib-department').append(o);}}).catch(e=>{by('use-library').checked=false;by('persist-chat').checked=false;by('workspace-account').textContent='持久化暂不可用 · 临时问答仍可用';report(e);});
})();
