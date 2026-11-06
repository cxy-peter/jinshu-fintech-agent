"""Verify official 2026 input data and the existing strict send-date policy."""
import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from unified.tools import execute


SOURCE = 'https://www.gov.cn/zhengce/zhengceku/202511/content_7047091.htm'
CALENDAR = json.loads((Path(__file__).parents[2] / 'core' / 'calendars' / 'cn_2026.json').read_text(encoding='utf-8'))


def _dates(start, end):
    day = date.fromisoformat(start)
    end = date.fromisoformat(end)
    while day <= end:
        yield day
        day += timedelta(days=1)


def test_official_2026_data_contains_all_published_dates():
    ranges = [('2026-01-01', '2026-01-03'), ('2026-02-15', '2026-02-23'),
              ('2026-04-04', '2026-04-06'), ('2026-05-01', '2026-05-05'),
              ('2026-06-19', '2026-06-21'), ('2026-09-25', '2026-09-27'),
              ('2026-10-01', '2026-10-07')]
    expected = [str(day) for start, end in ranges for day in _dates(start, end)]
    assert CALENDAR['holidays'] == expected
    assert len(expected) == 33 and len(set(expected)) == 33
    assert CALENDAR['workdays'] == ['2026-01-04', '2026-02-14', '2026-02-28',
                                   '2026-05-09', '2026-09-20', '2026-10-10']
    assert CALENDAR['source_url'] == SOURCE and CALENDAR['sources'] == [SOURCE]
    assert CALENDAR['synthetic'] is False
    assert (CALENDAR['coverage_start'], CALENDAR['coverage_end']) == ('2026-01-01', '2026-12-31')


def test_every_2026_start_date_never_produces_a_weekend_or_holiday_send():
    valid = blocked_at_boundary = 0
    for day in _dates('2026-01-01', '2026-12-31'):
        try:
            result = execute('issuance', {'start': str(day), 'term_days': 1,
                             'frequency_days': 7, 'count': 1},
                             sources={'calendar.json': CALENDAR})['result']
        except ValueError as exc:
            # Jan 1-5 require 2025 sending; Dec 31 matures in 2027.
            assert '覆盖范围' in str(exc)
            assert str(day) in {'2026-01-01', '2026-01-02', '2026-01-03', '2026-01-04', '2026-01-05', '2026-12-31'}
            blocked_at_boundary += 1
            continue
        candidate = result['rows'][0]['候选发送日']
        assert date.fromisoformat(candidate).weekday() < 5
        assert candidate not in CALENDAR['holidays']
        assert candidate not in CALENDAR['workdays']  # All official make-up days in 2026 are weekends.
        assert result['send_plan']['sent'] is False
        assert result['send_plan']['business_action_executed'] is False
        valid += 1
    assert (valid, blocked_at_boundary) == (359, 6)


def test_official_calendar_never_extrapolates_into_2027():
    with pytest.raises(ValueError, match='覆盖范围'):
        execute('issuance', {'start': '2026-11-09', 'term_days': 90,
                            'frequency_days': 7, 'count': 1},
                sources={'calendar.json': CALENDAR})
