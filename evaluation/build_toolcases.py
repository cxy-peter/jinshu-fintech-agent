from pathlib import Path
from datetime import date,timedelta
from decimal import Decimal
import json,hashlib,datetime
D=Path(__file__).resolve().parent;cases=[]
def add(tool,p,expect,fixture=None,kind='contract'):
 cases.append({'id':f'T{len(cases)+1:03d}','tool':tool,'params':p,'expect':expect,'fixture':fixture,'case_type':kind})
holidays={'2026-09-25','2026-10-01','2026-10-02'}
def sched(start,term=90,frequency=7,count=3):
 d=date.fromisoformat(start)
 def valid(d):return d.weekday()<5 and d.isoformat() not in holidays
 def nxt(d):
  while not valid(d):d+=timedelta(days=1)
  return d
 rows=[]
 for k in range(count):
  planned=d+timedelta(days=k*frequency);s=nxt(planned);e=nxt(s+timedelta(days=term));c=s-timedelta(days=1)
  while not valid(c):c-=timedelta(days=1)
  rows.append({'成立日':str(s),'募集结束日':str(c),'到期日':str(e),'实际自然日':(e-s).days,'顺延':s!=planned})
 return rows
for s,t,f,n in [('2026-09-24',90,7,3),('2026-09-25',90,7,3),('2026-09-26',1,14,2),('2026-10-01',30,7,2),('2026-10-02',14,14,1),('2026-12-31',31,7,2),('2028-02-29',1,7,1),('2026-09-28',3650,14,20),('2026-09-23',7,7,1)]:add('issuance',{'start':s,'term_days':t,'frequency_days':f,'count':n},{'rows_subset':sched(s,t,f,n)})
for p in [{'start':'2026-02-29'},{'start':'2026-02-31'},{'frequency_days':8},{'term_days':0},{'count':21},{'term_days':1.5},{'start':'09/25/2026'}]:add('issuance',p,{'error':True})
assert len(cases)==16
for title,s,t,n in [('模拟发行A','2026-09-25',90,3),('产品β测试','2026-10-01',1,1),('华文测试\n内部草稿','2026-09-24',10,2),('季度材料2026','2026-12-31',120,4)]:add('material_fill',{'title':title,'start':s,'term_days':t,'count':n},{'rows_subset':sched(s,t,7,n),'title':title})
for p in [{'term_days':-10},{'count':0},{'frequency_days':30},{'start':'not-a-date'}]:add('material_fill',p,{'error':True})
assert len(cases)==24
base={'登记编码':'0009','名称':'模拟产品','规模万元':'1,200','区间收益率':'2%','数据日期':'2026-08-30'}
for amount,rate,n,r in [('1,200','2%',1200,.02),('(120.5)','-1.5%',-120.5,-.015),('0','0%',0,0),('--','N/A',None,None),('','',None,None),(' 3,000.50 ',' 1.25% ',3000.5,.0125),('.5','0.2',.5,.2),('100','(2%)',100,-.02),('-12','--',-12,None),('42.3','(0.7)',42.3,-.7)]:add('weekly_report',{'rows':[base|{'规模万元':amount,'区间收益率':rate}]},{'rows_subset':[{'登记编码':'0009','规模万元':n,'区间收益率':r}]})
for p in [{'rows':[base,base]},{'rows':[base|{'登记编码':''}]},{'rows':[base|{'数据日期':''}]},{'rows':[base|{'规模万元':'NaN'}]},{'rows':[base|{'规模万元':'2%'}]},{'rows':[base|{'区间收益率':'infinity'}]},{'rows':[base|{'规模万元':'1,2,3'}]}]:add('weekly_report',p,{'error':True},kind='challenge' if '1,2,3' in str(p) else 'contract')
add('weekly_report',{'rows':[base|{'登记编码':9}]},{'error':True},kind='challenge')
add('weekly_report',{'rows':[base,base|{'数据日期':'2026-08-31'}]},{'row_count':2})
add('weekly_report',{'rows':[]},{'row_count':0})
assert len(cases)==44
cols={'投资性质':'固收','运作模式':'封闭','风险等级':'R2','持有期限':'90','代销渠道':'直销','币种':'CNY'}
products=[cols|{'产品编码':'A','产品全称':'模拟A'},cols|{'产品编码':'B','产品全称':'模拟B'}]
def nav(valsA,valsB):
 return [{'产品编码':p,'净值日期':dt,'累计净值':str(v)} for p,vals in [('A',valsA),('B',valsB)] for dt,v in zip(['2026-06-01','2026-07-01','2026-08-30'],vals)]
