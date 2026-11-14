"""Monthly universe: `universe_membership` and `collection_set` (design, section "Universe").

`rebuild(ctx, start, end)` reads the default views of `prices_raw`, `shares_issued`,
`market_cap` and `status_events`, ranks stocks at every month-end and appends the result. The
clean store is append-only, so a rebuild that would drop a row already stored raises
`UniverseConflict`; call it again with `new_version=True` over the full range (it writes `v<N+1>`
of both tables and switches `CURRENT`).
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import yaml

from twdata.common import paths, views
from twdata.common.cleanstore import CleanWriter, current_version, set_current
from twdata.common.config import repo_root
from twdata.common.timeutil import at, avail_max
from twdata.universe.classify import is_common_stock

FIRST_MONTH_END = date(2015, 6, 30)
BENCHMARK_ID = "0050"
WINDOW_DAYS = 60
UNAVAILABLE = 0.0  # sentinel for values with no input (benchmark, watchlist names)


class UniverseConflict(Exception):
    """A rebuild would leave stale rows in an append-only table; use new_version=True."""


def month_ends(cal, start: date, end: date) -> list[date]:
    """Last trading day of each calendar month within [start, end], from 2015-06-30 on.
    The calendar's final month is skipped when the calendar stops before that month's last
    calendar day (its last known day may not be the month-end)."""
    first, last = cal.first_day(), cal.last_day()
    if first is None:
        return []
    last_per_month: dict[tuple[int, int], date] = {}
    for d in cal.days_between(first, last):
        last_per_month[(d.year, d.month)] = d
    out = []
    for (y, m), d in sorted(last_per_month.items()):
        if (y, m) == (last.year, last.month) and last < _month_last_day(y, m):
            continue
        if (y, m) >= (FIRST_MONTH_END.year, FIRST_MONTH_END.month) and start <= d <= end:
            out.append(d)
    return out


def _month_last_day(y: int, m: int) -> date:
    nxt = date(y + (m == 12), m % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


def load_watchlist(path: Path | None = None) -> list[dict]:
    p = path or (repo_root() / "config" / "watchlist.yaml")
    data = yaml.safe_load(p.read_text(encoding="utf-8")) or []
    out = []
    for e in data:
        sd = e["start_date"]
        sd = sd if isinstance(sd, date) else date.fromisoformat(str(sd))
        out.append({**e, "stock_id": str(e["stock_id"]), "start_date": sd})
    return out


def _rows(con, sql: str, params=None) -> list[dict]:
    return con.sql(sql, params=params or []).to_arrow_table().to_pylist()


def _open(ctx):
    con = duckdb.connect()
    return con, views.register_views(con, ctx.settings)


def _window(days_to_date: list[date]) -> list[date]:
    return days_to_date[-WINDOW_DAYS:]


def _latest(pairs: list[tuple[datetime | None, bool]]) -> datetime | None:
    """avail_max over (max available_at, has_null) pairs; None when any input is pending."""
    vals: list[datetime | None] = []
    for mx, has_null in pairs:
        if has_null:
            return None
        if mx is not None:
            vals.append(mx)
    return avail_max(*vals) if vals else None


def compute_month(
    con,
    settings,
    d: date,
    w0: date,
    watchlist: list[dict],
    has_events: bool,
) -> tuple[list[dict], dict]:
    """Rows (without fetched_at) and the shortfall record of one month-end."""
    listed = _rows(con, "SELECT market, stock_id, stock_name FROM px WHERE event_date = ?", [d])
    stats = {
        r["stock_id"]: r
        for r in _rows(
            con,
            "SELECT stock_id, count(*) AS n, median(turnover_ntd) AS med FROM px "
            "WHERE event_date BETWEEN ? AND ? AND turnover_ntd > 0 GROUP BY stock_id",
            [w0, d],
        )
    }
    caps = {r["stock_id"]: r for r in _rows(con, "SELECT * FROM capt WHERE event_date = ?", [d])}
    isins = {
        r["stock_id"]: r["isin"]
        for r in _rows(con, "SELECT stock_id, isin FROM sharet WHERE event_date = ?", [d])
    }
    restricted: set[tuple[str, str]] = set()
    avail: list[tuple[datetime | None, bool]] = [(at(d, 18, 0), False)]
    if has_events:
        ev = _rows(
            con,
            "SELECT market, stock_id, available_at FROM evt "
            "WHERE start_date <= ? AND (end_date IS NULL OR end_date >= ?)",
            [d, d],
        )
        restricted = {(r["market"], r["stock_id"]) for r in ev}
        avail.append(
            (
                max((r["available_at"] for r in ev if r["available_at"] is not None), default=None),
                any(r["available_at"] is None for r in ev),
            )
        )
    available_at = _latest(avail)

    market_of = {r["stock_id"]: r["market"] for r in listed}
    candidates = []
    missing_cap = []
    n_common = 0
    for r in listed:
        sid, market = r["stock_id"], r["market"]
        if not is_common_stock(sid, r["stock_name"]):
            continue
        n_common += 1
        if (market, sid) in restricted:
            continue
        st = stats.get(sid)
        if (
            st is None
            or st["n"] < settings.min_observed_days
            or st["med"] < settings.liquidity_floor_ntd
        ):
            continue
        cap = caps.get(sid)
        if cap is None:
            missing_cap.append(sid)
            continue
        candidates.append((cap["market_cap_ntd"], st["med"], sid, market))
    candidates.sort(key=lambda t: (-t[0], -t[1], t[2]))
    ranked = candidates[: settings.universe_size]

    out: dict[str, dict] = {}
    for i, (cap, med, sid, market) in enumerate(ranked, start=1):
        out[sid] = _member(d, sid, market, isins, cap, med, i, available_at)
    watch_missing = []
    for e in watchlist:
        sid = e["stock_id"]
        if e["start_date"] > d:
            continue
        if sid in out:
            out[sid]["is_watchlist"] = True
            continue
        if sid not in market_of:
            watch_missing.append(sid)
            continue
        out[sid] = _member(
            d, sid, market_of[sid], isins, *_vals(caps, stats, sid), None, available_at
        )
        out[sid]["is_watchlist"] = True
    if BENCHMARK_ID in out:
        out[BENCHMARK_ID]["is_benchmark"] = True
    else:
        out[BENCHMARK_ID] = _member(
            d,
            BENCHMARK_ID,
            market_of.get(BENCHMARK_ID, "TWSE"),
            isins,
            *_vals(caps, stats, BENCHMARK_ID),
            None,
            available_at,
        )
        out[BENCHMARK_ID]["is_benchmark"] = True
    n_ranked = len(ranked)
    record = {
        "members": n_ranked,
        "shortfall": settings.universe_size - n_ranked,
        "null_market_cap": len(missing_cap),
    }
    return list(out.values()), record


def _vals(caps, stats, sid) -> tuple[float, float]:
    cap = caps.get(sid)
    st = stats.get(sid)
    return (cap["market_cap_ntd"] if cap else UNAVAILABLE, st["med"] if st else UNAVAILABLE)


def _member(d, sid, market, isins, cap, med, rank, available_at) -> dict:
    return {
        "month_end": d,
        "stock_id": sid,
        "isin": isins.get(sid),
        "market": market,
        "rank": rank,
        "market_cap_ntd": float(cap),
        "median_turnover_60d": float(med),
        "is_watchlist": False,
        "is_benchmark": False,
        "available_at": available_at,
    }


def compute_collection_set(members: list[dict], fetched_at: datetime) -> list[dict]:
    by: dict[str, dict] = {}
    for m in members:
        c = by.get(m["stock_id"])
        if c is None:
            by[m["stock_id"]] = {
                "stock_id": m["stock_id"],
                "first_month_end": m["month_end"],
                "last_month_end": m["month_end"],
                "ever_watchlist": bool(m["is_watchlist"]),
                "is_benchmark": bool(m["is_benchmark"]),
                "fetched_at": fetched_at,
            }
        else:
            c["first_month_end"] = min(c["first_month_end"], m["month_end"])
            c["last_month_end"] = max(c["last_month_end"], m["month_end"])
            c["ever_watchlist"] = c["ever_watchlist"] or bool(m["is_watchlist"])
            c["is_benchmark"] = c["is_benchmark"] or bool(m["is_benchmark"])
    return sorted(by.values(), key=lambda c: c["stock_id"])


def _write_shortfall(ctx, months: dict[str, dict]) -> Path:
    p = paths.state_file(ctx.settings, "universe_shortfall")
    paths.ensure(p.parent)
    doc: dict = {}
    if p.exists():
        doc = json.loads(p.read_text(encoding="utf-8"))
    doc.update(months)
    doc = dict(sorted(doc.items()))
    tmp = p.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, p)
    return p


def rebuild(
    ctx, start: date, end: date, *, watchlist: list[dict] | None = None, new_version: bool = False
) -> dict:
    """Rebuild the membership of every month-end in [start, end]. Returns a summary."""
    s = ctx.settings
    cal = ctx.calendar
    mends = month_ends(cal, start, end)
    watchlist = load_watchlist() if watchlist is None else watchlist
    summary = {"months": len(mends), "rows": 0, "shortfall_months": []}
    if not mends:
        return summary
    con, have = _open(ctx)
    try:
        for t in ("prices_raw", "shares_issued", "market_cap"):
            if t not in have:
                raise RuntimeError(f"universe: table {t} has no clean files")
        all_days = cal.days_between(cal.first_day(), mends[-1])
        windows = {d: _window([x for x in all_days if x <= d])[0] for d in mends}
        lo, hi = min(windows.values()), mends[-1]
        con.execute(
            "CREATE TEMP TABLE px AS SELECT market, stock_id, stock_name, event_date, close, "
            "turnover_ntd, available_at FROM default_prices_raw WHERE event_date BETWEEN ? AND ?",
            [lo, hi],
        )
        ph = ", ".join("?" for _ in mends)
        con.execute(
            "CREATE TEMP TABLE capt AS SELECT stock_id, event_date, market_cap_ntd, available_at "
            f"FROM default_market_cap WHERE event_date IN ({ph})",
            mends,
        )
        con.execute(
            "CREATE TEMP TABLE sharet AS SELECT stock_id, isin, event_date, available_at "
            f"FROM default_shares_issued WHERE event_date IN ({ph})",
            mends,
        )
        has_events = "status_events" in have
        if has_events:
            con.execute(
                "CREATE TEMP TABLE evt AS SELECT market, stock_id, start_date, end_date, "
                "available_at FROM default_status_events "
                "WHERE status_type IN ('disposition', 'changed_trading')"
            )
        members: list[dict] = []
        records: dict[str, dict] = {}
        for d in mends:
            rows, rec = compute_month(con, s, d, windows[d], watchlist, has_events)
            members += rows
            records[d.isoformat()] = rec
            if rec["shortfall"] > 0:
                summary["shortfall_months"].append(d.isoformat())
        existing_members: list[dict] = []
        existing_cs_keys: set[tuple] = set()
        if not new_version:
            if "universe_membership" in have:
                existing_members = _rows(
                    con,
                    "SELECT month_end, stock_id, is_watchlist, is_benchmark "
                    "FROM default_universe_membership",
                )
            if "collection_set" in have:
                existing_cs_keys = {
                    (r["stock_id"], r["first_month_end"])
                    for r in _rows(
                        con, "SELECT stock_id, first_month_end FROM default_collection_set"
                    )
                }
    finally:
        con.close()

    now = datetime.now(UTC)
    new_months = set(mends)
    new_keys = {(m["month_end"], m["stock_id"]) for m in members}
    stale = [
        (r["month_end"], r["stock_id"])
        for r in existing_members
        if r["month_end"] in new_months and (r["month_end"], r["stock_id"]) not in new_keys
    ]
    if stale:
        raise UniverseConflict(
            f"{len(stale)} stored membership rows would be stale, first {stale[0]}; "
            "rerun over the full range with new_version=True"
        )
    kept = [r for r in existing_members if r["month_end"] not in new_months]
    cs = compute_collection_set(kept + members, now)
    stale_cs = existing_cs_keys - {(c["stock_id"], c["first_month_end"]) for c in cs}
    if stale_cs:
        raise UniverseConflict(
            f"{len(stale_cs)} stored collection_set rows would be stale; "
            "rerun over the full range with new_version=True"
        )

    for m in members:
        m["fetched_at"] = now
    versions = {}
    for table, rows in (("universe_membership", members), ("collection_set", cs)):
        ver = current_version(s, table) + 1 if new_version else None
        written = CleanWriter(s, table, version=ver).append(rows, now)
        if new_version and written:
            set_current(s, table, ver)
        versions[table] = ver
    _write_shortfall(ctx, records)
    summary["rows"] = len(members)
    summary["collection_set_rows"] = len(cs)
    return summary


def assert_universe(rows, shortfall=None, universe_size: int = 200) -> None:
    """Gate check on the rows rebuild() wrote: each month-end has `universe_size` ranked members
    (or a recorded shortfall in the optional universe_shortfall.json mapping) and 2330."""
    by: dict = {}
    for r in rows:
        by.setdefault(r["month_end"], []).append(r)
    errors = []
    for me in sorted(by):
        rs = by[me]
        ranked = sum(1 for r in rs if r["rank"] is not None)
        rec = (shortfall or {}).get(me.isoformat()) or {}
        if ranked > universe_size:
            errors.append(f"{me}: {ranked} ranked members, more than {universe_size}")
        elif ranked < universe_size and not rec.get("shortfall"):
            errors.append(f"{me}: {ranked} ranked members and no shortfall recorded")
        if not any(r["stock_id"] == "2330" for r in rs):
            errors.append(f"{me}: 2330 is missing")
    if not by:
        errors.append("no universe rows")
    if errors:
        raise AssertionError("; ".join(errors))
