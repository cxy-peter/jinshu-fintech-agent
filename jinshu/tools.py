"""Deterministic read-only adapters; based on user's existing financial workflow patterns."""
from __future__ import annotations
import csv,hashlib,json,statistics,re
from datetime import date,timedelta
from decimal import Decimal as D,InvalidOperation
from .fixtures import DATA

def rows(name):
 with (DATA/name).open(encoding='utf-8-sig',newline='') as f:return list(csv.DictReader(f))
def number(x,percent=False):
 if x is None or str(x).strip() in {'','--','-','N/A'}:return None
 raw=str(x).strip()
 grouped='-'+raw[1:-1] if raw.startswith('(') and raw.endswith(')') else raw
 if ',' in raw and not re.fullmatch(r'[+-]?\d{1,3}(,\d{3})+(\.\d+)?%?',grouped):raise ValueError('千分位分组不合法')
 text=raw.replace(',','')
 if text.startswith('(') and text.endswith(')'):text='-'+text[1:-1]
 if text.endswith('%'):
  if not percent:raise ValueError('百分数不能当金额')
  text=text[:-1];scale=D(100)
 else:scale=D(1)
 try:n=D(text)/scale
 except InvalidOperation as exc:raise ValueError('不是可解析的数值') from exc
 if not n.is_finite():raise ValueError('禁止非有限数')
 return n

def wealth_benchmark(p):
 catalog=rows('products.csv');target=next((r for r in catalog if r['产品编码']==p.get('product','SIM0001')),None)
 if not target:raise ValueError('产品未找到')
 peers=[r for r in catalog if all(r[k]==target[k] for k in ['投资性质','运作模式','风险等级','持有期限','代销渠道','币种'])]
 if len(peers)<2:raise ValueError('可比样本不足')
 series=rows('nav.csv');out=[]
 start=p.get('start','2026-06-01');end=p.get('end','2026-08-30')
 if start>=end:raise ValueError('观察日期倒置')
 for prod in peers:
  a=sorted([r for r in series if r['产品编码']==prod['产品编码'] and start<=r['净值日期']<=end],key=lambda r:r['净值日期'])
  if not a or a[0]['净值日期']!=start or a[-1]['净值日期']!=end:raise ValueError('缺少共同起止日期数据')
  if len({r['净值日期'] for r in a})!=len(a):raise ValueError('净值主键重复')
  vals=[number(r['累计净值']) for r in a]
  if any(v is None or v<=0 for v in vals):raise ValueError('净值缺失或非正')
  peak=vals[0];dd=D(0)
  for v in vals:peak=max(v,peak);dd=max(dd,1-v/peak)
  out.append({'产品编码':prod['产品编码'],'产品全称':prod['产品全称'],'区间收益率':str(vals[-1]/vals[0]-1),'最大回撤':str(dd),'起始日':start,'截止日':end})
 vals=[D(r['区间收益率']) for r in out];tr=next(D(r['区间收益率']) for r in out if r['产品编码']==target['产品编码'])
 return {'rows':out,'summary':{'同口径样本数':len(out),'样本收益中位数':str(statistics.median(vals)),'严格低于目标的样本比例':sum(v<tr for v in vals)/len(vals)},'note':'合成净值无分红；不是全市场排名或投资建议'}

def issuance(p):
 cfg=json.loads((DATA/'calendar.json').read_text());holidays=set(cfg['holidays']);start=date.fromisoformat(p.get('start','2026-09-25'));term=int(p.get('term_days',90));freq=int(p.get('frequency_days',7));count=int(p.get('count',3))
 if term<1 or term>3650 or freq not in [7,14] or not 1<=count<=20:raise ValueError('排期参数超出允许范围')
 def valid(d):return d.weekday()<5 and str(d) not in holidays
 def advance(d):
  while not valid(d):d+=timedelta(days=1)
  return d
 out=[]
 for i in range(count):
  planned=start+timedelta(days=i*freq);actual=advance(planned);close=actual-timedelta(days=1)
  while not valid(close):close-=timedelta(days=1)
  maturity=advance(actual+timedelta(days=term))
  out.append({'批次':i+1,'拟成立日':str(planned),'成立日':str(actual),'募集结束日':str(close),'到期日':str(maturity),'实际自然日':(maturity-actual).days,'顺延':actual!=planned,'日历版本':cfg['version']})
 return {'rows':out,'material_preview':{'标题':'模拟产品发行材料草稿','约定期限自然日':term,'发行频率天':freq,'日历版本':cfg['version'],'需人工确认':['产品要素','日历适用市场','顺延日期','募集与成立时点']},'note':'根据模拟日历计算。所有结果为待核对排期草案，不是发行决定'}

