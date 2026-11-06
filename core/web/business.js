'use strict';
(() => {
  const by=id=>document.getElementById(id);
  function launch(suggestion,workflow=false){
    if(workflow){window.workflowBridge?.prefill(suggestion.tool,suggestion.values||suggestion.prefill||{}).then(()=>tab('workflows')).catch(e=>notice(e.message));return;}
    if(![...by('tool-select').options].some(o=>o.value===suggestion.tool)){notice('业务目录尚未载入，请稍后重试。');return;}
    by('tool-select').value=suggestion.tool;by('tool-select').onchange();
    by('tool-values').value=JSON.stringify(suggestion.values||suggestion.prefill||{},null,2);by('tool-values').oninput();
    tab('tools');notice('已定位业务工具并填入问题中的明确参数。请补齐数据并复核；尚未计算，也未发送任何业务消息。');
  }
  function renderSuggestions(node,rows){
    if(!rows?.length)return;
    const box=text('div','','business-suggestions');box.append(text('h3','可继续使用的业务工具'));
    for(const s of rows){const card=text('div','','card');card.append(text('strong',s.name));
      if(s.missing_fields?.length)card.append(text('p','待补参数：'+s.missing_fields.join('、'),'muted'));
      card.append(text('p','输入数据：'+(s.source_files||[]).join('、'),'muted'));
      const controls=text('div','','document-actions');
      for(const [label,workflow] of [['打开业务计算',false],['创建可恢复任务',true]]){const b=text('button',label);b.type='button';b.onclick=()=>launch(s,workflow);controls.append(b);}card.append(controls);box.append(card);
    }node.append(box);
  }
  for(const b of document.querySelectorAll('[data-issuance-demo]'))b.onclick=async()=>{b.disabled=true;try{const d=await api('/api/business-capabilities/issuance/demo');await window.workflowBridge.prefill(d.workflow,d.values,d.sources);tab('workflows');notice(d.notice);}catch(e){notice(e.message);}finally{b.disabled=false;}};
  by('load-cn-calendar').onclick=async()=>{try{if(!['issuance','material_fill'].includes(by('tool-select').value))throw Error('请先选择发行排期或发行材料工具。');const calendar=await api('/api/calendars/cn/2026'),sources=JSON.parse(by('tool-sources').value||'{}');sources['calendar.json']=calendar;by('tool-sources').value=JSON.stringify(sources,null,2);by('tool-examples').checked=false;invalidateTool();notice(calendar.notice);}catch(e){notice(e.message);}};
  by('wf-cn-calendar').onclick=async()=>{try{await window.workflowBridge.calendar(await api('/api/calendars/cn/2026'));}catch(e){notice(e.message);}};
  window.businessBridge={renderSuggestions};
  (async()=>{try{const d=await api('/api/business-capabilities'),root=by('business-capability-list');
    for(const c of d.capabilities){const item=document.createElement('details');item.append(text('summary',c.name),text('p',c.scenario));
      const queries=c.examples||[];if(queries.length){const buttons=text('div','','document-actions');for(const q of queries){const b=text('button',typeof q==='string'?q:q.query);b.type='button';b.onclick=()=>{tab('chat');by('query').value=typeof q==='string'?q:q.query;by('query').focus();};buttons.append(b);}item.append(buttons);}
      item.append(text('p','数据文件：'+(c.source_files||[]).join('、'),'muted'));for(const boundary of c.boundaries||[])item.append(text('p',boundary,'muted'));root.append(item);
    }
  }catch(e){by('business-capability-list').textContent=e.message;}})();
})();
