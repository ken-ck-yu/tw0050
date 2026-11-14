"""Official daily files to `prices_raw` and `shares_issued` (agent A-1, docs/specs/m1_agent_a.md).

Per trading day: TWSE `MI_INDEX` (per-stock table), TPEx `otc` and TWSE `MI_QFIIS`. All rows of the
endpoints are stored (ETFs and receipts included); classification is the universe step's job.
`available_at` is 18:00 Taipei on the trading day for every row.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from twdata.clients.base import DriftError
from twdata.clients.pair import fetch_daily_pair
from twdata.common import paths, sanity, schema, state
from twdata.common.parsing import ParseError, clean_name, parse_int, parse_number
from twdata.common.timeutil import avail_same_day_1800
from twdata.common.views import register_view

BATCH_DAYS = 20
PRICES = "prices_raw"
SHARES = "shares_issued"

# The first and last event_date of every stock in prices_raw (spec: listing_status view).
register_view(
    "listing_status",
    "SELECT market, stock_id, min(event_date) AS first_date, max(event_date) AS last_date "
    "FROM default_prices_raw GROUP BY market, stock_id",
)

# Field lists of the registered eras, copied from tests/fixtures/lead (whitespace is ignored by
# the comparison). Registered only when schema.py has none for the endpoint (see ensure_eras).
_MI_INDEX_FIELDS = (
    "證券代號,證券名稱,成交股數,成交筆數,成交金額,開盤價,最高價,最低價,收盤價,漲跌(+/-),漲跌價差,"
    "最後揭示買價,最後揭示買量,最後揭示賣價,最後揭示賣量,本益比"
).split(",")
_MI_QFIIS_FIELDS = (
    "證券代號,證券名稱,國際證券編碼,發行股數,外資及陸資尚可投資股數,全體外資及陸資持有股數,"
    "外資及陸資尚可投資比率,全體外資及陸資持股比率,外資及陸資共用法令投資上限比率,"
    "陸資法令投資上限比率,與前日異動原因(註),最近一次上市公司申報外資及陸資持股異動日期"
).split(",")
_OTC_HEAD = "代號,名稱,收盤,漲跌,開盤,最高,最低,成交股數,成交金額(元),成交筆數,最後買價".split(",")
_OTC_TAIL = "發行股數,次日漲停價,次日跌停價".split(",")
_OTC_ERA1 = tuple(_OTC_HEAD + ["最後賣價"] + _OTC_TAIL)
_OTC_ERA2 = tuple(_OTC_HEAD + ["最後買量<br>(千股)", "最後賣價", "最後賣量<br>(千股)"] + _OTC_TAIL)
_OTC_ERA3 = tuple(_OTC_HEAD + ["最後買量<br>(張數)", "最後賣價", "最後賣量<br>(張數)"] + _OTC_TAIL)


def ensure_eras() -> None:
    """Register the field-list eras of the three endpoints when schema.py has none.

    Called at the start of `run`, not at import, so importing the module has no global effect.
    """
    plan = {
        "twse.mi_index": [schema.Era(date(2015, 3, 2), None, tuple(_MI_INDEX_FIELDS))],
        "twse.mi_qfiis": [schema.Era(None, None, tuple(_MI_QFIIS_FIELDS))],
        "tpex.otc": [
            schema.Era(None, date(2020, 4, 29), _OTC_ERA1),
            schema.Era(date(2020, 4, 30), date(2025, 1, 9), _OTC_ERA2),
            schema.Era(date(2025, 1, 10), None, _OTC_ERA3),
        ],
    }
    for endpoint, eras in plan.items():
        if not schema.ERAS.get(endpoint):
            for era in eras:
                schema.register_era(endpoint, era)


def _cell(rec: dict, name: str) -> str:
    try:
        v = rec[name]
    except KeyError:
        raise DriftError(f"field {name!r} missing from the row {sorted(rec)}") from None
    return "" if v is None else str(v)


def _no_trade(prices: tuple) -> bool:
    return all(p is None for p in prices)


def _volume_cells(rec: dict, names: tuple, prices: tuple) -> tuple[int, int, int]:
    """volume, turnover, trades. A no-trade row (all prices null) stores zero for an empty cell."""
    out = []
    for name in names:
        v = parse_int(_cell(rec, name))
        if v is None:
            if not _no_trade(prices):
                raise ParseError(f"empty {name} on a row with prices: {rec}")
            v = 0
        out.append(v)
    return out[0], out[1], out[2]


def _price_row(market, d, fetched_at, stock_id, name, prices, vols) -> dict:
    o, h, lo, c = prices
    row = {
        "event_date": d,
        "available_at": avail_same_day_1800(d),
        "fetched_at": fetched_at,
        "market": market,
        "stock_id": stock_id,
        "stock_name": name,
        "open": o,
        "high": h,
        "low": lo,
        "close": c,
        "volume_shares": vols[0],
        "turnover_ntd": vols[1],
        "trades": vols[2],
    }
    sanity.check_price_row(row)
    return row


def twse_price_rows(records: list[dict], d: date, fetched_at: datetime) -> list[dict]:
    rows = []
    for rec in records:
        prices = tuple(
            parse_number(_cell(rec, k)) for k in ("開盤價", "最高價", "最低價", "收盤價")
        )
        vols = _volume_cells(rec, ("成交股數", "成交金額", "成交筆數"), prices)
        rows.append(
            _price_row(
                "TWSE",
                d,
                fetched_at,
                _cell(rec, "證券代號").strip(),
                clean_name(_cell(rec, "證券名稱")),
                prices,
                vols,
            )
        )
    return rows


def tpex_price_rows(records: list[dict], d: date, fetched_at: datetime) -> list[dict]:
    rows = []
    for rec in records:
        prices = tuple(parse_number(_cell(rec, k)) for k in ("開盤", "最高", "最低", "收盤"))
        vols = _volume_cells(rec, ("成交股數", "成交金額(元)", "成交筆數"), prices)
        rows.append(
            _price_row(
                "TPEx",
                d,
                fetched_at,
                _cell(rec, "代號").strip(),
                clean_name(_cell(rec, "名稱")),
                prices,
                vols,
            )
        )
    return rows


def _shares_row(market, d, fetched_at, stock_id, isin, shares) -> dict:
    return {
        "event_date": d,
        "available_at": avail_same_day_1800(d),
        "fetched_at": fetched_at,
        "market": market,
        "stock_id": stock_id,
        "isin": isin,
        "shares_issued": shares,
    }


def twse_shares_rows(records: list[dict], d: date, fetched_at: datetime) -> list[dict]:
    """A row whose 發行股數 is empty is skipped (no shares row, so no market cap that day)."""
    rows = []
    for rec in records:
        shares = parse_int(_cell(rec, "發行股數"))
        if shares is None:
            continue
        isin = _cell(rec, "國際證券編碼").strip() or None
        rows.append(
            _shares_row("TWSE", d, fetched_at, _cell(rec, "證券代號").strip(), isin, shares)
        )
    return rows


def tpex_shares_rows(records: list[dict], d: date, fetched_at: datetime) -> list[dict]:
    rows = []
    for rec in records:
        shares = parse_int(_cell(rec, "發行股數"))
        if shares is None:
            continue
        rows.append(_shares_row("TPEx", d, fetched_at, _cell(rec, "代號").strip(), None, shares))
    return rows


def _at(resp) -> datetime:
    return resp.fetched_at or datetime.now(UTC)


def _flush(ctx, price_rows: list, share_rows: list, days: list[date]) -> None:
    """Raw cache first (so raw survives a crash), then clean files, then state."""
    if not days:
        return
    ctx.cache.flush()
    if price_rows:
        ctx.writers(PRICES).append(price_rows)
    if share_rows:
        ctx.writers(SHARES).append(share_rows)
    lo, hi = min(days), max(days)
    state.mark_dates(ctx.settings, PRICES, lo, hi)
    state.mark_dates(ctx.settings, SHARES, lo, hi)


def run(ctx, start: date, end: date) -> None:
    if ctx.calendar is None:
        raise ValueError("daily_official needs the trading calendar (run the calendar ingest)")
    ensure_eras()
    s = ctx.settings
    pending = [
        d
        for d in ctx.calendar.days_between(start, end)
        if not (state.is_done(s, PRICES, d) and state.is_done(s, SHARES, d))
    ]
    ledger = paths.calendar_ledger(s)
    price_rows: list[dict] = []
    share_rows: list[dict] = []
    days: list[date] = []
    for d in pending:
        tw, tp = fetch_daily_pair(ctx.twse, ctx.tpex, d, "twse.mi_index", "tpex.otc", ledger)
        if tw.rows or tp.rows:  # both empty is a recorded calendar discrepancy: a non-trading day
            qf_records, qf = ctx.twse.mi_qfiis(d)
            tw_rec, tp_rec = tw.records, tp.records
            price_rows += twse_price_rows(tw_rec, d, _at(tw))
            price_rows += tpex_price_rows(tp_rec, d, _at(tp))
            share_rows += twse_shares_rows(qf_records, d, _at(qf))
            share_rows += tpex_shares_rows(tp_rec, d, _at(tp))
        days.append(d)
        if len(days) >= BATCH_DAYS:
            _flush(ctx, price_rows, share_rows, days)
            price_rows, share_rows, days = [], [], []
    _flush(ctx, price_rows, share_rows, days)


DATASETS = {"daily_official": run}
