import json
from datetime import date, datetime

import pytest
from helpers_b import LEAD, Router, fixture_bytes, make_ctx, query, weekday_calendar

from twdata.clients.base import DriftError, unique_field_names
from twdata.common import state
from twdata.common.parsing import ParseError
from twdata.common.sanity import SanityError
from twdata.common.timeutil import TAIPEI
from twdata.ingest import price_limits as pl

D = date(2020, 6, 15)  # Monday, previous trading day is Friday 2020-06-12


def router(otc="tpex/otc_20200601.json"):
    return (
        Router()
        .add("variation/TWT84U", fixture_bytes("twse/twt84u_20200615.json"))
        .add("afterTrading/otc", fixture_bytes(otc))
    )


def rows_of(tmp_path):
    return query(tmp_path, "SELECT * FROM default_price_limits ORDER BY market, stock_id")


def test_twt84u_duplicate_field_name_rule():
    d = json.loads((LEAD / "twse/twt84u_20200615.json").read_text(encoding="utf-8"))
    names = unique_field_names(d["fields"])
    assert names.count("開盤競價基準") == 1 and "開盤競價基準#2" in names
    rec = dict(zip(names, d["data"][0], strict=True))
    # first reference is the base of the up limit side, the second the base of the down side
    assert rec["開盤競價基準"] == "88.25" and rec["開盤競價基準#2"] == "89.05"
    assert rec["漲停價"] == "97.05" and rec["跌停價"] == "79.45"


def test_twse_rows_mapping(tmp_path):
    ctx = make_ctx(tmp_path, router())
    pl.run(ctx, D, D)
    rows = [r for r in rows_of(tmp_path) if r["market"] == "TWSE"]
    assert len(rows) == 21
    r = [x for x in rows if x["stock_id"] == "0050"][0]
    assert (r["limit_up"], r["limit_down"]) == (97.05, 79.45)
    assert r["event_date"] == D
    assert r["available_at"].astimezone(TAIPEI) == datetime(2020, 6, 15, 18, 0, tzinfo=TAIPEI)
    assert r["fetched_at"].year == 2026


def test_tpex_limits_shift_to_next_trading_day_and_sentinel(tmp_path):
    r = router("tpex/otc_20160601.json")
    ctx = make_ctx(tmp_path, r)
    d = date(2016, 6, 2)  # the otc file of 2016-06-01 gives the limits stored on 2016-06-02
    pl.run(ctx, date(2016, 6, 1), date(2016, 6, 1))
    otc_calls = [p for u, p in r.calls if "afterTrading/otc" in u]
    assert [p["date"] for p in otc_calls] == ["2016/06/01"]
    tp = {x["stock_id"]: x for x in rows_of(tmp_path) if x["market"] == "TPEx"}
    assert tp["1258"]["event_date"] == d
    assert {x["event_date"] for x in rows_of(tmp_path) if x["market"] == "TWSE"} == {
        date(2016, 6, 1)
    }
    assert (tp["1258"]["limit_up"], tp["1258"]["limit_down"]) == (41.35, 33.85)
    assert tp["1258"]["available_at"].astimezone(TAIPEI) == datetime(
        2016, 6, 2, 18, 0, tzinfo=TAIPEI
    )


def test_tpex_sentinel_becomes_null(tmp_path):
    ctx = make_ctx(tmp_path, router("tpex/otc_20200601.json"))
    pl.run(ctx, D, D)
    tp = {x["stock_id"]: x for x in rows_of(tmp_path) if x["market"] == "TPEx"}
    assert len(tp) == 22 and tp["00679B"]["event_date"] == date(2020, 6, 16)
    assert tp["00679B"]["limit_up"] is None and tp["00679B"]["limit_down"] is None


def test_limit_value_cells():
    assert pl.limit_value("9,999.95", up=True) is None
    assert pl.limit_value("0.01", up=False) is None
    assert pl.limit_value("0.01", up=True) == 0.01
    assert pl.limit_value("9,999.95", up=False) == 9999.95
    assert pl.limit_value("----", up=True) is None
    assert pl.limit_value("97.05", up=True) == 97.05
    with pytest.raises(ParseError):
        pl.limit_value("abc", up=True)


def test_tpex_taken_from_cache_not_network(tmp_path):
    r = router("tpex/otc_20160601.json")
    ctx = make_ctx(tmp_path, r)
    ctx.tpex.otc(date(2016, 6, 1))  # the daily prices pass stored the raw file
    assert r.count("afterTrading/otc") == 1
    pl.run(ctx, date(2016, 6, 1), date(2016, 6, 1))
    assert r.count("afterTrading/otc") == 1  # served from the cache


def test_cached_empty_otc_gives_no_tpex_rows(tmp_path):
    empty = (LEAD / "tpex/synthetic_empty_holiday.json").read_text(encoding="utf-8")
    body = json.loads(json.loads(empty)["body"])
    r = Router().add("variation/TWT84U", fixture_bytes("twse/twt84u_20200615.json"))
    r.add("afterTrading/otc", json.dumps(body, ensure_ascii=False).encode())
    ctx = make_ctx(tmp_path, r)
    ctx.tpex.otc(D, allow_empty=True)
    pl.run(ctx, D, D)
    assert {x["market"] for x in rows_of(tmp_path)} == {"TWSE"}


def test_state_and_rerun_write_nothing_new(tmp_path):
    r = router()
    ctx = make_ctx(tmp_path, r)
    pl.run(ctx, D, date(2020, 6, 16))
    assert state.is_done(ctx.settings, "price_limits", D)
    assert state.is_done(ctx.settings, "price_limits", date(2020, 6, 16))
    files = sorted(tmp_path.rglob("*.parquet"))
    n = len(r.calls)
    pl.run(ctx, D, date(2020, 6, 16))
    assert len(r.calls) == n and sorted(tmp_path.rglob("*.parquet")) == files
    assert [p["date"] for u, p in r.calls if "afterTrading/otc" in u] == [
        "2020/06/15",
        "2020/06/16",
    ]


def test_only_trading_days_are_requested(tmp_path):
    r = router()
    ctx = make_ctx(tmp_path, r)
    pl.run(ctx, date(2020, 6, 13), date(2020, 6, 14))  # Saturday and Sunday
    assert r.calls == []


def test_first_window_day_has_no_tpex_limit_row(tmp_path):
    ctx = make_ctx(tmp_path, router())
    pl.run(ctx, D, date(2020, 6, 16))
    tp = {x["event_date"] for x in rows_of(tmp_path) if x["market"] == "TPEx"}
    assert D not in tp and tp == {date(2020, 6, 16), date(2020, 6, 17)}


def test_no_next_trading_day_skips_tpex(tmp_path):
    cal = weekday_calendar(date(2020, 6, 1), D)
    ctx = make_ctx(tmp_path, router(), calendar=cal)
    pl.run(ctx, D, D)
    assert {x["market"] for x in rows_of(tmp_path)} == {"TWSE"}


def test_limit_down_above_limit_up_is_a_sanity_error():
    with pytest.raises(SanityError):
        pl.twse_rows(
            [{"證券代號": "1111", "漲停價": "10.00", "跌停價": "12.00"}],
            D,
            datetime(2020, 6, 15, tzinfo=TAIPEI),
        )


def test_missing_field_is_drift():
    with pytest.raises(DriftError):
        pl.tpex_rows([{"代號": "1111"}], D, datetime(2020, 6, 15, tzinfo=TAIPEI))
