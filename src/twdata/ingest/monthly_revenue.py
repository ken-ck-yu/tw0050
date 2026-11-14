"""FinMind monthly revenue to the clean table `monthly_revenue` (agent C, spec m2_agent_c).

One FinMind call per stock for the whole range. `event_date` is the first day of the revenue month
(from `revenue_year` and `revenue_month`, not from the source `date`, which is the first day of
the following month). `available_at` is the statutory deadline rule `avail_revenue`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb

from twdata.clients.base import DriftError
from twdata.common import state, views
from twdata.common.timeutil import TAIPEI, avail_revenue

DATASET = "monthly_revenue"
SOURCE_DATASET = "TaiwanStockMonthRevenue"
EXPECTED_COLUMNS = frozenset(
    {"date", "stock_id", "country", "revenue", "revenue_month", "revenue_year", "create_time"}
)


class MissingCollectionSet(RuntimeError):
    """A required input (the clean table `collection_set`, or the calendar) does not exist."""


def stock_list(ctx) -> list[str]:
    """Distinct stock_id of the collection_set table, sorted."""
    con = duckdb.connect()
    try:
        have = views.register_views(con, ctx.settings)
        if "collection_set" not in have:
            raise MissingCollectionSet(
                "clean table collection_set does not exist; run rebuild-universe first"
            )
        tbl = con.sql(
            "SELECT DISTINCT stock_id FROM default_collection_set ORDER BY stock_id"
        ).to_arrow_table()
    finally:
        con.close()
    return [str(v) for v in tbl.column("stock_id").to_pylist()]


def _int(row: dict, col: str) -> int:
    v = row[col]
    if isinstance(v, bool) or not isinstance(v, int):
        if isinstance(v, float) and v == int(v):
            return int(v)
        raise DriftError(f"{SOURCE_DATASET}: {col} is {v!r}, expected an integer")
    return v


def map_rows(source_rows: list[dict], calendar, fetched_at: datetime) -> list[dict]:
    """Source rows to clean rows. Raises DriftError on a column set other than the fixture's."""
    out = []
    for r in source_rows:
        if set(r) != EXPECTED_COLUMNS:
            raise DriftError(
                f"{SOURCE_DATASET}: columns {sorted(r)} differ from {sorted(EXPECTED_COLUMNS)}"
            )
        year, month = _int(r, "revenue_year"), _int(r, "revenue_month")
        if not 1 <= month <= 12:
            raise DriftError(f"{SOURCE_DATASET}: revenue_month {month} out of range")
        event_date = date(year, month, 1)
        create_time = r["create_time"]
        out.append(
            {
                "event_date": event_date,
                "available_at": avail_revenue(event_date, calendar),
                "fetched_at": fetched_at,
                "stock_id": str(r["stock_id"]),
                "country": str(r["country"]),
                "revenue_year": year,
                "revenue_month": month,
                "revenue": _int(r, "revenue"),
                "create_time": None if create_time in ("", None) else str(create_time),
            }
        )
    return out


def _need_calendar(ctx) -> None:
    if ctx.calendar is None:
        raise MissingCollectionSet("trading calendar not loaded; run the calendar ingest first")


def _fetch_write(ctx, writer, stock_id: str, start: date, end: date | None) -> list[dict]:
    source_rows = ctx.finmind.dataset(SOURCE_DATASET, start, end, data_id=stock_id)
    fetched_at = datetime.now(UTC)  # the time dataset() returned
    rows = map_rows(source_rows, ctx.calendar, fetched_at)
    if rows:
        writer.append(rows, fetched_at)
    return rows


def run(ctx, start: date, end: date) -> None:
    _need_calendar(ctx)
    stocks = stock_list(ctx)
    doc = state.load(ctx.settings, DATASET)
    done = set(doc["completed"]) if doc else set()
    writer = ctx.writers(DATASET)
    for stock_id in stocks:
        if stock_id in done:
            continue
        rows = _fetch_write(ctx, writer, stock_id, start, end)
        # a pending available_at (past the calendar end) keeps the stock open for later runs
        if all(r["available_at"] is not None for r in rows):
            state.mark_stocks(ctx.settings, DATASET, [stock_id])
        ctx.cache.flush()


def _months_back(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) - months
    return date(idx // 12, idx % 12 + 1, 1)


def refresh_recent(ctx, months: int = 3, today: date | None = None) -> None:
    """Re-fetch the last `months` calendar months for every stock in collection_set. Identical
    rows are skipped by the writer; new months are appended, restated values become new rows and
    a pending available_at is filled. State is not read or changed."""
    _need_calendar(ctx)
    today = today or datetime.now(UTC).astimezone(TAIPEI).date()
    start = _months_back(today, months)
    writer = ctx.writers(DATASET)
    for stock_id in stock_list(ctx):
        _fetch_write(ctx, writer, stock_id, start, today)
        ctx.cache.flush()


def run_refresh(ctx, start: date, end: date) -> None:
    """CLI entry: the window is the last 3 months before `end` (`start` is ignored)."""
    refresh_recent(ctx, 3, end)


def _find(row: dict, *needles: str) -> str:
    for k in row:
        if any(n in k for n in needles):
            return k
    raise DriftError(f"t187ap05_L: no field containing any of {needles} in {sorted(row)}")


def check_unit(ctx, stock_id: str, month: date) -> float:
    """Spike S5. Ratio of FinMind `revenue` to the official TWSE value (NT$ thousands) for one
    stock-month. A ratio of 1000 means FinMind is in NT$. The OpenAPI field names are matched by
    substring (company code, data month, current-month revenue) because no sample is saved."""
    month = date(month.year, month.month, 1)
    nxt = date(month.year + (month.month == 12), month.month % 12 + 1, 1)
    fm = ctx.finmind.dataset(SOURCE_DATASET, month, nxt, data_id=stock_id)
    want_ym = (month.year, month.month)
    fm_rows = [r for r in fm if (r["revenue_year"], r["revenue_month"]) == want_ym]
    if len(fm_rows) != 1:
        raise DriftError(f"S5: {len(fm_rows)} FinMind rows for {stock_id} {month:%Y-%m}")
    official, _ = ctx.twse.openapi("/opendata/t187ap05_L")
    if not official:
        raise DriftError("S5: t187ap05_L returned no rows")
    code_k = _find(official[0], "公司代號", "Code")
    ym_k = _find(official[0], "資料年月", "Month", "Date")
    rev_k = _find(official[0], "當月營收", "Revenue")
    want = f"{month.year - 1911}{month.month:02d}"
    hits = [
        r for r in official if str(r[code_k]).strip() == stock_id and str(r[ym_k]).strip() == want
    ]
    if len(hits) != 1:
        raise DriftError(f"S5: {len(hits)} official rows for {stock_id} {want}")
    thousands = float(str(hits[0][rev_k]).replace(",", ""))
    return fm_rows[0]["revenue"] / thousands


DATASETS = {DATASET: run, "monthly_revenue_refresh": run_refresh}
