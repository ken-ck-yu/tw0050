import json
import os
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from helpers_b import FIXED_NOW, LEAD, Router, fixture_bytes, make_ctx, query, weekday_calendar

from twdata.clients.base import unique_field_names
from twdata.common import state
from twdata.common.parsing import ParseError
from twdata.common.timeutil import TAIPEI
from twdata.ingest import corporate_actions as ca

MANUAL = Path(__file__).resolve().parents[1] / "fixtures" / "agent_b" / "manual_test.yaml"
NO_MANUAL = "/nonexistent/manual.yaml"


@pytest.fixture(autouse=True)
def manual_file(monkeypatch):
    monkeypatch.setattr(ca, "MANUAL_PATH", MANUAL)


def records(rel: str, table: bool = False) -> list[dict]:
    d = json.loads((LEAD / rel).read_text(encoding="utf-8"))
    t = d["tables"][0] if table else d
    names = unique_field_names(t["fields"])
    return [dict(zip(names, r, strict=True)) for r in t["data"]]


def by_stock(rows, sid):
    return [r for r in rows if r["stock_id"] == sid]


# ---- mappings against the fixtures ------------------------------------------------


def test_twt49u_mapping():
    rows = ca.parse_twt49u(records("twse/twt49u_2025_trimmed.json"))
    assert len(rows) == 20
    r = by_stock(rows, "2454")[0]
    assert r["market"] == "TWSE"
    assert r["event_date"] == date(2025, 1, 2)
    assert r["action_type"] == "ex_dividend"
    assert r["prev_close"] == 1415.0 and r["reference_price"] == 1386.0
    assert r["cash_dividend"] is None and r["stock_dividend_per_1000"] is None
    assert by_stock(rows, "6658")[0]["action_type"] == "ex_rights"
    etf = by_stock(rows, "0050")[0]  # the feed lists ETFs
    assert etf["event_date"] == date(2025, 1, 17)
    assert (etf["prev_close"], etf["reference_price"]) == (198.05, 195.35)
    assert {r["action_type"] for r in rows} == {"ex_dividend", "ex_rights"}


def test_twtauu_mapping():
    rows = ca.parse_twtauu(records("twse/twtauu_2015_2022_trimmed.json"))
    assert len(rows) == 21
    r = by_stock(rows, "6165")[0]
    assert r["market"] == "TWSE" and r["action_type"] == "capital_reduction"
    assert r["event_date"] == date(2015, 8, 24)
    assert r["halt_close"] == 7.0 and r["prev_close"] == 7.0 and r["reference_price"] == 13.38
    assert r["reduction_reason"] == "彌補虧損"
    assert by_stock(rows, "8261")[0]["reduction_reason"] == "退還股款"
    assert by_stock(rows, "2387")[0]["event_date"] == date(2016, 1, 5)


def test_ex_daily_mapping():
    rows = ca.parse_ex_daily(records("tpex/ex_daily_2016_trimmed.json", table=True))
    assert len(rows) == 23
    r = by_stock(rows, "4157")[0]
    assert r["market"] == "TPEx" and r["event_date"] == date(2016, 1, 7)
    assert r["action_type"] == "ex_rights"
    assert (r["prev_close"], r["reference_price"]) == (31.6, 31.49)
    assert r["cash_dividend"] == 0.0 and r["stock_dividend_per_1000"] == 0.0
    div = by_stock(rows, "3291")[0]
    assert div["action_type"] == "ex_dividend" and div["cash_dividend"] == 0.3
    both = by_stock(rows, "6185")[0]  # 除權息
    assert both["action_type"] == "ex_rights"
    assert both["cash_dividend"] == 1.6
    assert both["stock_dividend_per_1000"] == pytest.approx(40.0000042)
    assert {r["action_type"] for r in rows} == {"ex_dividend", "ex_rights"}


def test_revivt_mapping_seven_digit_roc_date():
    rows = ca.parse_revivt(records("tpex/revivt_2015_trimmed.json", table=True))
    assert len(rows) == 19
    r = by_stock(rows, "4131")[0]
    assert r["market"] == "TPEx" and r["action_type"] == "capital_reduction"
    assert r["event_date"] == date(2015, 1, 30)  # "1040130"
    assert r["halt_close"] == 9.95 and r["prev_close"] == 9.95 and r["reference_price"] == 12.56
    assert r["reduction_reason"] == "彌補虧損"
    assert by_stock(rows, "8111")[0]["event_date"] == date(2015, 2, 10)


