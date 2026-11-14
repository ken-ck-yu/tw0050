"""Benchmark total-return indexes (Agent B).

TAIEX_TR and TAIWAN50_TR come from the index table of the TWSE `MI_INDEX` reply (endpoint
`twse.mi_index_tr`, normally served from the cache). TPEX_TR comes from FinMind
`TaiwanStockTotalReturnIndex` with `data_id = "TPEx"` when a FinMind client is available.
`available_at` is 18:00 on the event date.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime

from twdata.clients.base import DriftError
from twdata.common import state
from twdata.common.parsing import parse_number
from twdata.common.timeutil import avail_same_day_1800

log = logging.getLogger(__name__)

TABLE = "benchmark_index"
BATCH_DAYS = 20
TWSE_ROWS = {
    "發行量加權股價報酬指數": "TAIEX_TR",
    "臺灣50報酬指數": "TAIWAN50_TR",
}
FINMIND_DATASET = "TaiwanStockTotalReturnIndex"
FINMIND_DATA_ID = "TPEx"


def _fetched(resp) -> datetime:
    return resp.fetched_at or datetime.now(UTC)


def twse_rows(records: list[dict], d: date, fetched: datetime) -> list[dict]:
    """The two wanted rows of the index table; a missing one is drift (stop and report)."""
    found: dict[str, float] = {}
    for r in records:
        name = str(r.get("報酬指數", "")).strip()
        if name in TWSE_ROWS:
            if "收盤指數" not in r:
                raise DriftError("twse.mi_index_tr: field '收盤指數' missing")
            v = parse_number(str(r["收盤指數"]))
            if v is None:
                raise DriftError(f"twse.mi_index_tr {d}: no value for {name}")
            found[TWSE_ROWS[name]] = v
    missing = sorted(set(TWSE_ROWS.values()) - set(found))
    if missing:
        raise DriftError(f"twse.mi_index_tr {d}: index rows missing: {missing}")
    return [
        {
            "index_id": index_id,
            "event_date": d,
            "available_at": avail_same_day_1800(d),
            "value": value,
            "fetched_at": fetched,
        }
        for index_id, value in found.items()
    ]


def run_twse(ctx, start: date, end: date) -> None:
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
            recs, resp = ctx.twse.mi_index_tr(d)
            rows.extend(twse_rows(recs, d, _fetched(resp)))
        writer.append(rows)
        ctx.cache.flush()
        for d in batch:
            state.mark_dates(ctx.settings, TABLE, d, d)


def tpex_tr_rows(records: list[dict], fetched: datetime) -> list[dict]:
    out = []
    for r in records:
        for k in ("date", "price"):
            if k not in r:
                raise DriftError(f"finmind {FINMIND_DATASET}: field {k!r} missing")
        d = date.fromisoformat(str(r["date"]))
        out.append(
            {
                "index_id": "TPEX_TR",
                "event_date": d,
                "available_at": avail_same_day_1800(d),
                "value": float(r["price"]),
                "fetched_at": fetched,
            }
        )
    return out


def run_tpex(ctx, start: date, end: date) -> None:
    if ctx.finmind is None:
        log.warning("benchmark_index: no FinMind client, TPEX_TR skipped")
        return
    writer = ctx.writers(TABLE)
    for y in range(start.year, end.year + 1):
        ws, we = max(start, date(y, 1, 1)), min(end, date(y, 12, 31))
        recs = ctx.finmind.dataset(FINMIND_DATASET, ws, we, data_id=FINMIND_DATA_ID)
        rows = tpex_tr_rows(recs, datetime.now(UTC))
        if rows:
            writer.append(rows)
    ctx.cache.flush()


def run(ctx, start: date, end: date) -> None:
    run_twse(ctx, start, end)
    run_tpex(ctx, start, end)


DATASETS = {"benchmark_index": run}
