from datetime import date

import pytest

from twdata.common.tradingcal import CalendarRangeError, TradingCalendar

CAL = TradingCalendar([date(2025, 6, 2), date(2025, 6, 3), date(2025, 6, 6)])


def test_next_and_prev():
    assert CAL.next_trading_day(date(2025, 6, 3)) == date(2025, 6, 6)
    assert CAL.next_trading_day(date(2025, 6, 6)) is None
    assert CAL.prev_trading_day(date(2025, 6, 6)) == date(2025, 6, 3)
    assert CAL.prev_trading_day(date(2025, 6, 2)) is None


def test_is_trading_range():
    assert CAL.is_trading(date(2025, 6, 3)) is True
    assert CAL.is_trading(date(2025, 6, 4)) is False
    with pytest.raises(CalendarRangeError):
        CAL.is_trading(date(2025, 5, 30))
    with pytest.raises(CalendarRangeError):
        CAL.is_trading(date(2025, 6, 7))


def test_days_between():
    assert CAL.days_between(date(2025, 6, 3), date(2025, 6, 6)) == [
        date(2025, 6, 3),
        date(2025, 6, 6),
    ]
