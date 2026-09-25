"""Server tools reuse jinshu.tools; inputs are explicit and remain request-local."""
from __future__ import annotations
import copy,json
from datetime import date
from jinshu import tools
REQUIRED_PARAMS={'issuance':['start','term_days','frequency_days','count'],'material_fill':['start','term_days','frequency_days','count','product_name'],
 'wealth_benchmark':['product','start','end'],'statements':['year'],'onboarding':['decision_stage'],'strategy':['feature','event','threshold'],'weekly_report':[],'kep':[]}
def execute(name,params,*,examples=False,sources=None):
 if name not in REQUIRED_PARAMS:raise ValueError('工具未登记')
 if not isinstance(params,dict):raise ValueError('参数需要对象')
 if set(params)-set(REQUIRED_PARAMS[name]):raise ValueError('含未登记的工具参数')
 params=copy.deepcopy(params)
 if not examples:
  absent=[k for k in REQUIRED_PARAMS[name] if params.get(k) in [None,'']]
  if absent:raise ValueError('缺少输入参数：'+','.join(absent))
  required=tools.FILES[name]
  if not isinstance(sources,dict) or set(sources)!=set(required):raise ValueError('请提供本工具完整数据文件：'+','.join(required))
  if len(json.dumps(sources,ensure_ascii=False).encode())>1_000_000:raise ValueError('单任务输入限制1MB')
  for filename,data in sources.items():
   if filename.endswith('.csv') and (not isinstance(data,list) or len(data)>5000 or not all(isinstance(x,dict) for x in data)):raise ValueError('数据表应为不超过5000行的对象数组')
  if 'calendar.json' in sources:
   c=sources['calendar.json']
   if not isinstance(c,dict) or not isinstance(c.get('holidays'),list) or not c.get('version'):raise ValueError('日历需要版本及holidays数组')
   for v in c['holidays']:date.fromisoformat(v)
 for k in ['start','end']:
  if k in params:date.fromisoformat(params[k])
 for k in ['term_days','frequency_days','count','threshold','decision_stage','year']:
  if k in params and (isinstance(params[k],bool) or not isinstance(params[k],int)):raise ValueError(k+'需要整数，不能截断小数')
 token=tools.INPUT_SOURCES.set(None if examples else copy.deepcopy(sources))
 try:
  if name=='material_fill':
   result=tools.run('issuance',params);result['tool']=name;result['result']['product_name']=params.get('product_name','示例产品')
  else:result=tools.run(name,params)
  result['input_mode']='synthetic_example' if examples else 'user_supplied';result['business_action_executed']=False
  if not examples:
   result['result']['calculation_assumptions']=result['result'].get('note','')
   result['result']['note']='依据本次用户提供数据计算；需核对数据口径、复核结果，不执行正式业务操作。'
  return result
 finally:tools.INPUT_SOURCES.reset(token)
def dispatch(name,params):
 if not params.get('execute_tool'):return {'tool':name,'executed':False,'status':'needs_explicit_inputs','result':{'note':'请在业务任务页确认参数与数据后执行；不会自动使用模拟数据。'}}
 return execute(name,params.get('values',{}),examples=params.get('use_examples') is True,sources=params.get('sources'))
