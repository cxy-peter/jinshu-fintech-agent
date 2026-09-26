'use strict';
// Personal corpus never enters the shared library or grants enterprise review.
// Reading V7 is read-only; all new writes use a separate, origin-local database.
(() => {
  const worker=new Worker('/assets/personal-worker.mjs',{type:'module'}),jobs=new Map();
  let serial=0,pack=null,ready=false,db=null;
  const by=id=>document.getElementById(id);
  function work(action,body){return new Promise((resolve,reject)=>{const id=++serial;jobs.set(id,{resolve,reject});worker.postMessage({id,action,...body});});}
  worker.onmessage=({data})=>{const job=jobs.get(data.id);if(!job)return;jobs.delete(data.id);data.error?job.reject(Error(data.error)):job.resolve(data.result);};
  worker.onerror=()=>{for(const j of jobs.values())j.reject(Error('个人索引加载失败，请重新导入资料。'));jobs.clear();ready=false;};
  function status(s){by('personal-status').textContent=s;by('personal-chat-status').textContent=s;}
  const documentId=chunk=>chunk.slice(0,chunk.lastIndexOf(':'));
  async function open(){return new Promise((resolve,reject)=>{const q=indexedDB.open('jinshu-personal-v1',1);q.onupgradeneeded=()=>q.result.createObjectStore('packs');q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);});}
  async function read(){return new Promise((resolve,reject)=>{const q=db.transaction('packs').objectStore('packs').get('current');q.onsuccess=()=>resolve(q.result);q.onerror=()=>reject(q.error);});}
  async function write(value){return new Promise((resolve,reject)=>{const t=db.transaction('packs','readwrite');t.objectStore('packs').put(value,'current');t.oncomplete=resolve;t.onerror=()=>reject(t.error);t.onabort=()=>reject(t.error);});}
  function original(id,page){
    const d=(pack?.documents||pack?.docs||[]).find(d=>String(d.id||d.sha256||d.title).slice(0,120)===id);
    if(!d)return notice('当前浏览器没有这份原文，请先导入对应资料包。');
    const pages=d.pages?.length?d.pages:d.chunks.map((c,i)=>({page:c.page||c.metadata?.page||i+1,text:c.content||c.text||''}));
    const dialog=document.createElement('dialog'),heading=text('h2',d.title),select=document.createElement('select'),body=text('pre',''),close=text('button','关闭原文');
    dialog.className='personal-original';
    for(let i=0;i<pages.length;i++){const p=pages[i],o=text('option','原文第'+(p.page||i+1)+'页');o.value=String(i);select.append(o);}
    select.value=String(Math.max(0,pages.findIndex(p=>p.page===page)));
    const draw=()=>{const p=pages[Number(select.value)];body.textContent=typeof p==='string'?p:p.text;};
    select.onchange=draw;close.onclick=()=>dialog.close();dialog.addEventListener('close',()=>dialog.remove());
    dialog.append(heading,select,body,close);document.body.append(dialog);draw();dialog.showModal();
  }
  async function load(value,save=false){
    ready=false;status('正在本机建立资料索引…');
    const summary=await work('load',{pack:value});
    if(save)await write(value);
    pack=value;ready=true;by('use-personal').checked=summary.active>0;
    status(`个人资料 ${summary.documents} 份 · 已启用 ${summary.active} 份 · ${summary.chunks} 个切片 · 本机保存`);
    const list=by('personal-list');list.replaceChildren();
    for(const d of summary.titles){const line=document.createElement('p'),b=text('button',d.title);b.onclick=()=>original(d.id);line.append(b,document.createTextNode(` · ${d.chunks}片 · ${d.status==='active'?'个人参考':'待本地核对'}`));list.append(line);}
    return summary;
  }
  async function legacy(){
    if(!indexedDB.databases)throw Error('浏览器不支持检查旧库；请导入旧工作区备份。');
    if(!(await indexedDB.databases()).some(d=>d.name==='jinshu-lite-v5'))return null;
    return new Promise((resolve,reject)=>{const q=indexedDB.open('jinshu-lite-v5');q.onerror=()=>reject(q.error);q.onsuccess=()=>{const old=q.result;if(!old.objectStoreNames.contains('state')){old.close();return resolve(null);}const r=old.transaction('state','readonly').objectStore('state').get('workspace');r.onsuccess=()=>{old.close();resolve(r.result);};r.onerror=()=>{old.close();reject(r.error);};};});
  }
  by('personal-restore').onclick=async()=>{try{const old=await legacy();if(!old?.docs?.length)throw Error('当前浏览器、当前域名未找到旧资料。其他域名的资料需从原页面导出后导入。');await load(old,true);notice('已恢复旧版个人资料；原工作区未删除，未上传共享库。');}catch(e){notice(e.message);}};
  by('personal-file').onchange=async()=>{
    const file=by('personal-file').files[0];if(!file)return;
    try{if(file.size>100000000)throw Error('资料包最多100MB，请拆分。');await load(JSON.parse(await file.text()),true);notice('资料包已保存到当前浏览器，发送问题时只提交命中的片段。');}
    catch(e){ready=false;status('导入未完成；原本地备份仍保留。');notice(e.message);}
    finally{by('personal-file').value='';}
  };
  by('personal-export').onclick=()=>{if(pack)download(pack,'jinshu-personal-backup.json');else notice('当前没有个人资料。');};
  window.personalBridge={open:(chunk,page)=>original(documentId(chunk),page),search:async query=>{await initialized;if(!by('use-personal').checked)return [];if(!ready)throw Error('个人资料索引尚未就绪，请等待或取消个人资料检索。');return work('search',{query});}};
  by('personal-search').onclick=async()=>{try{await initialized;if(!ready)throw Error('请先载入个人资料。');const q=by('personal-query').value.trim();if(!q)return;const hits=await work('search',{query:q});const out=by('personal-results');out.replaceChildren(text('p',`命中 ${hits.length} 个片段 · 本机检索，未调用 DeepSeek`));for(const h of hits){const article=text('article','','card'),b=text('button',h.title+(h.page?' · 第'+h.page+'页':''));b.onclick=()=>original(documentId(h.chunk_id),h.page);article.append(b,text('pre',h.text));out.append(article);}if(!hits.length)out.append(text('p','当前资料未命中足够相关的正文。不能用不相关的报告或合成示例代替。'));}catch(e){notice(e.message);}};
  const initialized=(async()=>{try{db=await open();const saved=await read();if(saved)await load(saved);else{const old=await legacy();if(old?.docs?.length)await load(old,true);else if(['localhost','127.0.0.1','[::1]'].includes(location.hostname)){const r=await fetch('/api/local-materials',{headers:headers()});if(r.ok)await load(await r.json(),true);else status('未载入个人资料 · 请导入本机资料包');}else status('未载入个人资料 · 在“资料与上传”恢复旧版或导入本机资料包');}}catch(e){status('本地资料不可用：'+e.message);}})();
})();
