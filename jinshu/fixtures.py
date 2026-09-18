"""Reproducible synthetic schemas model prior financial-product work; never company data."""
from __future__ import annotations
import csv,hashlib,json,random
from datetime import date,timedelta
from decimal import Decimal
from pathlib import Path
from . import ROOT
DATA=ROOT/'data'/'synthetic'
DEPARTMENTS={'dept_wealth':'理财产品','dept_release':'发行与报表','dept_risk':'准入与风控产品','dept_service':'客服知识'}
DOCS=[
('benchmark','dept_wealth','可比产品筛选口径',1,'active',
'''# 可比产品筛选口径（模拟）\n## 对标范围\n同业对标先统一投资性质、运作模式、持有期限、风险等级、代销渠道及观察区间。不要将固定收益和混合类产品直接排名。\n## 指标解释\n区间收益率按累计净值末值除以初值减一计算。最大回撤使用观察期内累计净值峰值，不等于净值最大单日跌幅。模拟净值没有分红，真实份额需要复权核对。\n## 结果边界\n市场中位数与分位只在当前筛选的样本内成立，不代表全行业；对照数据与本司净值必须使用共同起止日期。'''),
('calendar','dept_release','募集成立日期安排',2,'active',
'''# 募集成立日期安排（模拟制度）\n## 非工作日处理\n周或双周批次频率由产品配置指定。拟成立日遇非工作日应按模拟营业日历顺延，募集结束日在成立日前一个营业日；不得默认中国节假日规则适用于所有市场。\n## 期限说明\n到期日为成立日加约定期限后按示例约定顺延。期限单位为自然日，顺延后的实际天数可能变化，需要在预览中显示并交发行人员确认。\n## 复核清单\n检查拟成立日、实际成立日、募集结束日、到期日、顺延原因、时区、日历版本。Skill只能增加提醒或检索词，不能自行改动产品合同期限和正式节假日日历。'''),
('calendar','dept_release','募集成立日期安排',1,'archived',
'''# 募集成立日期安排旧版（模拟、已作废）\n## 旧口径\n示例旧版不执行非工作日顺延。该文仅用于验证旧版排除，禁止作为新答复依据。'''),
('weekly','dept_release','周报表格整理规范',1,'active',
'''# 周报表格整理规范（模拟）\n## 输入检查\n周报缺数先检查源文件是否齐全、字段名是否一致、观察日是否匹配。表头不固定为第一行，遇多个相同业务主键应报告冲突而非取第一条。\n## 数字清洗\n千分位金额、百分比、带括号的负数分开解析。登记编码始终保留字符串与前导零，空值不能填成零。\n## 输出检查\n净值、排名和格式整理分步记录，输出附输入哈希与行号；重跑不覆盖原输入。'''),
('onboarding','dept_risk','开户数据可用时点',1,'active',
'''# 开户数据可用时点（模拟需求，不是监管规定）\n## 决策时点\n演示流程为问卷、视频核验、账户激活、首次入金。候选字段必须在当前决策节点已经采集且满足授权要求。\n## 字段分工\n问卷的行业与收入区间可前置核对；本模拟把银行账户关联信息放在首次入金后，不能拿它反推入金前评分。\n## 产品交付\n输出字段、来源、采集节点、使用节点、负责人、待确认项。工具只形成需求澄清单，不给真实客户定级、不宣称满足MASAK或其他监管。'''),
('kep','dept_risk','案件邮件核查作业',1,'active',
'''# 案件邮件核查作业（模拟）\n## 匹配依据\n核查先用案件号精确查询，无结果再使用参考号。兼容分隔符时仍核对完整主题和时间范围；排除非目标业务邮件。\n## 异常分层\n找到发送记录、无法检索、多个候选、查询报错、编号缺失必须分开。未找到不是业务漏回复，发送记录也不等于送达成功。\n## 协同\n技术错误由工具维护人复查，业务状态交Fraud或相关负责人确认。Agent仅生成内部核查摘要，不自动回复监管邮件。'''),
('feature','dept_risk','特征需求与候选配置',1,'active',
'''# 特征需求与候选配置（模拟）\n## 字段约束\n计数特征要确认事件、状态、唯一键、时间窗口和刷新频率。success过滤不等于成功事件已去重；小时更新数据不能当实时特征。\n## 下线状态\n自然语言生成的策略只能输出候选JSON，检查事件权限和已有特征；发布目标保持disabled，不自动生效、不产生处罚。\n## 协同\n算法评估表达式，数据团队确认字段，产品核对需求，业务负责人审批；模型不可自己授权。'''),
('service','dept_service','客服问答与转人工',1,'active',
'''# 客服问答与转人工（模拟）\n## 问题分类\n一般流程咨询可查有效FAQ。涉及具体账户状态需授权业务查询；知识库没有账户实时状态。\n## 版本与语言\n答案需对应站点、语言和有效版本；中文、英文、土耳其语不能因语义接近而混用。旧政策的译文需要回查原文版本。\n## 无依据处理\n缺少有效资料时明确说明未取得依据，保留问题和已查来源转人工。不能编造退款、冻结或提现完成情况。'''),
('financial','dept_release','经营报表口径',1,'active',
'''# 经营报表口径（模拟）\n## 三表关系\n资产应等于负债加权益；现金净变动按经营、投资、筹资及汇率影响合计；期末现金等于期初加净变动。\n## 数据边界\n合并与母公司口径分开，元万元分开，利润表和现金流量表为期间数、资产负债表为时点数。空数据不当零。\n## 说明\n经营净现金流下降只能形成检查线索，原因必须回到附注或业务记录核实，不由模型自行猜测。'''),
('draft','dept_service','提现新说明草稿',2,'pending_review',
'''# 提现新说明草稿（模拟未发布）\n## 草稿\n本文件没有审核，不能用于对客答复。'''),
]
WORKFLOWS={
 'wealth_benchmark':{'name':'理财产品对标','dept':'dept_wealth','triggers':['对标','净值','理财比较'],'tool':'wealth_benchmark','query':'可比产品 筛选 观察区间','template':'范围—指标—来源—复核'},
 'issuance':{'name':'发行排期与材料预览','dept':'dept_release','triggers':['排期','募集','成立日','发行'],'tool':'issuance','query':'募集 成立 期限','template':'日期—差异—待确认'},
 'weekly_report':{'name':'周报清洗与质检','dept':'dept_release','triggers':['周报','缺数','文本数字'],'tool':'weekly_report','query':'周报 输入 字段 数字清洗','template':'输入—异常—输出'},
 'onboarding':{'name':'开户需求与字段时点核对','dept':'dept_risk','triggers':['开户','onboarding','IBAN','KYC'],'tool':'onboarding','query':'开户 字段 决策时点','template':'字段—时点—责任—待确认'},
 'kep':{'name':'案件邮件核查辅助','dept':'dept_risk','triggers':['核查','邮件','KEP'],'tool':'kep','query':'案件 邮件 匹配 异常','template':'状态—证据—人工复核'},
 'strategy':{'name':'特征与策略候选预检','dept':'dept_risk','triggers':['策略','特征','计数'],'tool':'strategy','query':'特征 事件 状态 下线','template':'输入—约束—候选—审批'},
 'statements':{'name':'模拟三表口径核对','dept':'dept_release','triggers':['三表','财报','资产负债'],'tool':'statements','query':'三表关系 合并 单位','template':'核对—差异—来源'},
 'service':{'name':'客服知识与异常转人工','dept':'dept_service','triggers':['客服','提现','转人工','FAQ'],'tool':None,'query':'客服 知识 版本 无依据','template':'依据—行动—转人工'},
}

