"""Idempotent V5 -> V6 source migration. Original engine/ and source corpus are untouched."""
from pathlib import Path
import runpy
root=Path(__file__).resolve().parents[1]
p=root/'lite/web/app.mjs';s=p.read_text()
if "from './assurance.mjs'" not in s:
 old='FLOWS,Index,route,answerQuestion,propose';assert old in s
 s=s.replace(old,'FLOWS,Index,propose');s="import {route,answerQuestion} from './assurance.mjs';\n"+s
if 'evidence-reference' not in s:
 needle="const steps=E('div',undefined,'steps');";assert needle in s
 added="""if(a.references?.length){const refs=E('div');refs.className='reference-panel';for(const ref of a.references){const box=E('div',undefined,'source evidence-reference');box.dataset.chunkId=ref.chunk_id;box.append(E('h3',`【来源${ref.id}】${ref.document_title} · ${ref.title}`),E('p',ref.source+(ref.page?' · 第'+ref.page+'页':'')+' · 版本'+ref.version,'muted'),E('blockquote',ref.quote,'answer original-quote'),E('small',ref.provenance_note),button('打开对应原文',()=>showDocument(ref.doc_id,ref.page)));refs.append(box);}p.append(details('参考文献与原文摘录（逐字可核对）',refs));p.lastChild.open=true;}
 """
 s=s.replace(needle,added+needle)
if 'p100=panel' not in s:
 needle='function showEval(){';assert needle in s
 added="""function showEval(){const p100=panel('100题：路由、依据和引用联合验收'),out100=E('div');p100.append(E('p','56概念题、20改写题、16业务题、2追问、2多源题、4无依据题。运行公开资料；这是开发验收，不是独立盲测。','warning'),button('运行100题带出处验收',async b=>{b.disabled=true;try{const {evaluate}=await import('./benchmarking.mjs');const response=await fetch('benchmark100.json');if(!response.ok)throw Error('评测标签尚未随构建部署');const result=evaluate(await response.json(),seed);out100.replaceChildren(jpre(result.summary),table(result.rows.map(r=>({题号:r.id,问题:r.question,通过:r.pass,路由:r.route,召回:r.retrieved_ids.join('、'),关键点覆盖:r.key_coverage,原文逐字校验:r.quote_verified}))),button('导出100题答案、原文与出处',()=>downloadBlob(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}),'jinshu-100-actual-result.json')));}finally{b.disabled=false}},'primary'),out100);wrap.append(p100);
"""
 s=s.replace(needle,added)
s=s.replace('成功部署后才有自己的vercel.app地址。','本项目实际体验地址为 https://jinshu-workbench.vercel.app；原工程与网站发布仓库分别维护。')
p.write_text(s)
p=root/'lite/web/index.html';p.write_text(p.read_text().replace('LITE / V5','LITE / V6'))
p=root/'lite/build.mjs';s=p.read_text().replace("version:'5.0.0'","version:'6.0.0',commit:process.env.VERCEL_GIT_COMMIT_SHA||process.env.GITHUB_SHA||'local'");p.write_text(s)
p=root/'lite/web/style.css';s=p.read_text()
if '.original-quote{' not in s:s+='\n.original-quote{margin:10px 0;padding:10px 14px;border-left:3px solid #b6c9b8;background:#f4f7f1;font-size:13px;line-height:1.85}.reference-panel{max-width:100%;overflow-wrap:anywhere}\n'
p.write_text(s)
for name in ['01_architecture.svg','03_loop.svg']:
 p=root/'diagrams'/name;p.write_text(p.read_text().replace('scale(1.81 1.81)','scale(1 1)'))
runpy.run_path(str(root/'scripts/make_benchmark_v6.py'),run_name='__main__')
print('V6 source migration complete; original engine and corpus preserved.')
