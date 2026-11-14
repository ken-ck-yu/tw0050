"""Status events: disposition (TWSE punish, TPEx disposal) and TPEx changed trading (chtm).

Table `status_events` (docs/data_dictionary/a_universe.md). Rows are written for every code,
common stock or not: filtering is the universe's job.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

import duckdb

from twdata.clients.base import DriftError
from twdata.common import state, views
from twdata.common.parsing import ParseError
from twdata.common.timeutil import avail_next_day_0830, roc_to_date

DATASET = "status_events"
CHTM_FLAGS = ("變更交易", "分盤交易", "屬管理股票")
_TILDES = ("～", "~")


def parse_roc_range(text: str) -> tuple[date, date]:
    """`104/09/25～104/10/12` (TWSE, full-width tilde) or `104/06/30~104/07/13` (TPEx)."""
    t = (text or "").strip()
    for sep in _TILDES:
        if sep in t:
            parts = [p.strip() for p in t.split(sep)]
            break
    else:
        raise ParseError(f"not a date range: {text!r}")
    if len(parts) != 2:
        raise ParseError(f"not a date range: {text!r}")
    try:
        lo, hi = roc_to_date(parts[0]), roc_to_date(parts[1])
    except ValueError as e:
        raise ParseError(f"not a date range: {text!r}") from e
    if hi < lo:
        raise ParseError(f"range ends before it starts: {text!r}")
    return lo, hi


def _roc(text: str, what: str) -> date:
    try:
        return roc_to_date(text)
    except ValueError as e:
        raise ParseError(f"{what}: {text!r}") from e


def _need(records: list[dict], names: tuple[str, ...], where: str) -> None:
    if records:
        missing = [n for n in names if n not in records[0]]
        if missing:
            raise DriftError(f"{where}: fields missing {missing}")


def disposition_rows(
    market: str, records: list[dict], *, range_key: str, detail_key: str, cal, fetched_at
) -> list[dict]:
    """Map disposition records to status_events rows. Rows with an empty code (TPEx pads the
    list with blank rows) are skipped. When one key (market, code, start_date) occurs more than
    once, the first row in response order is kept."""
    _need(records, ("公布日期", "證券代號", range_key, detail_key), f"{market} disposition")
    best: dict[tuple, dict] = {}
    for rec in records:
        code = str(rec["證券代號"]).strip()
        if not code:
            continue
        announce = _roc(str(rec["公布日期"]), "announce date")
        start, end = parse_roc_range(str(rec[range_key]))
        detail = str(rec[detail_key]).strip() or None
        row = {
            "event_date": announce,
            "available_at": avail_next_day_0830(announce, cal),
            "market": market,
            "stock_id": code,
            "status_type": "disposition",
            "announce_date": announce,
            "start_date": start,
            "end_date": end,
            "detail": detail,
            "fetched_at": fetched_at,
        }
        key = (market, code, start)
        old = best.get(key)
        if old is None:  # first row in response order wins
            best[key] = row
    return list(best.values())


def _flagged(rec: dict) -> bool:
    return any(str(rec.get(f, "")).strip() for f in CHTM_FLAGS)


def chtm_runs(
    days: list[date],
    day_records: dict[date, list[dict]],
    seeds: dict[str, tuple[date, str | None]] | None = None,
    fetched: dict[date, datetime] | None = None,
) -> list[dict]:
    """Runs of consecutive trading days per stock. `days` are consecutive trading days.
    `seeds` maps a stock to (start_date, detail) of a stored run that ended on the trading day
    before days[0]; a seed that is not extended into `days` produces no output (it is already
    stored). Returns dicts with stock_id, start_date, end_date, detail, fetched_at (the response
    time of the last day in the run). A run still open on the last day ends there."""
    open_runs: dict[str, dict] = {
        sid: {"start": start, "end": None, "detail": detail, "fetched_at": None}
        for sid, (start, detail) in (seeds or {}).items()
    }
    out: list[dict] = []

    def close(sid: str) -> None:
        r = open_runs.pop(sid)
        if r["end"] is None:
            return  # an untouched seed
        out.append(
            {
                "stock_id": sid,
                "start_date": r["start"],
                "end_date": r["end"],
                "detail": r["detail"],
                "fetched_at": r["fetched_at"],
            }
        )

    for d in days:
        flagged: dict[str, None] = {}
        for rec in day_records.get(d, []):
            sid = str(rec.get("證券代號", "")).strip()
            if sid and _flagged(rec):
                flagged[sid] = None
        for sid in [s for s in open_runs if s not in flagged]:
            close(sid)
        for sid, f in flagged.items():
            r = open_runs.get(sid)
            if r is None:
                r = open_runs[sid] = {"start": d, "end": None, "detail": f, "fetched_at": None}
            r["end"] = d
            r["fetched_at"] = (fetched or {}).get(d)
    for sid in list(open_runs):
        close(sid)
    return out


def _read_seeds(ctx, prev_day: date | None) -> dict[str, tuple[date, str | None]]:
    """Runs of the store whose end_date is the trading day before the first day processed."""
    if prev_day is None:
        return {}
    con = duckdb.connect()
    try:
        if "status_events" not in views.register_views(con, ctx.settings):
            return {}
        got = con.execute(
            "SELECT stock_id, start_date, detail FROM default_status_events "
            "WHERE market = 'TPEx' AND status_type = 'changed_trading' AND end_date = ?",
            [prev_day],
        ).fetchall()
    finally:
        con.close()
    return {sid: (start, detail) for sid, start, detail in got}


def _write(ctx, rows: list[dict]) -> None:
    if rows:
        ctx.writers("status_events").append(rows, datetime.now(UTC))


def _years(start: date, end: date):
    for y in range(start.year, end.year + 1):
        yield max(start, date(y, 1, 1)), min(end, date(y, 12, 31))


def run_dispositions(ctx, start: date, end: date) -> None:
    for s, e in _years(start, end):
        recs, resp = ctx.twse.punish(s, e)
        _write(
            ctx,
            disposition_rows(
                "TWSE",
                recs,
                range_key="處置起迄時間",
                detail_key="處置措施",
                cal=ctx.calendar,
                fetched_at=resp.fetched_at or datetime.now(UTC),
            ),
        )
        recs, resp = ctx.tpex.disposal(s, e)
        _write(
            ctx,
            disposition_rows(
                "TPEx",
                recs,
                range_key="處置起訖時間",
                detail_key="處置原因",
                cal=ctx.calendar,
                fetched_at=resp.fetched_at or datetime.now(UTC),
            ),
        )
        ctx.cache.flush()


def run_changed_trading(ctx, start: date, end: date) -> None:
    cal = ctx.calendar
    days = cal.days_between(start, end)
    first_open = next((d for d in days if not state.is_done(ctx.settings, DATASET, d)), None)
    if first_open is None:
        return
    days = [d for d in days if d >= first_open]
    for y in sorted({d.year for d in days}):
        chunk = [d for d in days if d.year == y]
        seeds = _read_seeds(ctx, cal.prev_trading_day(chunk[0]))
        recs: dict[date, list[dict]] = {}
        fetched: dict[date, datetime] = {}
        for i, d in enumerate(chunk):
            rows, resp = ctx.tpex.chtm(d, allow_empty=True)
            _need(rows, ("證券代號", *CHTM_FLAGS), "TPEx chtm")
            recs[d] = rows
            fetched[d] = resp.fetched_at or datetime.now(UTC)
            if (i + 1) % 20 == 0:
                ctx.cache.flush()
        ctx.cache.flush()
        out = []
        for r in chtm_runs(chunk, recs, seeds, fetched):
            start_d = r["start_date"]
            out.append(
                {
                    "event_date": start_d,
                    "available_at": avail_next_day_0830(start_d, cal),
                    "market": "TPEx",
                    "stock_id": r["stock_id"],
                    "status_type": "changed_trading",
                    "announce_date": None,
                    "start_date": start_d,
                    "end_date": r["end_date"],
                    "detail": r["detail"],
                    "fetched_at": r["fetched_at"] or fetched[chunk[-1]],
                }
            )
        _write(ctx, out)
        state.mark_dates(ctx.settings, DATASET, chunk[0], chunk[-1])


def run(ctx, start: date, end: date) -> None:
    run_dispositions(ctx, start, end)
    run_changed_trading(ctx, start, end)


DATASETS = {"status_events": run}
