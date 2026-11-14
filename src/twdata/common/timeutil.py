"""Time rules. Rules return None when the calendar does not reach the needed date."""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo

TAIPEI = ZoneInfo("Asia/Taipei")
UTC = UTC


def at(d: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(d, time(hour, minute), tzinfo=TAIPEI)


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("naive datetime")
    return dt.astimezone(UTC)


_ROC_PATTERNS = [
    re.compile(r"^(\d{2,3})/(\d{1,2})/(\d{1,2})$"),
    re.compile(r"^(\d{2,3})\.(\d{1,2})\.(\d{1,2})$"),
    re.compile(r"^(\d{2,3})年(\d{1,2})月(\d{1,2})日$"),
]


def roc_to_date(text: str) -> date:
    t = text.strip()
    for pat in _ROC_PATTERNS:
        m = pat.match(t)
        if m:
            y, mo, d = (int(x) for x in m.groups())
            return date(y + 1911, mo, d)
    if re.fullmatch(r"\d{6,7}", t):
        y, mo, d = int(t[:-4]), int(t[-4:-2]), int(t[-2:])
        return date(y + 1911, mo, d)
    raise ValueError(f"not a ROC date: {text!r}")


def date_to_roc(d: date) -> str:
    return f"{d.year - 1911:03d}/{d.month:02d}/{d.day:02d}"


def next_trading_day(d: date, cal) -> date | None:
    """First trading day strictly after d, or None when the calendar does not reach it."""
    nxt = cal.next_after(d)
    return nxt


def avail_same_day_1800(d: date) -> datetime:
    return at(d, 18, 0)


def avail_next_day_0830(d: date, cal) -> datetime | None:
    n = next_trading_day(d, cal)
    return None if n is None else at(n, 8, 30)


def avail_revenue(revenue_month: date, cal) -> datetime | None:
    y, m = (
        (revenue_month.year + 1, 1)
        if revenue_month.month == 12
        else (
            revenue_month.year,
            revenue_month.month + 1,
        )
    )
    tenth = date(y, m, 10)
    if cal.last_day() is None or tenth > cal.last_day():
        return None
    if cal.contains_trading(tenth):
        return at(tenth, 18, 0)
    n = next_trading_day(tenth, cal)
    return None if n is None else at(n, 18, 0)


_DEADLINES = {(3, 31): (5, 15, 0), (6, 30): (8, 14, 0), (9, 30): (11, 14, 0), (12, 31): (3, 31, 1)}


def avail_financials(period_end: date, cal) -> datetime | None:
    key = (period_end.month, period_end.day)
    if key not in _DEADLINES:
        raise ValueError(f"period_end must be a quarter end, got {period_end}")
    mo, dy, add_year = _DEADLINES[key]
    deadline = date(period_end.year + add_year, mo, dy)
    return avail_next_day_0830(deadline, cal)


def avail_us(us_date: date) -> datetime:
    return at(us_date + timedelta(days=1), 8, 30)


def avail_announcement(d: date, time_text: str | None, cal) -> datetime | None:
    if time_text:
        m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::(\d{2}))?", time_text.strip())
        if m:
            hh, mm, ss = int(m.group(1)), int(m.group(2)), int(m.group(3) or 0)
            return datetime.combine(d, time(hh, mm, ss), tzinfo=TAIPEI)
    return avail_next_day_0830(d, cal)


def avail_max(*ts: datetime | None) -> datetime | None:
    if any(t is None for t in ts):
        return None
    return max(ts)


def clamp_snapshot_date(snapshot_date: date, first_seen_at: datetime) -> date:
    seen = first_seen_at.astimezone(TAIPEI).date()
    return min(snapshot_date, seen)