def write_csv(name,rows):
 path=DATA/name;path.parent.mkdir(parents=True,exist_ok=True)
 with path.open('w',encoding='utf-8-sig',newline='') as f:
  writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
 return path

def generate():
 DATA.mkdir(parents=True,exist_ok=True);rng=random.Random(20260918)
 products=[];nav=[]
 for i in range(12):
  pid=f'SIM{i+1:04d}';products.append({'产品编码':pid,'产品全称':f'模拟机构{i//4+1}稳健系列{90 if i<8 else 180}天持有期理财产品第{i+1}号','投资性质':'固定收益' if i<10 else '混合','运作模式':'开放式','风险等级':'R2','持有期限':90 if i<8 else 180,'代销渠道':'渠道A' if i%4!=3 else '渠道B','币种':'CNY','synthetic':'true'})
  value=Decimal('1.000000');start=date(2026,6,1)
  for day in range(91):
   value *= Decimal(str(1+rng.gauss(.00009,.0004)))
   nav.append({'产品编码':pid,'净值日期':str(start+timedelta(days=day)),'累计净值':str(value.quantize(Decimal('.000001'))),'synthetic':'true'})
 write_csv('products.csv',products);write_csv('nav.csv',nav)
 write_csv('weekly_raw.csv',[{'登记编码':f'00{i:04d}','名称':f'模拟周报产品{i}','规模万元':f'{1000+i*32:,}.50','区间收益率':'--' if i==5 else f'{1+i*.1:.2f}%','数据日期':'2026-08-30','synthetic':'true'} for i in range(1,9)])
 write_csv('onboarding.csv',[{'field':k,'source':s,'available_stage':a,'owner':o,'synthetic':'true'} for k,s,a,o in [('industry','questionnaire',1,'业务'),('income_band','questionnaire',1,'业务'),('video_status','video_kyc',2,'KYC'),('bank_link','first_deposit',4,'数据'),('transaction_count_7d','events',4,'算法')]])
 write_csv('cases.csv',[{'case_id':f'SIM-CASE-{i:03d}','case_no':f'2026/{1000+i}','reference_no':f'REF-{i:03d}','channel':'KEP','synthetic':'true'} for i in range(1,21)])
 mails=[{'message_id':f'SIM-MSG-{i:03d}','case_no':f'2026-{1000+i}','reference_no':f'REF-{i:03d}','sent_at':'2026-08-30T10:00:00+03:00','delivery':'delivered' if i%3 else 'unknown','synthetic':'true'} for i in range(1,16)]
 mails.append(dict(mails[0],message_id='SIM-DUP-001'));write_csv('mails.csv',mails)
 write_csv('features.csv',[{'name':'successful_deposit_count_7d','event':'FiatDeposit','status_filter':'success','dedup_key':'transaction_id','window':'7d','refresh':'T+1','synthetic':'true'},{'name':'withdraw_sum_24h','event':'ChainWithdraw','status_filter':'success','dedup_key':'transaction_id','window':'24h','refresh':'realtime','synthetic':'true'}])
 write_csv('statements.csv',[{'year':y,'assets':1000000+y*10,'liabilities':400000+y*5,'equity':600000+y*5,'revenue':800000+y*12,'profit':100000+y,'cfo':80000+y,'cfi':-50000,'cff':10000,'fx':0,'net_cash_change':40000+y,'opening_cash':50000,'ending_cash':90000+y,'unit':'元','scope':'consolidated','synthetic':'true'} for y in [2024,2025]])
 (DATA/'calendar.json').write_text(json.dumps({'synthetic':True,'version':'SIM-CALENDAR-v1','note':'仅为模拟营业日历，不是官方节假日表','holidays':['2026-09-25','2026-10-01','2026-10-02']},ensure_ascii=False,indent=2))
 docs=[]
 for topic,dept,title,version,status,body in DOCS:
  f=f'{topic}_v{version}.md';(DATA/f).write_text(body+'\n\n> 本文及数值均为模拟，仅用于验证软件流程。',encoding='utf-8');docs.append(dict(topic=topic,dept_id=dept,title=title,version=version,status=status,file=f))
 (DATA/'documents.json').write_text(json.dumps(docs,ensure_ascii=False,indent=2))
 (DATA/'manifest.json').write_text(json.dumps({'seed':20260918,'synthetic':True,'description':'仿照历史业务字段结构生成，不是原公司数据','files':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in DATA.iterdir() if p.is_file() and p.name!='manifest.json'}},ensure_ascii=False,indent=2))
 return {'products':len(products),'nav_rows':len(nav),'documents':len(docs)}

if __name__=='__main__':print(generate())

# Separate executable material skill: reuse issuance calculation, not a second calculator.
WORKFLOWS['material_fill']={'name':'理财发行材料生成','dept':'dept_release','triggers':['材料填充','生成Word','材料生成'], 'tool':'material_fill','query':'发行材料 产品要素 日历 顺延 复核','template':'日期—差异—待确认'}