def test_cell_helpers():
    assert ca.parse_event_date("114年01月02日") == date(2025, 1, 2)
    assert ca.parse_event_date("104/08/24") == date(2015, 8, 24)
    assert ca.parse_event_date("1040130") == date(2015, 1, 30)
    assert ca.parse_event_date("20150130") == date(2015, 1, 30)
    for cell, want in [
        ("權", "ex_rights"),
        ("息", "ex_dividend"),
        ("權息", "ex_rights"),
        ("除權", "ex_rights"),
        ("除息", "ex_dividend"),
        ("除權息", "ex_rights"),
    ]:
        assert ca.action_from_mark(cell) == want
    with pytest.raises(ParseError):
        ca.action_from_mark("?")


# ---- manual file ------------------------------------------------------------------


def test_manual_file_with_null_reference_price():
    rows, mtime = ca.load_manual(MANUAL)
    assert mtime.tzinfo is not None
    split = by_stock(rows, "0050")[0]
    assert split["action_type"] == "split" and split["market"] == "TWSE"
    assert split["event_date"] == date(2025, 6, 18)
    assert split["ratio"] == 4.0
    assert split["halt_close"] == 188.65 and split["prev_close"] == 188.65
    assert split["reference_price"] is None
    par = by_stock(rows, "9999")[0]
    assert par["reference_price"] == 25.0 and par["market"] == "TPEx"


def test_repo_manual_file_loads():
    rows, _ = ca.load_manual(
        Path(__file__).resolve().parents[2] / "config" / "manual_corporate_actions.yaml"
    )
    assert [(r["stock_id"], r["action_type"], r["ratio"], r["reference_price"]) for r in rows] == [
        ("0050", "split", 4.0, None)
    ]


def test_manual_file_errors(tmp_path):
    p = tmp_path / "m.yaml"
    p.write_text(
        "- market: TWSE\n  stock_id: '1'\n  action_type: nonsense\n  event_date: 2020-01-02\n"
    )
    with pytest.raises(ParseError):
        ca.load_manual(p)
    p.write_text("- market: TWSE\n  stock_id: '1'\n  action_type: split\n")
    with pytest.raises(ParseError):
        ca.load_manual(p)
    assert ca.load_manual(tmp_path / "missing.yaml") == ([], None)


# ---- end to end -------------------------------------------------------------------


def router():
    return (
        Router()
        .add("exRight/TWT49U", fixture_bytes("twse/twt49u_2025_trimmed.json"))
        .add("reducation/TWTAUU", fixture_bytes("twse/twtauu_2015_2022_trimmed.json"))
        .add("bulletin/exDailyQ", fixture_bytes("tpex/ex_daily_2016_trimmed.json"))
        .add("bulletin/revivt", fixture_bytes("tpex/revivt_2015_trimmed.json"))
    )


def test_run_writes_all_sources_with_available_at(tmp_path):
    ctx = make_ctx(tmp_path, router())
    ca.run(ctx, date(2025, 1, 1), date(2025, 12, 31))
    rows = query(tmp_path, "SELECT * FROM default_corporate_actions")
    assert len(rows) == 20 + 21 + 23 + 19 + 1  # manual 0050 split is in range, 9999 is not
    key = {(r["market"], r["stock_id"], r["event_date"], r["action_type"]): r for r in rows}
    r = key[("TWSE", "2454", date(2025, 1, 2), "ex_dividend")]
    # next trading day 08:30 Taipei (Friday 2025-01-03)
    assert r["available_at"].astimezone(TAIPEI) == datetime(2025, 1, 3, 8, 30, tzinfo=TAIPEI)
    assert r["fetched_at"] == FIXED_NOW
    split = key[("TWSE", "0050", date(2025, 6, 18), "split")]
    assert split["ratio"] == 4.0 and split["reference_price"] is None
    assert split["available_at"].astimezone(TAIPEI) == datetime(2025, 6, 19, 8, 30, tzinfo=TAIPEI)
    # the manual row takes the file's modification time
    mtime = datetime.fromtimestamp(os.path.getmtime(MANUAL), UTC)
    assert split["fetched_at"] == mtime
    assert state.is_done(ctx.settings, "corporate_actions", date(2025, 6, 1))