def expected(vals):
 vs=list(map(lambda v:Decimal(str(v)),vals));peak=vs[0];dd=Decimal('0')
 for v in vs:peak=max(peak,v);dd=max(dd,1-v/peak)
 return {'区间收益率':float(vs[-1]/vs[0]-1),'最大回撤':float(dd)}
scens=[([1,1.1,1.2],[1,.9,1.1]),([1,1,1],[2,2,2]),([1,1.2,1.05],[1,1.01,1.02]),([1,.7,.8],[1,1.05,1.01]),([2,3,2.5],[1,.99,1.1]),([1,.99,.98],[1,.98,.99]),([10,11,9],[1,1,1.3]),([1,2,1],[2,3,4])]
for a,b in scens:add('wealth_benchmark',{'products':products,'nav':nav(a,b),'product':'A'},{'rows_subset':[{'产品编码':'A'}|expected(a),{'产品编码':'B'}|expected(b)]})
p={'products':products,'nav':nav([1,1.1,1.2],[1,.9,1.1]),'product':'A'}
mutations=[p|{'product':'X'},p|{'products':[products[0]]},p|{'products':[products[0],products[1]|{'风险等级':'R3'}]},p|{'start':'2026-09-01'},p|{'end':'2026-07-02'},p|{'start':'2026-02-30'},p|{'nav':p['nav'][1:]},p|{'nav':p['nav']+[p['nav'][0]]},p|{'nav':[p['nav'][0]|{'累计净值':'0'}]+p['nav'][1:]},p|{'nav':[p['nav'][0]|{'累计净值':'-1'}]+p['nav'][1:]},p|{'nav':[p['nav'][0]|{'累计净值':''}]+p['nav'][1:]},p|{'nav':[p['nav'][0]|{'累计净值':'NaN'}]+p['nav'][1:]}]
for m in mutations:add('wealth_benchmark',m,{'error':True})
assert len(cases)==64
for stage in [1,2,3,4,'2']:
 add('onboarding',{'decision_stage':stage},{'stage':int(stage)})
for stage in [0,-1,5,1.5,'x',99,float('inf')]:add('onboarding',{'decision_stage':str(stage) if stage==float('inf') else stage},{'error':True})
assert len(cases)==76
for th in [1,5,50,999,1000000]:add('strategy',{'threshold':th},{'candidate_subset':{'threshold':th,'status':'disabled','approval':'required'}})
for p in [{'threshold':0},{'threshold':-1},{'threshold':1000001},{'threshold':.5},{'threshold':'unknown'},{'feature':'not_registered'},{'event':'not_event'}]:add('strategy',p,{'error':True})
assert len(cases)==88
for y in [2024,2025]:add('statements',{'year':y},{'passed':True})
add('statements',{'year':2099},{'error':True})
f=json.loads((R:=D.parent/'lite/web/fixtures.json').read_text());sample=f['statements'][0]
add('statements',{'year':int(sample['year'])},{'passed':False},{'statements':[sample|{'assets':str(Decimal(str(sample['assets']))+1)}]})
# Explicit missing-data challenges: null is not a valid financial zero.
for key in ['cfo','fx']:
 toy={'year':'2025','assets':'100','liabilities':'60','equity':'40','cfo':'0','cfi':'0','cff':'0','fx':'0','net_cash_change':'0','opening_cash':'10','ending_cash':'10','unit':'万元','scope':'synthetic','synthetic':True};toy[key]=None
 add('statements',{'year':2025},{'must_not_pass':True},{'statements':[toy]},kind='challenge')
assert len(cases)==94
case={'case_id':'CA','case_no':'2026-1','reference_no':'R1'};mail={'message_id':'M1','case_no':'2026-1','reference_no':'R1','delivery':'unconfirmed'}
for ff,expected_ in [({'cases':[case],'mails':[mail]},{'status':'found_sent_record','delivery':'unconfirmed'}),({'cases':[case],'mails':[]},{'status':'not_found_needs_review'}),({'cases':[case],'mails':[mail,mail|{'message_id':'M2'}]},{'status':'ambiguous'}),({'cases':[case],'mails':[mail|{'case_no':'unmatched'}]},{'match_key':'reference_no','status':'found_sent_record'}),({'cases':[case|{'case_no':'2026/1'}],'mails':[mail]},{'status':'found_sent_record'}),({'cases':[case|{'reference_no':''}],'mails':[mail|{'case_no':'other'}]},{'status':'not_found_needs_review'})]:add('kep',{}, {'rows_subset':[expected_]},ff)
assert len(cases)==100
(D/'tools100.json').write_text(json.dumps({'source':'Independent Decimal/date reference calculations; synthetic fixtures; parameterized cases not separate business tasks','rows':cases},ensure_ascii=False,indent=2,allow_nan=False))
print('Tools cases',len(cases))