def weekly_report(p):
 out=[];issues=[];seen=set()
 for i,r in enumerate(p.get('rows',rows('weekly_raw.csv')),2):
  if not isinstance(r.get('登记编码'),str):raise ValueError('登记编码必须为字符串，不能猜测前导零')
  key=(r['登记编码'],r['数据日期'])
  if key in seen:raise ValueError('登记编码/日期重复')
  seen.add(key);rate=number(r['区间收益率'],True)
  if rate is None:issues.append({'源行':i,'字段':'区间收益率','状态':'缺失保留，需补充'})
  out.append({'登记编码':r['登记编码'],'名称':r['名称'],'规模万元':str(number(r['规模万元'])) if number(r['规模万元']) is not None else None,'区间收益率':str(rate) if rate is not None else None,'数据日期':r['数据日期'],'源行':i})
 return {'rows':out,'issues':issues,'note':'登记编码保留前导零，输入不覆盖；模拟周报'}

def onboarding(p):
 stage=int(p.get('decision_stage',1))
 if stage not in [1,2,3,4]:raise ValueError('未知流程节点')
 result=[r|{'available_now':int(r['available_stage'])<=stage,'待确认':'可评估用途与授权' if int(r['available_stage'])<=stage else '本时点尚未采集，不允许使用未来信息'} for r in rows('onboarding.csv')]
 return {'rows':result,'decision_stage':stage,'note':'模拟时序不是公司现行KYC或监管要求；仅输出需求澄清，不决定风险等级'}

def kep(p):
 normalize=lambda s:s.strip().replace('/','-')
 mails=rows('mails.csv');out=[]
 for c in rows('cases.csv'):
  found=[m for m in mails if normalize(m['case_no'])==normalize(c['case_no'])]
  via='case_no'
  if not found:found=[m for m in mails if c['reference_no'] and m['reference_no']==c['reference_no']];via='reference_no'
  status='found_sent_record' if len(found)==1 else 'ambiguous' if len(found)>1 else 'not_found_needs_review'
  out.append({'case_id':c['case_id'],'status':status,'match_key':via,'evidence_ids':[m['message_id'] for m in found],'delivery':found[0]['delivery'] if len(found)==1 else 'unconfirmed'})
 return {'rows':out,'note':'未找到不等于漏回复，发送不等于送达；只处理模拟表，不发邮件'}

def strategy(p):
 feature=p.get('feature','successful_deposit_count_7d');event=p.get('event','FiatDeposit');r=next((x for x in rows('features.csv') if x['name']==feature),None)
 if not r or r['event']!=event:raise ValueError('未登记特征或事件不匹配')
 if not 1<=int(p.get('threshold',5))<=1000000:raise ValueError('候选阈值超出允许范围')
 return {'rows':[r],'candidate':{'event':event,'feature':feature,'operator':'>=','threshold':int(p.get('threshold',5)),'status':'disabled','approval':'required'},'note':'候选不连接策略平台；状态过滤和去重分别验证；T+1不是实时'}

def statements(p):
 year=str(p.get('year',2025));r=next((x for x in rows('statements.csv') if x['year']==year),None)
 if not r:raise ValueError('未取得这个年度的模拟数据')
 v={k:number(x) for k,x in r.items() if k not in ['year','unit','scope','synthetic']}
 missing=[k for k in ['assets','liabilities','equity','cfo','cfi','cff','fx','net_cash_change','opening_cash','ending_cash'] if v.get(k) is None]
 if missing:return {'rows':[r],'checks':None,'passed':False,'status':'incomplete_needs_review','missing_fields':missing,'note':'必需数据缺失，不按0计算'}
 checks={'资产负债':v['assets']-v['liabilities']-v['equity'],'现金净变动':v['net_cash_change']-v['cfo']-v['cfi']-v['cff']-v['fx'],'期末现金':v['ending_cash']-v['opening_cash']-v['net_cash_change']}
 return {'rows':[r],'checks':{k:str(x) for k,x in checks.items()},'passed':all(x==0 for x in checks.values()),'note':'全部模拟金额，不做真实公司财报判断'}

TOOLS={f.__name__:f for f in [wealth_benchmark,issuance,weekly_report,onboarding,kep,strategy,statements]}
FILES={'wealth_benchmark':['products.csv','nav.csv'],'issuance':['calendar.json'],'weekly_report':['weekly_raw.csv'],'onboarding':['onboarding.csv'],'kep':['cases.csv','mails.csv'],'strategy':['features.csv'],'statements':['statements.csv']}
def run(tool,p=None):
 if tool not in TOOLS:raise ValueError('工具不在白名单')
 result=TOOLS[tool](p or {})
 return {'tool':tool,'synthetic':True,'result':result,'source_files':[{'file':n,'sha256':hashlib.sha256((DATA/n).read_bytes()).hexdigest()} for n in FILES[tool]]}

def material_fill(p):
 from .python_skills import material_fill as impl
 return impl(p)
TOOLS['material_fill']=material_fill
FILES['material_fill']=['calendar.json']
