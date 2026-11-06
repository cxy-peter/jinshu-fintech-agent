"""Deterministic read-only adapters; based on user's existing financial workflow patterns."""
from __future__ import annotations
import csv,hashlib,json,statistics,re
from datetime import date,timedelta
from decimal import Decimal as D,InvalidOperation
from .fixtures import DATA
from contextvars import ContextVar
INPUT_SOURCES=ContextVar("jinshu_input_sources",default=None)

def source(name):
 values=INPUT_SOURCES.get()
 if values is not None:
  if name not in values:raise ValueError("缺少本次输入资料："+name)
  return values[name]
 if name.endswith(".json"):return json.loads((DATA/name).read_text(encoding="utf-8-sig"))
 with (DATA/name).open(encoding="utf-8-sig",newline="") as f:return list(csv.DictReader(f))

def rows(name):return source(name)
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
 """Apply an explicit calendar policy, not a model-invented trading calendar."""
 cfg=source('calendar.json')
 if not isinstance(cfg,dict) or not cfg.get('version'):
  raise ValueError('日历必须有版本')
 def dates(name):
  raw=cfg.get(name,[])
  if not isinstance(raw,list) or len(raw)>5000:
   raise ValueError('日历日期列表无效')
  return {date.fromisoformat(x) for x in raw}
 holidays=dates('holidays');workdays=dates('workdays')
 if holidays & workdays:raise ValueError('同一天不能同时为休息日和指定工作日')
 lower=date.fromisoformat(cfg['coverage_start']) if cfg.get('coverage_start') else None
 upper=date.fromisoformat(cfg['coverage_end']) if cfg.get('coverage_end') else None
 if bool(lower)!=bool(upper) or lower and lower>upper:
  raise ValueError('日历覆盖起止范围须同时填写且顺序正确')
 start=date.fromisoformat(p.get('start','2026-09-25'))
 term=int(p.get('term_days',90));freq=int(p.get('frequency_days',7));count=int(p.get('count',3))
 if term<1 or term>3650 or freq not in [7,14] or not 1<=count<=20:
  raise ValueError('排期参数超出允许范围')
 def valid(d):
  if lower and not lower<=d<=upper:
   raise ValueError('排期超出已提供日历覆盖范围，请补日历后重算')
  return d in workdays or (d.weekday()<5 and d not in holidays)
 def adjust(d,direction=1):
  for _ in range(371):
   if valid(d):return d
   d+=timedelta(days=direction)
  raise ValueError('日历连续不可用天数过多，停止计算，请核对输入')
 out=[];establishments=set()
 for i in range(count):
  planned=start+timedelta(days=i*freq);actual=adjust(planned)
  close=adjust(actual-timedelta(days=1),-1);maturity=adjust(actual+timedelta(days=term))
  if actual in establishments:
   raise ValueError('顺延导致多个批次成立日重合，请调整起始日或发行频率')
  if not close<actual<maturity:raise ValueError('募集、成立和到期日期顺序不合法')
  establishments.add(actual)
  out.append({'批次':i+1,'拟成立日':str(planned),'成立日':str(actual),'募集结束日':str(close),
              '到期日':str(maturity),'实际自然日':(maturity-actual).days,'顺延':actual!=planned,'日历版本':cfg['version']})
 assumptions=['按输入日历顺延；不是法定节假日日历或发行规则认证']
 if not lower:assumptions.append('未提供日历覆盖范围，跨期完整性须人工核验')
 return {'rows':out,'issues':[{'字段':'日历','状态':x} for x in assumptions],
         'constraint_checks':{'chronology':True,'distinct_establishment_dates':True,
                              'calendar_coverage_provided':bool(lower),'calendar_version':cfg['version']},
         'material_preview':{'标题':'产品发行材料草稿','约定期限自然日':term,'发行频率天':freq,
                             '日历版本':cfg['version'],'需人工确认':['产品要素','日历适用市场','顺延日期','募集与成立时点']},
         'note':'仅对输入规则作确定性校验；所有结果是待复核排期草案，不是发行决定'}

def weekly_report(p):
 out=[];issues=[];seen=set()
 for i,r in enumerate(p.get('rows',rows('weekly_raw.csv')),2):
  if not isinstance(r.get('登记编码'),str):raise ValueError('登记编码必须为字符串，不能猜测前导零')
  date.fromisoformat(r['数据日期'])
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
 return {'tool':tool,'synthetic':INPUT_SOURCES.get() is None,'result':result,'source_files':[{'file':n,'sha256':hashlib.sha256((DATA/n).read_bytes() if INPUT_SOURCES.get() is None else json.dumps(source(n),ensure_ascii=False,sort_keys=True).encode()).hexdigest()} for n in FILES[tool]]}

def material_fill(p):
 from .python_skills import material_fill as impl
 return impl(p)
TOOLS['material_fill']=material_fill
FILES['material_fill']=['calendar.json']
