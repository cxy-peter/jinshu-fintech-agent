"""Explicit synthetic calendars verify sending rules, not official holidays."""
from datetime import date

import pytest

from unified.tools import execute


def calendar(**updates):
    return {'version': 'SYNTHETIC-CALENDAR-TEST-v1', 'synthetic': True,
            'coverage_start': '2026-11-01', 'coverage_end': '2027-05-01',
            'holidays': [], 'workdays': [], **updates}


def schedule(cfg, tool='issuance', **updates):
    params = {'start': '2026-11-09', 'term_days': 90, 'frequency_days': 7, 'count': 3, **updates}
    if tool == 'material_fill':
        params['product_name'] = '模拟发行产品（测试）'
    return execute(tool, params, sources={'calendar.json': cfg})['result']


def test_makeup_sunday_remains_forbidden_for_sending():
    result = schedule(calendar(workdays=['2026-11-08']))
    first = result['rows'][0]
    assert first['募集结束日'] == '2026-11-08'
    assert first['候选发送日'] == '2026-11-06'
    assert result['send_plan']['sent'] is False
    assert result['send_plan']['requires_review'] is True
    assert result['send_plan']['business_action_executed'] is False


def test_makeup_saturday_establishment_compatibility_preserved():
    result = schedule(calendar(workdays=['2026-11-07']), start='2026-11-07', count=1)
    assert result['rows'][0]['成立日'] == '2026-11-07'
    assert result['rows'][0]['候选发送日'] == '2026-11-06'


@pytest.mark.parametrize('frequency', [7, 14])
def test_every_send_candidate_excludes_weekends_and_all_listed_holidays(frequency):
    cfg = calendar(holidays=['2026-11-06', '2026-11-20'], workdays=['2026-11-08', '2026-11-22'])
    result = schedule(cfg, frequency_days=frequency)
    assert result['rows'][0]['候选发送日'] == '2026-11-05'
    for row in result['rows']:
        candidate = date.fromisoformat(row['候选发送日'])
        assert candidate.weekday() < 5
        assert row['候选发送日'] not in cfg['holidays']
        assert row['候选发送日'] <= row['募集结束日'] < row['成立日']


def test_unknown_calendar_coverage_does_not_produce_guessed_send_dates():
    result = schedule({'version': 'INCOMPLETE', 'holidays': []})
    assert result['send_plan']['status'] == 'calendar_incomplete'
    assert all(row['候选发送日'] is None for row in result['rows'])
    assert result['constraint_checks']['send_dates_on_weekdays'] is None


def test_send_search_stops_at_calendar_boundary_even_when_issuance_fits():
    # Sunday is a supplied make-up day; finding Friday would leave the coverage.
    with pytest.raises(ValueError, match='发送计划.*覆盖范围'):
        schedule(calendar(coverage_start='2026-11-08', workdays=['2026-11-08']), count=1)


def test_material_preview_reuses_schedule_and_send_plan():
    cfg = calendar(holidays=['2026-11-06'], workdays=['2026-11-08'])
    plain = schedule(cfg)
    material = schedule(cfg, tool='material_fill')
    assert material['rows'] == plain['rows']
    assert material['send_plan'] == plain['send_plan']
    assert material['product_name'] == '模拟发行产品（测试）'


def test_changed_holiday_recomputes_candidate_without_mutating_input():
    cfg = calendar(workdays=['2026-11-08'])
    before = schedule(cfg)
    after = schedule({**cfg, 'version': 'SYNTHETIC-CALENDAR-TEST-v2', 'holidays': ['2026-11-06']})
    assert before['rows'][0]['候选发送日'] == '2026-11-06'
    assert after['rows'][0]['候选发送日'] == '2026-11-05'
    assert cfg['holidays'] == []
