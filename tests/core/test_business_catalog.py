"""Business discovery must never execute tools or invent missing inputs."""
import pytest

from core.business_catalog import catalog, suggest
from jinshu.tools import FILES
from unified.tools import REQUIRED_PARAMS


def test_catalog_matches_registered_tools_and_is_detached():
    entries = catalog()
    assert {item['id'] for item in entries} == set(REQUIRED_PARAMS)
    for item in entries:
        assert item['required_params'] == REQUIRED_PARAMS[item['id']]
        assert item['source_files'] == FILES[item['id']]
        assert item['boundaries'] and item['source'] and item['examples']
    entries[0]['required_params'].clear()
    assert catalog()[0]['required_params']


def test_explicit_schedule_prefills_only_parameters_stated():
    result = suggest('从2026-11-09起，期限90天，每两周发行，共三期，生成排期')[0]
    assert result['tool'] == 'issuance'
    assert result['values'] == {'start': '2026-11-09', 'term_days': 90, 'count': 3, 'frequency_days': 14}
    assert result['missing_fields'] == []
    assert result['missing_sources'] == ['calendar.json']
    assert result['requires_confirmation'] and not result['executed']
    assert result['use_examples'] is False and result['business_action_executed'] is False


@pytest.mark.parametrize('query', ['FOF是什么', '黄达金融学解释货币政策', '你好', '', None])
def test_general_knowledge_does_not_start_business_tools(query):
    assert suggest(query) == []


def test_missing_ambiguous_and_invalid_inputs_are_not_guessed():
    result = suggest('帮我排期，下周开始，每周或双周都可能，期限90天或者180天，2026-02-30')[0]
    assert result['values'] == {}
    assert set(result['missing_fields']) == {'start', 'term_days', 'count', 'frequency_days'}


def test_material_uses_same_schedule_without_redundant_recommendation():
    result = suggest('为产品名称“模拟一号”生成发行材料及排期，2026年11月9日开始，期限90天，每周3期')
    assert len(result) == 1 and result[0]['tool'] == 'material_fill'
    assert result[0]['values']['product_name'] == '模拟一号'
    assert result[0]['values']['start'] == '2026-11-09'
    assert result[0]['values']['frequency_days'] == 7


def test_benchmark_period_and_product_require_explicit_input():
    result = suggest('对标产品编码SIM0001，从2026-06-01到2026-08-30的净值表现')[0]
    assert result['values'] == {'product': 'SIM0001', 'start': '2026-06-01', 'end': '2026-08-30'}
    result = suggest('同业对标，2026-08-30到2026-06-01')[0]
    assert result['values'] == {} and result['missing_fields'] == ['product', 'start', 'end']


def test_at_most_two_recommendations_even_if_many_tools_mentioned():
    assert len(suggest('排期、周报、财务三表和开户都检查一下')) == 2


@pytest.mark.parametrize('count', ['三四', '十七八', '二二十'])
def test_unusual_chinese_number_does_not_crash(count):
    assert 'count' not in suggest('排期，' + count + '期')[0]['values']
