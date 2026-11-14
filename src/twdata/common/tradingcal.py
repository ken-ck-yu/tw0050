"""Trading calendar. is_trading raises outside the covered range."""

from __future__ import annotations

import bisect
from collections.abc import Iterable
from datetime import date


class CalendarRangeError(Exception):
    pass


class TradingCalendar:
    def __init__(self, days: Iterable[date]):
        self._days = sorted(set(days))

    def first_day(self) -> date | None:
        return self._days[0] if self._days else None

    def last_day(self) -> date | None:
        return self._days[-1] if self._days else None

    def covers(self, d: date) -> bool:
        return bool(self._days) and self._days[0] <= d <= self._days[-1]

    def contains_trading(self, d: date) -> bool:
        i = bisect.bisect_left(self._days, d)
        return i < len(self._days) and self._days[i] == d

    def is_trading(self, d: date) -> bool:
        if not self.covers(d):
            raise CalendarRangeError(f"{d} is outside the calendar range")
        return self.contains_trading(d)

    def next_after(self, d: date) -> date | None:
        i = bisect.bisect_right(self._days, d)
        return self._days[i] if i < len(self._days) else None

    def next_trading_day(self, d: date) -> date | None:
        return self.next_after(d)

    def prev_trading_day(self, d: date) -> date | None:
        i = bisect.bisect_left(self._days, d)
        return self._days[i - 1] if i > 0 else None

    def days_between(self, start: date, end: date) -> list[date]:
        lo = bisect.bisect_left(self._days, start)
        hi = bisect.bisect_right(self._days, end)
        return self._days[lo:hi]

    def __len__(self) -> int:
        return len(self._days)


def load_calendar(settings) -> TradingCalendar:
    """Trading days from the clean table `trading_calendar` (all sources, is_trading true)."""
    import duckdb

    from twdata.common import views

    con = duckdb.connect()
    try:
        views.register_views(con, settings)
        rows = con.execute(
            "SELECT DISTINCT event_date FROM default_trading_calendar WHERE is_trading"
        ).fetchall()
    finally:
        con.close()
    return TradingCalendar(r[0] for r in rows)
