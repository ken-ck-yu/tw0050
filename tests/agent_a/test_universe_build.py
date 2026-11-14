"""Universe rules on small synthetic clean tables (offline)."""

import dataclasses
import json
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace

import duckdb
import pytest

from twdata.common import config, paths, views
from twdata.common.cleanstore import CleanWriter, current_version
from twdata.common.timeutil import at
from twdata.common.tradingcal import TradingCalendar
from twdata.universe import build

FETCHED = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)
JUNE, JULY = date(2015, 6, 30), date(2015, 7, 31)
FLOOR = 20_000_000


def weekdays(a: date, b: date, skip=()) -> list[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5 and d not in skip:
            out.append(d)
        d += timedelta(days=1)
    return out


CAL = TradingCalendar(weekdays(date(2015, 3, 2), date(2015, 8, 31)))


def settings(tmp_path, **kw):
    s = config.load_settings(data_dir_override=str(tmp_path))
    return dataclasses.replace(s, **kw)


def ctx_for(s, cal=CAL):
    return SimpleNamespace(
        settings=s, calendar=cal, writers=lambda t: CleanWriter(s, t), cache=None
    )


def stock(
    sid, *, market="TWSE", name=None, turnover=30_000_000, cap=None, first=None, zero_from=None
):
    return {
        "sid": sid,
        "market": market,
        "name": name or f"N{sid}",
        "turnover": turnover,
        "cap": cap,
        "first": first,
        "zero_from": zero_from,
    }


def write_tables(s, stocks, cal=CAL, cap_dates=(JUNE, JULY), events=()):
    prices, caps, shares = [], [], []
    for st in stocks:
        for d in cal.days_between(date(2015, 3, 2), date(2015, 8, 31)):
            if st["first"] and d < st["first"]:
                continue
            t = st["turnover"]
            if st["zero_from"] and st["zero_from"][0] <= d <= st["zero_from"][1]:
                t = 0
            px = None if t == 0 else 10.0
            prices.append(
                {
                    "event_date": d,
                    "available_at": at(d, 18, 0),
                    "market": st["market"],
                    "stock_id": st["sid"],
                    "stock_name": st["name"],
                    "open": px,
                    "high": px,
                    "low": px,
                    "close": px,
                    "volume_shares": 0 if t == 0 else 1000,
                    "turnover_ntd": t,
                    "trades": 0 if t == 0 else 5,
                }
            )
            if d in cap_dates and st["cap"] is not None:
                caps.append(
                    {
                        "event_date": d,
                        "available_at": at(d, 18, 0),
                        "stock_id": st["sid"],
                        "close": 10.0,
                        "shares_issued": int(st["cap"] / 10),
                        "market_cap_ntd": float(st["cap"]),
                    }
                )
                shares.append(
                    {
                        "event_date": d,
                        "available_at": at(d, 18, 0),
                        "market": st["market"],
                        "stock_id": st["sid"],
                        "isin": f"TW{st['sid']}" if st["market"] == "TWSE" else None,
                        "shares_issued": int(st["cap"] / 10),
                    }
                )
    CleanWriter(s, "prices_raw").append(prices, FETCHED)
    CleanWriter(s, "market_cap").append(caps, FETCHED)
    CleanWriter(s, "shares_issued").append(shares, FETCHED)
    if events:
        CleanWriter(s, "status_events").append(list(events), FETCHED)


def event(sid, kind, start, end, market="TWSE", available=None):
    return {
        "event_date": start,
        "available_at": available if available is not None else at(start, 8, 30),
        "market": market,
        "stock_id": sid,
        "status_type": kind,
        "announce_date": None,
        "start_date": start,
        "end_date": end,
        "detail": None,
    }


def membership(s):
    con = duckdb.connect()
    try:
        views.register_views(con, s)
        rows = con.execute(
            'SELECT month_end, stock_id, isin, market, "rank", market_cap_ntd, '
            "median_turnover_60d, is_watchlist, is_benchmark, available_at "
            "FROM default_universe_membership ORDER BY 1, 2"
        ).fetchall()
    finally:
        con.close()
    keys = ("month_end", "stock_id", "isin", "market", "rank", "cap", "med", "wl", "bm", "av")
    return [dict(zip(keys, r, strict=True)) for r in rows]


def by_month(rows, d):
    return {r["stock_id"]: r for r in rows if r["month_end"] == d}


def files(s, table):
    return sorted((s.data_dir / "clean" / table).rglob("*.parquet"))


def rule_stocks():
    return [
        stock("2330", cap=1000, turnover=100_000_000),
        stock("1001", cap=900),
        stock("1002", cap=800),
        stock("1003", cap=800, turnover=40_000_000),  # ties with 1002, higher turnover wins
        stock("1004", cap=100),  # 5th by cap
        stock("1005", cap=950, turnover=10_000_000),  # below the floor
        stock("1006", cap=960, first=date(2015, 6, 1)),  # 22 observed days < 40
        stock("1007", cap=990),  # under disposition on June 30 only
        stock("1008"),  # no market cap
        stock("1009", cap=970, zero_from=(date(2015, 4, 20), date(2015, 6, 30))),  # suspended
        stock("9103", cap=999, name="美德-DR"),  # depositary receipt
        stock("0050", cap=5000, turnover=5_000_000, name="元大台灣50"),
        stock("6488", market="TPEx", cap=700),
        stock("00878", cap=9999),  # ETF
    ]


def events_for_rules():
    return [
        event("1007", "disposition", date(2015, 6, 25), date(2015, 7, 8)),
        event("1004", "changed_trading", date(2015, 7, 1), date(2015, 7, 31)),
    ]


# ---- month-ends -------------------------------------------------------------------------


def test_month_ends_from_calendar():
    cal = TradingCalendar(weekdays(date(2015, 3, 2), date(2015, 9, 30), skip={JUNE}))
    me = build.month_ends(cal, date(2015, 1, 1), date(2015, 12, 31))
    # March to May are before the first universe month; June 30 is a holiday here
    assert me == [date(2015, 6, 29), JULY, date(2015, 8, 31), date(2015, 9, 30)]
    assert build.month_ends(cal, date(2015, 7, 1), date(2015, 8, 31)) == [JULY, date(2015, 8, 31)]


def test_month_ends_skip_incomplete_final_month():
    cal = TradingCalendar(weekdays(date(2015, 3, 2), date(2015, 9, 15)))
    me = build.month_ends(cal, date(2015, 6, 1), date(2015, 12, 31))
    assert me[-1] == date(2015, 8, 31)


# ---- rules ------------------------------------------------------------------------------


def test_rules_ranking_exclusions_watchlist_benchmark(tmp_path):
    s = settings(tmp_path, universe_size=3)
    write_tables(s, rule_stocks(), events=events_for_rules())
    wl = [
        {"stock_id": "1004", "start_date": date(2015, 6, 30), "reason": "r", "added_on": "x"},
        {"stock_id": "2330", "start_date": date(2015, 7, 15), "reason": "r", "added_on": "x"},
        {"stock_id": "7777", "start_date": date(2015, 6, 1), "reason": "r", "added_on": "x"},
    ]
    summary = build.rebuild(ctx_for(s), date(2015, 6, 1), date(2015, 8, 31), watchlist=wl)
    assert summary["months"] == 3
    rows = membership(s)
    jun = by_month(rows, JUNE)

    # ranked: cap descending; 1007 (disposition), 1005 (floor), 1006 (<40 days), 1009
    # (suspended days are not observed), 1008 (no cap), DR, ETF and 0050 are not ranked
    ranked = {sid: r["rank"] for sid, r in jun.items() if r["rank"] is not None}
    assert ranked == {"2330": 1, "1001": 2, "1003": 3}  # 1003 beats 1002 on turnover
    assert "1002" not in jun  # fourth by cap and turnover: cut at universe_size
    for absent in ("1005", "1006", "1007", "1008", "1009", "9103", "00878", "6488"):
        assert absent not in jun or jun[absent]["rank"] is None

    # watchlist extra, below the ranking, with its own numbers; 7777 is not listed
    assert jun["1004"]["rank"] is None and jun["1004"]["wl"] is True
    assert jun["1004"]["cap"] == 100 and jun["1004"]["market"] == "TWSE"
    assert jun["2330"]["wl"] is False  # applies from the first month-end after 2015-07-15
    # benchmark: always a row, no rank, whatever the floor says
    assert jun["0050"]["rank"] is None and jun["0050"]["bm"] is True
    assert jun["0050"]["cap"] == 5000 and jun["0050"]["med"] == 5_000_000
    assert jun["2330"]["isin"] == "TW2330" and jun["2330"]["med"] == 100_000_000
    assert jun["2330"]["av"] == at(JUNE, 18, 0)

    jul = by_month(rows, JULY)
    # 1007's disposition ended on July 8; 1004 is under changed trading on July 31
    assert {sid for sid, r in jul.items() if r["rank"] is not None} == {"2330", "1007", "1006"}
    assert jul["2330"]["rank"] == 1 and jul["2330"]["wl"] is True  # ranked keeps its rank
    assert "1001" not in jul  # fourth by cap, cut
    assert jul["1004"]["wl"] is True and jul["1004"]["rank"] is None  # watchlist ignores filters
    # benchmark appears every month-end, including August (no market cap rows there)
    aug = by_month(rows, date(2015, 8, 31))
    assert aug["0050"]["bm"] is True

    sf = json.loads(paths.state_file(s, "universe_shortfall").read_text("utf-8"))
    assert sf["2015-06-30"] == {"members": 3, "shortfall": 0, "null_market_cap": 1}
    assert sf["2015-08-31"] == {"members": 0, "shortfall": 3, "null_market_cap": 10}
    assert aug["0050"]["cap"] == 0.0 and aug["0050"]["med"] > 0  # 0.0 means unavailable

    # collection_set: one row per stock over all months
    con = duckdb.connect()
    views.register_views(con, s)
    cs = {
        r[0]: r
        for r in con.execute(
            "SELECT stock_id, first_month_end, last_month_end, ever_watchlist, is_benchmark "
            "FROM default_collection_set"
        ).fetchall()
    }
    assert cs["2330"][1:] == (JUNE, date(2015, 8, 31), True, False)
    assert cs["0050"][4] is True and cs["0050"][1] == JUNE
    assert cs["1004"][3] is True and cs["2330"][3] is True
    assert "1008" not in cs and "9103" not in cs


def test_tie_break_by_stock_id_after_turnover(tmp_path):
    s = settings(tmp_path, universe_size=2)
    write_tables(
        s,
        [
            stock("2330", cap=1000),
            stock("1102", cap=800),
            stock("1101", cap=800),
            stock("1103", cap=800),
        ],
    )
    build.rebuild(ctx_for(s), JUNE, JUNE, watchlist=[])
    jun = by_month(membership(s), JUNE)
    assert jun["2330"]["rank"] == 1 and jun["1101"]["rank"] == 2 and "1102" not in jun


def test_floor_boundary_and_shortfall_gate(tmp_path):
    s = settings(tmp_path, universe_size=10)
    write_tables(
        s,
        [
            stock("2330", cap=1000, turnover=100_000_000),
            stock("1010", cap=500, turnover=FLOOR),  # exactly at the floor: in
            stock("1011", cap=600, turnover=FLOOR - 1),  # just below: out
            stock("1012", cap=400, first=date(2015, 5, 6)),  # exactly 40 observed days: in
            stock("1013", cap=450, first=date(2015, 5, 7)),  # 39 days: out
        ],
    )
    build.rebuild(ctx_for(s), JUNE, JUNE, watchlist=[])
    rows = membership(s)
    jun = by_month(rows, JUNE)
    assert {k for k, r in jun.items() if r["rank"]} == {"2330", "1010", "1012"}
    assert jun["1012"]["rank"] == 3
    sf = json.loads(paths.state_file(s, "universe_shortfall").read_text("utf-8"))
    assert sf["2015-06-30"]["shortfall"] == 7
    build.assert_universe(rows, sf, universe_size=10)
    with pytest.raises(AssertionError, match="no shortfall recorded"):
        build.assert_universe(rows, None, universe_size=10)


def test_assert_universe_requires_2330_and_size():
    def row(month, sid, rank):
        return {"month_end": month, "stock_id": sid, "rank": rank}

    ok = [row(JUNE, "2330", 1), row(JUNE, "1101", 2)]
    build.assert_universe(ok, universe_size=2)
    with pytest.raises(AssertionError, match="2330 is missing"):
        build.assert_universe([row(JUNE, "1101", 1), row(JUNE, "1102", 2)], universe_size=2)
    with pytest.raises(AssertionError, match="more than"):
        build.assert_universe(ok + [row(JUNE, "1103", 3)], universe_size=2)
    with pytest.raises(AssertionError):
        build.assert_universe([], universe_size=2)
    # a watchlist extra (no rank) does not count as a ranked member
    build.assert_universe(ok + [row(JUNE, "1103", None)], universe_size=2)


def test_pending_event_makes_available_at_pending(tmp_path):
    s = settings(tmp_path, universe_size=3)
    ev = [event("1007", "disposition", JUNE, date(2015, 7, 8), available=None)]
    ev[0]["available_at"] = None
    write_tables(s, [stock("2330", cap=1000), stock("1007", cap=900)], events=ev)
    build.rebuild(ctx_for(s), JUNE, JUNE, watchlist=[])
    jun = by_month(membership(s), JUNE)
    assert "1007" not in jun and jun["2330"]["av"] is None


def test_restricted_market_must_match(tmp_path):
    s = settings(tmp_path, universe_size=3)
    ev = [event("1007", "disposition", JUNE, date(2015, 7, 8), market="TPEx")]
    write_tables(s, [stock("2330", cap=1000), stock("1007", cap=900)], events=ev)
    build.rebuild(ctx_for(s), JUNE, JUNE, watchlist=[])
    assert by_month(membership(s), JUNE)["1007"]["rank"] == 2


def test_rerun_writes_nothing_and_conflict_needs_new_version(tmp_path):
    s = settings(tmp_path, universe_size=3)
    write_tables(s, rule_stocks(), events=events_for_rules())
    ctx = ctx_for(s)
    build.rebuild(ctx, JUNE, JULY, watchlist=[])
    n = {t: len(files(s, t)) for t in ("universe_membership", "collection_set")}
    build.rebuild(ctx, JUNE, JULY, watchlist=[])
    assert {t: len(files(s, t)) for t in n} == n  # identical rows are skipped

    # a new restriction would drop 1001 from June: append-only storage cannot do that
    CleanWriter(s, "status_events").append(
        [event("1001", "changed_trading", date(2015, 6, 29), date(2015, 7, 2))], FETCHED
    )
    with pytest.raises(build.UniverseConflict):
        build.rebuild(ctx, JUNE, JULY, watchlist=[])
    assert {t: len(files(s, t)) for t in n} == n  # nothing was written

    build.rebuild(ctx, JUNE, JULY, watchlist=[], new_version=True)
    assert current_version(s, "universe_membership") == 2
    assert current_version(s, "collection_set") == 2
    jun = by_month(membership(s), JUNE)
    assert "1001" not in jun and jun["2330"]["rank"] == 1
    assert (s.data_dir / "clean" / "universe_membership" / "v1").is_dir()  # old version kept


def test_load_watchlist_yaml(tmp_path):
    p = tmp_path / "w.yaml"
    p.write_text(
        "- {stock_id: '2330', start_date: 2015-06-30, reason: test, added_on: 2026-11-14}\n",
        encoding="utf-8",
    )
    wl = build.load_watchlist(p)
    assert wl[0]["stock_id"] == "2330" and wl[0]["start_date"] == JUNE
    empty = tmp_path / "e.yaml"
    empty.write_text("[]\n", encoding="utf-8")
    assert build.load_watchlist(empty) == []


def test_no_datasets_entry():
    assert not hasattr(build, "DATASETS")
