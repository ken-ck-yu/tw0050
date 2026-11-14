"""Fill the trading-calendar stub for 2015-03-02 to 2015-05-29 (Lead, spec section 12).

For each weekday, request TWSE MI_INDEX and TPEx otc through the standard clients (empty
replies allowed). If both return zero rows the day is a holiday, otherwise a trading day.
Writes `trading_calendar` rows with source "stub". No token needed. 130 requests, run by hand:
    .venv/bin/python scripts/calendar_stub.py
"""

from datetime import UTC, date, datetime, timedelta

from twdata.clients.context import build_context
from twdata.common import state
from twdata.common.config import load_settings

START, END = date(2015, 3, 2), date(2015, 5, 29)


def main() -> int:
    s = load_settings()
    ctx = build_context(s, finmind=False)
    rows = []
    d = START
    while d <= END:
        if d.weekday() < 5:
            tw_rows, _ = ctx.twse.mi_index(d, allow_empty=True)
            tp_rows, _ = ctx.tpex.otc(d, allow_empty=True)
            trading = bool(tw_rows) or bool(tp_rows)
            rows.append({"event_date": d, "is_trading": trading, "source": "stub"})
            print(d, "trading" if trading else "holiday", len(tw_rows), len(tp_rows), flush=True)
        d += timedelta(days=1)
    ctx.cache.flush()
    ctx.writers("trading_calendar").append(rows, datetime.now(UTC))
    state.mark_dates(s, "trading_calendar_stub", START, END)
    print("weekdays", len(rows), "trading", sum(r["is_trading"] for r in rows))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
