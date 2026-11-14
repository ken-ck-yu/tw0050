from datetime import date, datetime, timedelta

import pytest

from twdata.common import timeutil as T
from twdata.common.tradingcal import TradingCalendar


def weekday_cal(start, end, holidays=()):
    days = []
    d = start
    while d <= end:
        if d.weekday() < 5 and d not in holidays:
            days.append(d)
        d += timedelta(days=1)
    return TradingCalendar(days)


CAL = weekday_cal(date(2024, 1, 1), date(2026, 12, 31))


def test_roc_forms():
    assert T.roc_to_date("104/06/01") == date(2015, 6, 1)
    assert T.roc_to_date("104.06.12") == date(2015, 6, 12)
    assert T.roc_to_date("1040601") == date(2015, 6, 1)
    assert T.roc_to_date("1100111") == date(2021, 1, 11)
    assert T.roc_to_date("104年06月01日") == date(2015, 6, 1)
    assert T.roc_to_date("113/02/29") == date(2024, 2, 29)
    assert T.date_to_roc(date(2015, 6, 1)) == "104/06/01"
    with pytest.raises(ValueError):
        T.roc_to_date("abc")


def test_next_trading_day_friday_to_monday():
    nxt = T.avail_next_day_0830(date(2025, 6, 20), CAL)
    assert nxt == datetime(2025, 6, 23, 8, 30, tzinfo=T.TAIPEI)


def test_next_day_past_calendar_is_none():
    assert T.avail_next_day_0830(date(2026, 12, 31), CAL) is None


def test_lunar_new_year_gap():
    cal = weekday_cal(
        date(2025, 1, 1),
        date(2025, 3, 1),
        holidays={date(2025, 1, 27) + timedelta(days=i) for i in range(0, 9)},
    )
    nxt = T.next_trading_day(date(2025, 1, 24), cal)
    assert nxt == date(2025, 2, 5)


def test_revenue_saturday_and_tuesday_tenth():
    # 2025-06-10 is a Tuesday: revenue month May 2025
    assert T.avail_revenue(date(2025, 5, 1), CAL) == datetime(2025, 6, 10, 18, 0, tzinfo=T.TAIPEI)
    # 2025-05-10 is a Saturday: revenue month April 2025 -> Monday 2025-05-12
    assert T.avail_revenue(date(2025, 4, 1), CAL) == datetime(2025, 5, 12, 18, 0, tzinfo=T.TAIPEI)
    # beyond the calendar end
    assert T.avail_revenue(date(2026, 12, 1), CAL) is None


def test_financials_deadlines():
    cal = weekday_cal(date(2019, 1, 1), date(2026, 12, 31))
    # Q3 2020: 14 Nov 2020 was a Saturday, strictly after -> Monday 16 Nov 08:30
    assert T.avail_financials(date(2020, 9, 30), cal) == datetime(
        2020, 11, 16, 8, 30, tzinfo=T.TAIPEI
    )
    # annual 2024: deadline 31 Mar 2025 (Monday) -> strictly after -> Tuesday 1 Apr 08:30
    assert T.avail_financials(date(2024, 12, 31), cal) == datetime(
        2025, 4, 1, 8, 30, tzinfo=T.TAIPEI
    )
    with pytest.raises(ValueError):
        T.avail_financials(date(2020, 5, 31), cal)


def test_us_saturday():
    # Friday 2025-06-20 -> Saturday 08:30
    assert T.avail_us(date(2025, 6, 20)) == datetime(2025, 6, 21, 8, 30, tzinfo=T.TAIPEI)


def test_announcement_with_and_without_time():
    assert T.avail_announcement(date(2025, 6, 4), "16:30", CAL) == datetime(
        2025, 6, 4, 16, 30, tzinfo=T.TAIPEI
    )
    assert T.avail_announcement(date(2025, 6, 4), None, CAL) == datetime(
        2025, 6, 5, 8, 30, tzinfo=T.TAIPEI
    )


def test_avail_max_and_clamp():
    a = datetime(2025, 1, 1, tzinfo=T.TAIPEI)
    b = datetime(2025, 1, 2, tzinfo=T.TAIPEI)
    assert T.avail_max(a, b) == b
    assert T.avail_max(a, None) is None
    seen = datetime(2026, 11, 13, 20, 0, tzinfo=T.UTC)  # 2026-11-14 04:00 Taipei
    assert T.clamp_snapshot_date(date(2026, 11, 20), seen) == date(2026, 11, 14)
    assert T.clamp_snapshot_date(date(2026, 11, 1), seen) == date(2026, 11, 1)


def test_same_day_1800():
    assert T.avail_same_day_1800(date(2025, 6, 2)).hour == 18
