"""Build public learning summaries and existing synthetic fixtures. No private inputs."""
from pathlib import Path
import csv,json,hashlib
root=Path(__file__).resolve().parents[1];source=root/'data/synthetic';out=root/'lite/web';out.mkdir(parents=True,exist_ok=True)
data={}
for p in source.glob('*.csv'):
 with p.open(encoding='utf-8-sig') as f:data[p.stem]=list(csv.DictReader(f))
data['calendar']=json.loads((source/'calendar.json').read_text());data['hashes']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in source.glob('*') if p.is_file()}
(out/'fixtures.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')))
rows=[]
for line in (root/'lite/learning.tsv').read_text().splitlines():
 n,page,title,body=line.split('\t',3);key=f'learn-{int(n):03d}'
 rows.append(dict(id=key,doc_id=key,title=title,content=body.replace('\\n','\n'),flow='finance_learning',status='active',version=1,page=int(page),source=f'原创学习提要；对应上传金融学笔记第{page}页起的主题，2022背景，非现行政策',public_summary=True))
flows={'benchmark':'wealth_benchmark','calendar':'issuance','weekly':'weekly_report','onboarding':'onboarding','kep':'kep','feature':'strategy','service':'service','financial':'statements'}
for d in json.loads((source/'documents.json').read_text()):
 if d['status']!='active' or d['topic'] not in flows:continue
 key='sim-'+d['topic'];rows.append(dict(id=key,doc_id=key,title=d['title'],content=(source/d['file']).read_text(),flow=flows[d['topic']],status='active',version=d['version'],page=None,source='项目原有模拟文件／'+d['file'],synthetic=True))
for key,title,flow,body in [('material','发行材料生成与复核','material_fill','先确认标题、产品期限、发行频率和拟成立日，工具用模拟日历生成排期与Word草稿，运营复核后才可处理真实业务。'),('fof','FOF研究工作流（模拟）','fund_research','先确认FOF投资目标、风险预算和基金池，比较底层基金策略、费用、观察区间和风格一致性，并检查集中度与流动性。本页不代表机构研报观点；上传原文后再查询具体研究。'),('date','研究资料的来源和时间','fund_research','研究观点应与机构、日期、样本区间同时读取，不把历史业绩当作未来保证。此处不接实时行情。'),('guide','金枢执行原理','all','浏览器分词、中文双字补充、BM25、标题加权及规则路由。默认无语义Embedding与模型生成；全文可在来源中展开。本地文件和反馈保存在当前浏览器IndexedDB。完整部署使用服务器Mongo、Redis、Milvus及模型。')]:
 rows.append(dict(id='guide-'+key,doc_id='guide-'+key,title=title,flow=flow,content=body,status='active',version=1,page=None,source='项目原创模拟说明',synthetic=True))
(out/'knowledge.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2));print(f'Public summaries:56; total:{len(rows)}')