def test_rerun_writes_no_new_files(tmp_path):
    ctx = make_ctx(tmp_path, router())
    ca.run(ctx, date(2025, 1, 1), date(2025, 12, 31))
    files = sorted(tmp_path.rglob("*.parquet"))
    ca.run(ctx, date(2025, 1, 1), date(2025, 12, 31))
    assert sorted(tmp_path.rglob("*.parquet")) == files


def test_windows_one_year_except_twt49u(tmp_path):
    r = router()
    ctx = make_ctx(tmp_path, r)
    rows, stats = ca.collect(ctx, date(2015, 6, 1), date(2017, 3, 31))
    assert r.count("TWT49U") == 1
    for needle in ("reducation/TWTAUU", "bulletin/exDailyQ", "bulletin/revivt"):
        assert r.count(needle) == 3
    spans = [(p["startDate"], p["endDate"]) for u, p in r.calls if "TWTAUU" in u]
    assert spans == [
        ("20150601", "20151231"),
        ("20160101", "20161231"),
        ("20170101", "20170331"),
    ]
    twt49 = [p for u, p in r.calls if "TWT49U" in u][0]
    assert (twt49["startDate"], twt49["endDate"]) == ("20150601", "20170331")
    # the same feed body is returned for each window, so its rows collapse by key
    assert stats.collisions > 0


def test_key_collision_keeps_first_in_response_order():
    base = dict(
        market="TPEx",
        stock_id="6185",
        event_date=date(2016, 6, 7),
        action_type="ex_rights",
        prev_close=22.15,
        reference_price=19.76,
        halt_close=None,
        ratio=None,
        cash_dividend=1.6,
        reduction_reason=None,
    )
    a = {**base, "stock_dividend_per_1000": 0.0, "tag": "a"}
    b = {**base, "stock_dividend_per_1000": 40.0, "tag": "b"}
    other = {**base, "stock_id": "1111", "stock_dividend_per_1000": None, "tag": "o"}
    out, dropped = ca.dedupe([a, b, other])
    assert dropped == 1
    assert [r["tag"] for r in out] == ["a", "o"]


def test_collision_in_run_is_written_once(tmp_path):
    body = json.loads(fixture_bytes("tpex/ex_daily_2016_trimmed.json"))
    row = list(body["tables"][0]["data"][0])
    dup = list(row)
    dup[8] = "除權息"  # same key as `row` after the mapping (both ex_rights)
    dup[14] = "25.00000000"
    body["tables"][0]["data"] = [row, dup]
    body["tables"][0]["totalCount"] = 2
    r = Router()
    r.add(
        "exRight/TWT49U",
        json.dumps(
            {"stat": "很抱歉，沒有符合條件的資料!", "total": 0}, ensure_ascii=False
        ).encode(),
    )
    r.add(
        "reducation/TWTAUU",
        json.dumps(
            {"stat": "很抱歉，沒有符合條件的資料!", "total": 0}, ensure_ascii=False
        ).encode(),
    )
    r.add("bulletin/exDailyQ", json.dumps(body, ensure_ascii=False).encode())
    r.add("bulletin/revivt", fixture_bytes("tpex/revivt_2015_trimmed.json"))
    ctx = make_ctx(tmp_path, r)
    monkey_rows, stats = ca.collect(ctx, date(2016, 1, 1), date(2016, 12, 31))
    assert stats.collisions == 1
    kept = [x for x in monkey_rows if x["stock_id"] == "4157"]
    assert len(kept) == 1 and kept[0]["stock_dividend_per_1000"] == 0.0


def test_pending_available_at_without_calendar_coverage(tmp_path):
    # a calendar that ends before the event: available_at is null (pending) and is filled later
    cal = weekday_calendar(date(2025, 1, 1), date(2025, 1, 2))
    r = router()
    ctx = make_ctx(tmp_path, r, calendar=cal)
    rows, _ = ca.collect(ctx, date(2025, 1, 1), date(2025, 12, 31))
    late = [x for x in rows if x["event_date"] >= date(2025, 1, 2)]
    assert late and all(x["available_at"] is None for x in late)
