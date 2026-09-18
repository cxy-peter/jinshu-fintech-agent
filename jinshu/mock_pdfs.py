"""Generate native-text synthetic PDFs from registered financial sample files.
No original employer document or personal record is included.
"""
from __future__ import annotations
import csv,json
from pathlib import Path
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle
from reportlab.lib.pagesizes import A4
from .fixtures import DATA,generate as generate_data
from . import ROOT
OUT=ROOT/'data'/'mock_pdf'


def generate():
    if not (DATA/'statements.csv').exists():generate_data()
    OUT.mkdir(parents=True,exist_ok=True)
    if 'STSong-Light' not in pdfmetrics.getRegisteredFontNames():pdfmetrics.registerFont(UnicodeCIDFont('STSong-Light'))
    title=ParagraphStyle('title',fontName='STSong-Light',fontSize=19,leading=26,spaceAfter=16)
    h=ParagraphStyle('heading',fontName='STSong-Light',fontSize=14,leading=21,spaceBefore=12,spaceAfter=8)
    body=ParagraphStyle('body',fontName='STSong-Light',fontSize=10.5,leading=17,spaceAfter=8)
    manifest=[]
    def footer(canvas,doc):
        canvas.setFont('STSong-Light',9);canvas.setFillColor(colors.HexColor('#65736e'))
        canvas.drawString(38,22,f'金枢模拟样例 / 无真实客户数据 / 第{doc.page}页')
    def make(file,name,dept,topic,level,paragraphs,table=None):
        story=[Paragraph(name,title),Paragraph('演示企业：金枢模拟金融服务有限公司。全部数值与制度为个人项目合成样例，不代表任何机构现行规则。',body)]
        for head,text in paragraphs:story.extend([Paragraph(head,h),Paragraph(text,body)])
        if table:
            width=(A4[0]-76)/len(table[0]);t=Table([[Paragraph(str(c),body) for c in row] for row in table],colWidths=[width]*len(table[0]),repeatRows=1)
            t.setStyle(TableStyle([('GRID',(0,0),(-1,-1),.5,colors.HexColor('#a5b5ae')),('BACKGROUND',(0,0),(-1,0),colors.HexColor('#e6efe9')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),6),('RIGHTPADDING',(0,0),(-1,-1),6)]));story.append(t)
        SimpleDocTemplate(str(OUT/file),pagesize=A4,leftMargin=38,rightMargin=38,topMargin=40,bottomMargin=38).build(story,onFirstPage=footer,onLaterPages=footer)
        manifest.append({'file':file,'title':name,'dept_id':dept,'topic':topic,'version':1,'manual_sensitivity':level,'synthetic':True})
    with (DATA/'statements.csv').open(encoding='utf-8-sig') as f:stat=list(csv.DictReader(f))
    metric={'assets':'资产总计','liabilities':'负债合计','equity':'所有者权益合计','revenue':'营业收入','cost':'营业成本','profit':'净利润','cfo':'经营活动现金流量净额','cfi':'投资活动现金流量净额','cff':'筹资活动现金流量净额','fx':'汇率影响','net_cash_change':'现金净变动','opening_cash':'期初现金','ending_cash':'期末现金'}
    for file,name,keys in [('01_balance_sheet.pdf','模拟资产负债表',['assets','liabilities','equity']),('02_income_statement.pdf','模拟利润表',['revenue','profit']),('03_cashflow_statement.pdf','模拟现金流量表',['cfo','cfi','cff','fx','net_cash_change','opening_cash','ending_cash'])]:
        cols=['项目']+[r['year']+'年' for r in stat]
        table=[cols]+[[metric[k]]+[r.get(k,'未提供') for r in stat] for k in keys]
        make(file,name,'dept_wealth',file[:-4],'internal',[('报表口径','单位：元；合并口径；2024、2025年度模拟财务样例。不能与真实公司数字拼接。'),('复核要求','核对年份与单位。缺失不等于零。资产等于负债与权益之和，现金流量表需要核对净变动和期初期末关系。')],table)
    with (DATA/'products.csv').open(encoding='utf-8-sig') as f:products=list(csv.DictReader(f))
    make('04_wealth_products.pdf','模拟理财产品资料','dept_wealth','pdf-wealth-products','internal',[
      ('对标范围','按投资性质、运作模式、风险等级、持有期限、渠道与币种筛选；净值使用同一观察区间。'),('使用边界','产品均为SIM编码，不是可购买的实际产品。收益与回撤由Python计算，资料用于说明字段口径。')],
      [['产品编码','产品名称','性质','持有期限']]+[[r['产品编码'],r['产品全称'],r['投资性质'],r['持有期限']] for r in products])
    make('05_issuance_sop.pdf','模拟发行排期与材料SOP','dept_release','pdf-issuance-sop','internal',[
      ('排期步骤','先确认产品期限、周或双周发行频率和目标成立日，再调用Python发行排期Skill。非工作日按模拟日历顺延，日历版本写入结果。'),
      ('材料准备','将产品名称、募集结束日、成立日、到期日映射到Word模板。相同参数可复用同一草稿，最终由产品运营复核。'),
      ('节假日冲突','拟成立日不等于调整后成立日。必须同时显示原日期、实际日期、顺延原因与日历版本。模拟日历不是真实官方日历。')])
    make('06_public_faq.pdf','模拟客服公共FAQ','dept_service','pdf-public-faq','public',[
      ('怎样查询提现帮助','未登录用户可阅读公共帮助。具体账户状态需先验证身份；不能依据公共FAQ推测用户账户是否被冻结。'),
      ('怎样转人工','用户主动请求、会话连续未解决或高风险个案可进入人工支持。接口不可用时保留待提交草稿，并明确尚未提交成功。'),
      ('接口异常','登录验证失败只提供公共说明；验证失败不视为验证成功。知识查询失败时显示帮助入口，不编造答案。')])
    make('07_onboarding_sop.pdf','模拟开户字段时点说明','dept_risk','pdf-onboarding','restricted',[
      ('字段与节点','前置开户评分只可使用决策节点已经采集的信息。IBAN为演示中的后置字段，不能当作前置节点普通缺失值直接填充。'),
      ('流程澄清','确认字段定义、来源、产生时间、使用目的与负责人。系统输出需求清单，不自动决定客户风险等级。'),
      ('敏感提示','内部风控策略与阈值说明需要审核后限定部门可见；本材料不含真实生产阈值。')])
    make('08_case_handoff.pdf','模拟客服个案交接表','dept_service','pdf-case-handoff','internal',[
      ('个案摘要','演示邮箱：case-demo@example.invalid。此为虚构测试标识，用于触发敏感性建议，不是真实联系方式。'),
      ('审核原则','上传者初标为内部，系统根据邮箱字段建议敏感。最终由另一位审核人确认级别与可访问部门；审核通过前不进入普通问答。'),
      ('工单失败','远端工单服务未确认时状态保持待提交。沿用幂等键重试，避免因反复点击生成多份本地请求。')])
    (OUT/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return manifest
if __name__=='__main__':print(json.dumps(generate(),ensure_ascii=False,indent=2))
