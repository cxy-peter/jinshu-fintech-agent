"""Add service mode and real-pilot entry without rewriting the V3 visual template."""
from fastapi.responses import HTMLResponse
from . import ROOT

ADDON=r'''<script>
(()=>{
let serverMode=false;
const existing=$('login-name'), list=document.createElement('datalist');list.id='v4-users';
for(const option of existing.options){const o=document.createElement('option');o.value=option.value;o.label=option.text;list.append(o)}
const input=document.createElement('input');input.id='login-name';input.value=existing.value;input.setAttribute('list','v4-users');input.placeholder='服务器上创建的用户名';existing.replaceWith(input);document.body.append(list);
input.onchange=()=>{if(!serverMode)$('password').value='demo-'+input.value};
examples.fund_research='根据上传研报，FOF选择基金时应当关注哪些维度？请区分材料年份。';
examples.finance_learning='根据上传的金融学学习笔记，支付中介的含义是什么？';
document.querySelector('header .pill').textContent='离线展示 / 私有服务 · 两套模式';
const panel=E('section');panel.id='v4';panel.innerHTML=`<div class="panel"><h2>真实服务与执行模式</h2><p>状态检查不调用生成模型；模型是否实际参与，请查看任务 Trace 中的 model_calls 和 answer_mode。</p><button id="v4-refresh">读取当前服务状态</button><pre id="v4-status">登录后可查看。离线模式不会伪装数据库和模型调用。</pre></div><div class="panel"><h2>用户试点记录</h2><p class="small">这里是参与者真实填写的记录入口，不是预置的成功案例。默认标记为测试数据；同意参与后才能提交。人工正确性应由另外的评审复核。</p><div class="inline-inputs"><input id="v4-task" value="task-01" aria-label="任务编号"><select id="v4-phase"><option value="manual">人工查找基线</option><option value="agent">Agent辅助</option></select><input type="number" id="v4-seconds" min="1" placeholder="实际耗时（秒）"><select id="v4-rating"><option>3</option><option>4</option><option>5</option><option>2</option><option>1</option></select></div><div class="inline-inputs"><label><input type="checkbox" id="v4-done">任务完成</label><label><input type="checkbox" id="v4-test" checked>测试数据，不计作真人试点</label><label><input type="checkbox" id="v4-consent">同意记录本次任务反馈</label></div><textarea id="v4-note" placeholder="反馈，不要填写客户身份、银行账户或其他敏感内容"></textarea><button id="v4-submit" class="primary">提交本次实际记录</button> <button id="v4-withdraw">撤回同意并删除我的记录</button><pre id="v4-result"></pre></div>`;
document.querySelector('.tabs').append(panel);const nav=E('button','服务与试点');nav.dataset.tab='v4';nav.onclick=()=>tab('v4');document.querySelector('nav').append(nav);
async function refresh(){try{$('v4-status').textContent=JSON.stringify(await api('services'),null,2)}catch(e){$('v4-status').textContent=e.message}}
$('v4-refresh').onclick=refresh;
const login=$('login').onclick;$('login').onclick=async()=>{await login();if(!cat)return;const live=cat.profile==='services';$('mode').textContent=live?'私有服务模式：使用服务器账号；模型参与及回退状态以实际执行记录为准。':'离线模式：hash测试向量与原文摘录，保留可演示工作流。';document.querySelector('#loop .warning').textContent='自进化只改执行策略，不改模型权重。离线实验、真实服务联调与真实用户效果是三类不同证据。';await refresh()};
const run=$('run').onclick;$('run').onclick=async()=>{await run();if(last){const state=last.execution||{};const details=E('details');details.append(E('summary','模型调用与最终输出模式'));details.append(E('pre',JSON.stringify({answer_mode:state.answer_mode,attempted_answer_mode:state.attempted_answer_mode,model_calls:state.model_calls||[]},null,2)));$('execution').append(details)}};
$('v4-submit').onclick=async()=>{try{if(!$('v4-consent').checked)throw Error('请先阅读并确认同意');await api('pilot/consent','POST',{consent:true});const phase=$('v4-phase').value;const j=await api('pilot/result','POST',{task_id:$('v4-task').value,phase,trace_id:phase==='agent'?last?.trace_id:null,seconds:Number($('v4-seconds').value),completed:$('v4-done').checked,rating:Number($('v4-rating').value),note:$('v4-note').value,is_test:$('v4-test').checked});$('v4-result').textContent=JSON.stringify(j,null,2)}catch(e){$('v4-result').textContent=e.message}};
$('v4-withdraw').onclick=async()=>{try{$('v4-result').textContent=JSON.stringify(await api('pilot/withdraw','POST'),null,2)}catch(e){$('v4-result').textContent=e.message}};
fetch('/health').then(r=>r.json()).then(h=>{if(h.profile==='services'){serverMode=true;input.value='';$('password').value='';$('password').placeholder='服务器账户密码';$('mode').textContent='私有服务模式：请先在服务器创建用户，演示口令不会自动生效。'}}).catch(()=>{});
})();
</script>'''

def install_ui(app):
    app.router.routes=[r for r in app.router.routes if getattr(r,'path',None)!='/']
    @app.get('/',response_class=HTMLResponse)
    def workbench():
        text=(ROOT/'static'/'index.html').read_text(encoding='utf-8')
        return text.replace('</body>',ADDON+'</body>')
