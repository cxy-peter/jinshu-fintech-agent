"""Discover existing business workflows without executing or supplying demo data."""
from __future__ import annotations

import copy
import re
from datetime import date

from jinshu.tools import FILES
from unified.tools import REQUIRED_PARAMS

_REPO = 'https://github.com/cxy-peter/jinshu-fintech-agent/blob/main/'
_FIELDS = {
    'start': '起始日期（YYYY-MM-DD）', 'end': '截止日期（YYYY-MM-DD）',
    'term_days': '约定期限自然日（1–3650）', 'frequency_days': '发行周期（7 或 14 天）',
    'count': '批次数（1–20）', 'product_name': '产品名称', 'product': '产品编码',
    'year': '报表年度', 'decision_stage': '采集节点（1–4）',
    'feature': '已登记特征名', 'event': '已登记事件名', 'threshold': '候选阈值',
}
_SPECS = [
    ('issuance', '发行与发送排期', '计算周／双周发行日期，以及禁止周末与已列节假日的发送计划。',
     ['从2026-11-09起，期限90天，每两周发行，共3期，生成排期'],
     ['发送计划需覆盖完整的已确认日历；调休周末也禁止发送。', '成立日仍遵循输入营业日历；结果为待复核草稿，不发邮件。'],
     r'排期|发行计划|募集日期|成立日期|发送计划|周末.{0,6}发送|节假日.{0,6}发送'),
    ('material_fill', '发行材料预览', '把同一次排期的日期和产品名称带入发行材料预览。',
     ['为产品名称“模拟稳健一号”生成发行材料，从2026-11-09起，期限90天，每周发行3期'],
     ['线上输出结构化材料预览；本地 Python Skill 可生成 Word。', '材料与排期共用计算结果，仍需人工核对模板和条款。'],
     r'发行材料|材料填充|模板填充|产品发行书|填充.{0,4}(?:材料|模板)'),
    ('wealth_benchmark', '同口径产品对标', '按六项产品属性筛选同类，并计算共同区间收益率及最大回撤。',
     ['对标产品编码SIM0001，从2026-06-01到2026-08-30的净值表现'],
     ['必须提供产品表和共同起止日净值；不补造缺失数据。', '不是全市场排名，不含分红复权处理或投资建议。'],
     r'同业对标|业绩比较|净值对比|收益对标|产品对标|同业比较|对标.{0,8}产品|净值表现'),
    ('weekly_report', '周报数据质检', '保留登记编码前导零，规范金额和收益率，标记缺失及重复主键。',
     ['清洗周报里的千分位、百分数，保留登记编码前导零'],
     ['原始输入不覆盖；缺失不按零计算。', '需要按登记编码、名称、规模万元、区间收益率、数据日期提供数据。'],
     r'周报|月报.{0,6}(?:清洗|质检)|数字清洗|数据清洗|前导零|千分位'),
    ('onboarding', '开户信息采集时序', '核对给定节点已经取得的字段，标出当前尚不可用的信息。',
     ['核对开户流程第2阶段能够使用哪些已采集字段'],
     ['不使用未来节点的数据，不作 KYC 或客户风险等级决定。'],
     r'开户|\bKYC\b|采集时序|信息采集.{0,6}(?:节点|阶段)'),
    ('kep', '案件与邮件记录核对', '按案件号、参考号匹配邮件记录，区分唯一、歧义和未找到。',
     ['核对案件是否有邮件回复记录，找出歧义匹配'],
     ['未找到不等于漏回复，已发送记录不等于送达。', '仅核对输入表，不读取邮箱或发送邮件。'],
     r'\bKEP\b|案件.{0,8}(?:核对|邮件)|邮件.{0,8}(?:核对|记录)|漏回复'),
    ('strategy', '策略候选校验', '校验登记特征与事件对应关系，生成关闭状态的阈值候选。',
     ['核验策略候选：feature=successful_deposit_count_7d，event=FiatDeposit，threshold=5'],
     ['候选保持 disabled，需人工审批；未连接真实策略执行平台。'],
     r'策略候选|策略阈值|特征.{0,8}事件|风控策略'),
    ('statements', '财务三表勾稽', '验证资产负债、现金净变动、期末现金三个等式。',
     ['检查2025年度财务三表勾稽'],
     ['十个必要字段不全则阻断；不补零，不替代审计意见。'],
     r'财务三表|三表勾稽|财报.{0,6}(?:核验|核对|检查)|资产负债.{0,6}(?:平衡|勾稽)|现金流.{0,6}勾稽'),
]


def catalog() -> list[dict]:
    """Return descriptions of callable, registered tools, with no mutable globals."""
    return [
        {'id': tool, 'tool': tool, 'name': name, 'scenario': scenario,
         'required_params': list(REQUIRED_PARAMS[tool]),
         'inputs': {key: _FIELDS[key] for key in REQUIRED_PARAMS[tool]},
         'source_files': list(FILES[tool]), 'examples': list(examples),
         'source': [_REPO + 'jinshu/tools.py', _REPO + 'unified/tools.py'],
         'boundaries': list(boundaries), 'requires_confirmation': True,
         'business_action_executed': False}
        for tool, name, scenario, examples, boundaries, _pattern in _SPECS
    ]


