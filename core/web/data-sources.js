'use strict';
(() => {
  const by=id=>document.getElementById(id);
  const post=(url,body={})=>api(url,{method:'POST',body:JSON.stringify(body)});
  const button=(label,action)=>{const b=text('button',label);b.type='button';b.onclick=async()=>{b.disabled=true;try{await action();}catch(e){notice(e.message);}finally{b.disabled=false;}};return b;};
  let cloudReady=false,localReady=false;
  async function refresh(){
    await window.workspaceReady;
    const result=await api('/api/private-library');cloudReady=true;
    by('private-chat-status').textContent=`我的云端资料 ${result.documents.length} 份 · 当前浏览器专属`;
    by('cloud-list').replaceChildren();
    for(const d of result.documents){const line=text('article','','doc-item'),open=button(d.title,()=>openSource({origin:'private_cloud',doc_id:d.id,page:1}));
      line.append(open,text('span',`${d.pages} ${d.location_kind==='logical_text_section'?'文本段':'页'} · ${d.characters.toLocaleString()}字`),button('移出检索',async()=>{await api('/api/private-library/'+encodeURIComponent(d.id),{method:'DELETE'});await refresh();}));
      by('cloud-list').append(line);
    }
    if(!result.documents.length)by('cloud-list').append(text('p','还没有云端个人资料。上传后会自动进入问答检索范围。','muted'));
  }
  async function upload(file){
    if(file.size>12000000)throw Error(file.name+' 超过12MB，请拆分。');
    const bytes=new Uint8Array(await file.arrayBuffer());
    const digest=await crypto.subtle.digest('SHA-256',bytes);
    const sha=[...new Uint8Array(digest)].map(x=>x.toString(16).padStart(2,'0')).join('');
    const row=await post('/api/private-library/uploads',{name:file.name,sha256:sha,size:bytes.length});
    if(row.existing)return {document:row.existing,deduplicated:true};
    let next=0,completed=0;
    async function worker(){while(next<row.parts){const n=next++,part=bytes.slice(n*row.part_size,(n+1)*row.part_size);let binary='';for(const b of part)binary+=String.fromCharCode(b);
      await api(`/api/private-library/uploads/${row.id}/parts/${n}`,{method:'PUT',body:JSON.stringify({data:btoa(binary)})});
      by('cloud-status').textContent=`上传 ${file.name}：${++completed}/${row.parts}，之后一次性解析建立索引。`;
    }}
    await Promise.all(Array.from({length:Math.min(4,row.parts)},worker));
    by('cloud-status').textContent=`正在解析 ${file.name} 并建立页码索引…`;
    return post(`/api/private-library/uploads/${row.id}/finish`);
  }
  async function filesChanged(input){
    input.disabled=true;let ok=0,duplicate=0;const failures=[];
    try{await window.workspaceReady;const selected=[...input.files],files=selected.filter(f=>/\.(pdf|docx|txt|md|csv|json)$/i.test(f.name));
      if(files.length>25)throw Error('一次最多25份支持的文件，请选择更小的资料文件夹。');
      for(const f of files){try{const r=await upload(f);r.deduplicated?duplicate++:ok++;}catch(e){failures.push(f.name+'：'+e.message);}}
      by('cloud-status').textContent=`新导入 ${ok} 份，跳过重复 ${duplicate} 份，其他格式 ${selected.length-files.length} 份。${failures.length?'未完成：'+failures.join('；'):'索引已保存，可直接提问。'}`;await refresh();
    }catch(e){notice(e.message);}finally{input.disabled=false;input.value='';}
  }
  for(const id of ['cloud-files','cloud-folder'])by(id).onchange=()=>filesChanged(by(id));
  by('cloud-refresh').onclick=()=>refresh().catch(e=>notice(e.message));
  by('cloud-handoff').onclick=async()=>{try{const d=await post('/api/private-library/handoff');const box=by('cloud-handoff-result');box.replaceChildren(text('p','24小时内一次有效。另一个浏览器认领后，资料访问权转移；不要公开链接。'));const a=document.createElement('a');a.href=location.origin+'/#library='+encodeURIComponent(d.token);a.textContent='在目标浏览器打开此资料认领链接';box.append(a);}catch(e){notice(e.message);}};
  async function openSource(source){
    const base=source.origin==='local_folder'?'/api/local-folder/documents/':'/api/private-library/';
    const d=await api(base+encodeURIComponent(source.doc_id)+'/page/'+(source.page||1));
    document.getElementById('private-reader')?.remove();
    const dialog=text('dialog','','reference-reader');dialog.id='private-reader';const select=document.createElement('select');
    for(const page of d.pages){const o=text('option',d.location_kind==='logical_text_section'?'文本段 '+page:'PDF第 '+page+' 页');o.value=String(page);select.append(o);}select.value=String(d.page);
    const body=text('pre',d.text,'reference-page');select.onchange=async()=>{try{const p=await api(base+encodeURIComponent(source.doc_id)+'/page/'+select.value);body.textContent=p.text;}catch(e){notice(e.message);}};
    dialog.append(text('h2',d.title),text('p','这是提取原文；表格及图片请对照原文件。','muted'),select,body);
    if(source.origin==='private_cloud'&&d.original_available)dialog.append(button('下载原文件',async()=>{const r=await fetch(base+encodeURIComponent(source.doc_id)+'/original',{headers:headers(),cache:'no-store'});if(!r.ok)throw Error('原文件读取失败');const blob=await r.blob(),a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=d.title;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}));
    dialog.append(button('关闭',()=>dialog.close()));dialog.addEventListener('close',()=>dialog.remove());document.body.append(dialog);dialog.showModal();
  }
  window.dataSources={openSource,refresh,chatFields:()=>({use_private_library:cloudReady&&by('use-private-cloud').checked,use_local_folder:localReady&&by('use-local-folder').checked,answer_mode:by('answer-mode').value})};
  by('search-only').onclick=async()=>{
    const query=by('query').value.trim();if(!query){notice('先输入要检索的问题。');return;}
    by('search-only').disabled=true;
    try{await window.workspaceReady;const payload={...(window.workspaceBridge?.chatFields()||{}),...window.dataSources.chatFields(),query,history:history.slice(-8),documents:documents.map(d=>({...d})),include_examples:by('include-examples').checked,persist:false,consent:false};
      payload.personal_passages=await window.personalBridge?.search(query,history)||[];
      const start=performance.now(),r=await post('/api/retrieve',payload),node=message('assistant',`找到 ${r.sources.length} 个片段 · 服务器检索 ${r.diagnostics.elapsed_ms}ms · 本次浏览器往返 ${Math.round(performance.now()-start)}ms · 未调用模型`);
      for(const s of r.sources){node.append(text('h3',s.title+(s.page?' · '+sourceLocation(s):'')),text('blockquote',s.text));if(['private_cloud','local_folder'].includes(s.origin))node.append(button('查看提取原文',()=>openSource(s)));else if(s.origin==='shared_reference')node.append(button('查看原文',()=>window.workspaceBridge.openReference(s.doc_id,s.page)));}
      window.businessBridge?.renderSuggestions(node,r.business_suggestions);
      if(!r.sources.length)node.append(text('p','请检查已选择的资料范围和登录状态；没有命中不能证明文件中没有该知识。'));
    }catch(e){notice(e.message);}finally{by('search-only').disabled=false;}
  };
  window.addEventListener('jinshu:workspace-ready',({detail:w})=>{
    const a=w.accounts.find(a=>a.role==='operator');by('shared-quick-login').hidden=!!w.actor||!a||!w.shared_reference_count;
    by('shared-quick-login').onclick=async()=>{try{await post('/api/workspace/login',{username:a.username,password:a.password});await window.workspaceBridge.refresh();notice('已登录学习资料阅读角色，已有资料会参与下一次检索。');}catch(e){notice(e.message);}};
  });
  function localStatus(d){
    const changes=d.scan?`本次新增 ${d.scan.added}、修改 ${d.scan.changed}、未变化 ${d.scan.unchanged}、移出 ${d.scan.removed}、解析失败 ${d.scan.errors}。`:'';
    by('folder-status').textContent=`已连接 ${d.root||'待设置目录'} · 已索引 ${d.indexed_documents||0} 份。${changes}`;
    let list=by('folder-list');if(!list){list=text('div','');list.id='folder-list';by('folder-local-controls').append(list);}list.replaceChildren();
    for(const doc of d.documents||[]){const line=text('div','','doc-item');line.append(text('span',doc.relative_path));if(doc.status==='indexed')line.append(button('查看提取原文',()=>openSource({origin:'local_folder',doc_id:doc.id,page:1})));else line.append(text('span',doc.error,'warning'));list.append(line);}
    for(const skip of d.skipped||[])list.append(text('p',skip.path+'：'+skip.reason,'muted'));
  }
  async function local(){
    if(!['localhost','127.0.0.1','[::1]'].includes(location.hostname))return;
    try{const d=await api('/api/local-folder');localReady=true;by('folder-local-controls').hidden=false;by('local-folder-toggle').hidden=false;by('folder-root').value=d.root||d.path||'';by('use-local-folder').checked=true;localStatus(d);}
    catch{by('folder-description').textContent='本机文件夹服务尚未连接。请使用 START_LOCAL_FOLDER.bat 启动同一工作台。';}
  }
  by('folder-save').onclick=async()=>{try{const d=await post('/api/local-folder/config',{root:by('folder-root').value});localStatus(d);}catch(e){notice(e.message);}};
  by('folder-scan').onclick=async()=>{by('folder-scan').disabled=true;try{by('folder-status').textContent='正在扫描变化并建立索引…';const d=await post('/api/local-folder/scan');localStatus(d);}catch(e){notice(e.message);}finally{by('folder-scan').disabled=false;}};
  let claiming=false;
  async function claimFromHash(){
    if(claiming)return;
    const token=new URLSearchParams(location.hash.slice(1)).get('library');if(!token)return;
    claiming=true;window.history.replaceState(null,'',location.pathname+location.search);
    try{await window.workspaceReady;const d=await post('/api/private-library/claim',{token});tab('library');notice(`已认领 ${d.claimed} 份个人资料，可直接提问。`);await refresh();}
    catch(e){tab('library');by('cloud-status').textContent=e.message;notice(e.message);}
    finally{claiming=false;}
  }
  window.addEventListener('hashchange',()=>claimFromHash());
  window.dataSources.ready=(async()=>{try{await window.workspaceReady;await claimFromHash();await refresh();await local();}catch(e){by('cloud-status').textContent=e.message;}})();
})();
