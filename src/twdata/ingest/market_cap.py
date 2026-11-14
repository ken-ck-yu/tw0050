"""Derived `market_cap` table (agent A-1, docs/specs/m1_agent_a.md).

One row per (stock, date) where `prices_raw` has a close and `shares_issued` has a row on the
same date and market. No carry-forward. `available_at` is the later of the two inputs.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb

from twdata.common import views
from twdata.common.cleanstore import KeyUniquenessError
from twdata.common.timeutil import avail_max

TABLE = "market_cap"

_SQL = """
SELECT p.market AS market, p.stock_id AS stock_id, p.event_date AS event_date, p.close AS close,
       s.shares_issued AS shares_issued,
       p.available_at AS price_available_at, s.available_at AS shares_available_at
FROM default_prices_raw p
JOIN default_shares_issued s
  ON s.market = p.market AND s.stock_id = p.stock_id AND s.event_date = p.event_date
WHERE p.close IS NOT NULL AND p.event_date BETWEEN ? AND ?
ORDER BY p.event_date, p.stock_id
"""


def _months(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        lo = max(start, date(y, m, 1))
        nxt = date(y + (m == 12), m % 12 + 1, 1)
        hi = min(end, date.fromordinal(nxt.toordinal() - 1))
        yield lo, hi
        y, m = nxt.year, nxt.month


def market_cap_rows(records: list[dict], fetched_at: datetime) -> list[dict]:
    seen: dict[tuple, str] = {}
    for r in records:  # market_cap is keyed (stock_id, event_date): one market per stock and day
        k = (r["stock_id"], r["event_date"])
        if k in seen and seen[k] != r["market"]:
            raise KeyUniquenessError(f"market_cap: {k} appears on two markets")
        seen[k] = r["market"]
    rows = []
    for r in records:
        rows.append(
            {
                "event_date": r["event_date"],
                "fetched_at": fetched_at,
                "available_at": avail_max(r["price_available_at"], r["shares_available_at"]),
                "stock_id": r["stock_id"],
                "close": r["close"],
                "shares_issued": r["shares_issued"],
                "market_cap_ntd": r["close"] * r["shares_issued"],
            }
        )
    return rows


def run(ctx, start: date, end: date) -> None:
    con = duckdb.connect()
    try:
        con.execute("SET TimeZone = 'Asia/Taipei'")
        tables = views.register_views(con, ctx.settings)
        if "prices_raw" not in tables or "shares_issued" not in tables:
            return  # nothing to derive from yet
        writer = ctx.writers(TABLE)
        for lo, hi in _months(start, end):
            records = con.sql(_SQL, params=[lo, hi]).to_arrow_table().to_pylist()
            if records:
                writer.append(market_cap_rows(records, datetime.now(UTC)))
    finally:
        con.close()


DATASETS = {TABLE: run}
