"""Daily price limits (Agent B): TWSE from TWT84U, TPEx from the previous day's `otc` file.

TWT84U for date d lists the limits that apply on d. The TPEx `otc` file of trading day p carries
`次日漲停價` and `次日跌停價`, the limits for the next trading day, so they are stored on that next
day. The no-limit sentinel (9999.95 up, 0.01 down) becomes null. `available_at` is 18:00 on the
event date (the conservative reading for the TPEx rows, which exist one day earlier).
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from twdata.clients.base import DriftError
from twdata.common import state
from twdata.common.parsing import ParseError, parse_number
from twdata.common.sanity import SanityError
from twdata.common.timeutil import avail_same_day_1800

log = logging.getLogger(__name__)

TABLE = "price_limits"
BATCH_DAYS = 20
SENTINEL_UP = 9999.95
SENTINEL_DOWN = 0.01


def _fetched(resp) -> datetime:
    return resp.fetched_at or datetime.now(UTC)


def limit_value(cell, *, up: bool) -> float | None:
    """Parse a limit cell; the sentinel and the empty markers give None."""
    if cell is None:
        return None
    v = parse_number(str(cell))
    if v is None:
        return None
    if up and v >= SENTINEL_UP:
        return None
    if not up and v <= SENTINEL_DOWN:
        return None
    return v


def _field(rec: dict, name: str, source: str):
    if name not in rec:
        raise DriftError(f"{source}: field {name!r} missing from the response")
    return rec[name]


def _make(market: str, stock_id: str, d: date, up, down, fetched: datetime) -> dict:
    if up is not None and down is not None and down > up:
        raise SanityError(f"{market} {stock_id} {d}: limit_down {down} above limit_up {up}")
    return {
        "market": market,
        "stock_id": stock_id,
        "event_date": d,
        "available_at": avail_same_day_1800(d),
        "limit_up": up,
        "limit_down": down,
        "fetched_at": fetched,
    }


def twse_rows(records: list[dict], d: date, fetched: datetime) -> list[dict]:
    """TWT84U rows. The field `開盤競價基準` appears twice, so the records carry `開盤競價基準`
    and `開盤競價基準#2`; neither is stored, only the limits."""
    src = "twse.twt84u"
    out = []
    for r in records:
        sid = str(_field(r, "證券代號", src)).strip()
        out.append(
            _make(
                "TWSE",
                sid,
                d,
                limit_value(_field(r, "漲停價", src), up=True),
                limit_value(_field(r, "跌停價", src), up=False),
                fetched,
            )
        )
    return out


def tpex_rows(records: list[dict], d: date, fetched: datetime) -> list[dict]:
    """Rows from the `otc` file of the previous trading day, stored on `d`."""
    src = "tpex.otc"
    out = []
    for r in records:
        sid = str(_field(r, "代號", src)).strip()
        if not sid:
            raise ParseError(f"{src}: empty stock id")
        out.append(
            _make(
                "TPEx",
                sid,
                d,
                limit_value(_field(r, "次日漲停價", src), up=True),
                limit_value(_field(r, "次日跌停價", src), up=False),
                fetched,
            )
        )
    return out


def day_rows(ctx, d: date) -> list[dict]:
    """TWSE limits for trading day d, and the TPEx limits carried by d's `otc` file, which are
    stored on the next trading day (no TPEx row when the calendar has no later day)."""
    recs, resp = ctx.twse.twt84u(d)
    rows = twse_rows(recs, d, _fetched(resp))
    nxt = ctx.calendar.next_trading_day(d)
    if nxt is None:
        log.warning("price_limits %s: no next trading day in the calendar, TPEx skipped", d)
        return rows
    # Cache first: the raw file normally exists from the daily prices pass. allow_empty serves a
    # cached empty reply (a recorded calendar discrepancy) without a drift error.
    recs, resp = ctx.tpex.otc(d, allow_empty=True)
    rows.extend(tpex_rows(recs, nxt, _fetched(resp)))
    return rows


def run(ctx, start: date, end: date) -> None:
    days = [
        d
        for d in ctx.calendar.days_between(start, end)
        if not state.is_done(ctx.settings, TABLE, d)
    ]
    writer = ctx.writers(TABLE)
    for i in range(0, len(days), BATCH_DAYS):
        batch = days[i : i + BATCH_DAYS]
        rows: list[dict] = []
        for d in batch:
            rows.extend(day_rows(ctx, d))
        writer.append(rows)
        ctx.cache.flush()
        for d in batch:
            state.mark_dates(ctx.settings, TABLE, d, d)


DATASETS = {"price_limits": run}