def _integer(value: str) -> int:
    if value.isdigit():
        return int(value)
    if not re.fullmatch(r'(?:[一二两三四五六七八九]|[一二两三四五六七八九]?十[一二三四五六七八九]?)', value):
        raise ValueError('不猜测不规范的中文数词')
    digits = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
              '六': 6, '七': 7, '八': 8, '九': 9, '零': 0}
    if '十' in value:
        left, right = value.split('十', 1)
        return (digits.get(left, 1) if left else 1) * 10 + digits.get(right, 0)
    return digits[value]


def _one_number(pattern: str, query: str, lower: int, upper: int):
    values = set()
    for match in re.findall(pattern, query, re.I):
        try:
            values.add(_integer(match))
        except (KeyError, ValueError):
            continue
    return next(iter(values)) if len(values) == 1 and lower <= next(iter(values)) <= upper else None


def _values(tool: str, query: str) -> dict:
    values = {}
    dates = []
    for m in re.finditer(r'(?<!\d)(\d{4})[-/年](\d{1,2})[-/月](\d{1,2})日?(?!\d)', query):
        try:
            parsed = date(*map(int, m.groups())).isoformat()
        except ValueError:
            continue
        dates.append(parsed)
    dates = list(dict.fromkeys(dates))
    if tool in ('issuance', 'material_fill'):
        if len(dates) == 1:
            values['start'] = dates[0]
        for key, pattern, lo, hi in [
            ('term_days', r'(?:期限|存续期|存续|(?<=天)或(?:者)?)\s*(\d{1,4})\s*(?:个)?(?:自然)?天', 1, 3650),
            ('count', r'(?:共|计划|发行|排)?\s*([一二两三四五六七八九十零]{1,3}|\d{1,2})\s*(?:期|批)(?!限)', 1, 20),
        ]:
            n = _one_number(pattern, query, lo, hi)
            if n is not None:
                values[key] = n
        fortnight = bool(re.search(r'双周|每(?:两|二|2)周|每\s*14\s*天|周期\s*14\s*天', query))
        weekly = bool(re.search(r'每周|单周|每(?:一|1)周|每\s*7\s*天|周期\s*7\s*天', query))
        if fortnight != weekly:
            values['frequency_days'] = 14 if fortnight else 7
        if tool == 'material_fill':
            names = re.findall(r'产品名称\s*[：:=]?\s*[“"「]([^”"」\n]{1,100})[”"」]', query)
            if len(set(names)) == 1:
                values['product_name'] = names[0]
    elif tool == 'wealth_benchmark':
        if len(dates) == 2 and dates[0] < dates[1]:
            values.update(start=dates[0], end=dates[1])
        products = re.findall(r'产品编码\s*[：:=]?\s*([A-Za-z0-9_-]{1,64})(?![A-Za-z0-9_-])', query)
        if len(set(products)) == 1:
            values['product'] = products[0]
    elif tool == 'statements':
        n = _one_number(r'(?<!\d)(\d{4})\s*年(?:度)?', query, 1900, 2200)
        if n is not None:
            values['year'] = n
    elif tool == 'onboarding':
        n = _one_number(r'第\s*([一二三四]|[1-4])\s*(?:阶段|节点)', query, 1, 4)
        if n is not None:
            values['decision_stage'] = n
    elif tool == 'strategy':
        for key in ('feature', 'event'):
            matches = re.findall(r'\b' + key + r'\s*[=:]\s*([A-Za-z_][A-Za-z0-9_]{0,99})', query)
            if len(set(matches)) == 1:
                values[key] = matches[0]
        n = _one_number(r'\bthreshold\s*[=:]\s*(\d{1,7})(?!\d)', query, 1, 1_000_000)
        if n is not None:
            values['threshold'] = n
    return values


def suggest(query: str) -> list[dict]:
    """Suggest at most two workflows from explicit terms; never execute a task."""
    if not isinstance(query, str) or not query.strip():
        return []
    query = query[:8000]
    matches = [item for item, spec in zip(catalog(), _SPECS) if re.search(spec[-1], query, re.I)]
    # A material request already includes the issuance calculation.
    if any(item['tool'] == 'material_fill' for item in matches):
        matches = [item for item in matches if item['tool'] != 'issuance']
    result = []
    for item in matches[:2]:
        values = _values(item['tool'], query)
        result.append({**item, 'values': values, 'prefill': copy.deepcopy(values),
                       'missing_fields': [key for key in item['required_params'] if key not in values],
                       'missing_sources': list(item['source_files']), 'use_examples': False,
                       'status': 'needs_explicit_inputs', 'executed': False})
    return result
