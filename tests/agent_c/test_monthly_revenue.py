"""Offline tests for src/twdata/ingest/monthly_revenue.py (agent C)."""

import dataclasses
import json
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb
import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "lead"))  # fixtures_inline (importlib import mode)

from fixtures_inline import TOKEN, FakeTransport, jb, make, ok  # noqa: E402

from twdata.clients.base import BlockedError, DriftError  # noqa: E402
from twdata.clients.context import RunContext  # noqa: E402
from twdata.clients.finmind import FinMindClient  # noqa: E402
from twdata.clients.transport import HttpResult  # noqa: E402
from twdata.common import state, views  # noqa: E402
from twdata.common.cleanstore import CleanWriter  # noqa: E402
from twdata.common.tradingcal import TradingCalendar  # noqa: E402
from twdata.ingest import monthly_revenue as mr  # noqa: E402

FIXTURE = (
    HERE.parent / "fixtures" / "lead" / "finmind" / "TaiwanStockMonthRevenue_2330_trimmed.json"
)
FIX_ROWS = json.loads(FIXTURE.read_text(encoding="utf-8"))["data"]
START, END = date(2024, 12, 1), date(2025, 6, 30)


def weekday_calendar(first=date(2024, 12, 2), last=date(2026, 3, 31)):
    days, d = [], first
    while d <= last:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return TradingCalendar(days)


CAL = weekday_calendar()


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", TOKEN)


def body(rows):
    return jb({"msg": "success", "status": 200, "data": rows})


def with_id(rows, stock_id):
    return [{**r, "stock_id": stock_id} for r in rows]


def routed(by_stock, calls=None):
    """A transport result function: answer by the data_id request parameter."""

    def fn(url, params):
        sid = params["data_id"]
        if calls is not None:
            calls.append(sid)
        r = by_stock[sid]
        return r if isinstance(r, HttpResult) else ok(body(r))

    return fn


def seed_collection_set(settings, stock_ids):
    rows = [
        {
            "stock_id": s,
            "first_month_end": date(2024, 12, 31),
            "last_month_end": date(2025, 5, 31),
            "ever_watchlist": False,
            "is_benchmark": False,
        }
        for s in stock_ids
    ]
    CleanWriter(settings, "collection_set").append(rows, datetime.now(UTC))


def make_ctx(tmp_path, by_stock, *, calendar=CAL, seed=True, settings_kw=None, calls=None):
    t = FakeTransport(routed(by_stock, calls))
    c, lim, cache, _ = make(tmp_path, FinMindClient, t, calendar=calendar, settings_kw=settings_kw)
    s = c.settings
    if seed:
        seed_collection_set(s, list(by_stock))
    ctx = RunContext(s, calendar, None, None, c, cache, lambda tbl: CleanWriter(s, tbl))
    return ctx, t


def read_rows(settings, order="event_date"):
    con = duckdb.connect()
    try:
        views.register_views(con, settings)
        cur = con.execute(f"SELECT * FROM as_first_seen_monthly_revenue ORDER BY stock_id, {order}")
        names = [d[0] for d in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
    finally:
        con.close()


def row_for(rows, stock_id, event_date):
    return next(r for r in rows if r["stock_id"] == stock_id and r["event_date"] == event_date)


def tpe(y, m, d, hh=18, mm=0):
    from twdata.common.timeutil import at

    return at(date(y, m, d), hh, mm)


def test_fixture_has_the_columns_the_module_expects():
    assert set(FIX_ROWS[0]) == mr.EXPECTED_COLUMNS


def test_event_date_mapping_and_values(tmp_path):
    ctx, t = make_ctx(tmp_path, {"2330": FIX_ROWS})
    mr.run(ctx, START, END)
    rows = read_rows(ctx.settings)
    assert [r["event_date"] for r in rows] == [
        date(2024, 12, 1),
        date(2025, 1, 1),
        date(2025, 2, 1),
        date(2025, 3, 1),  # source date 2025-04-01, revenue_month 3
        date(2025, 4, 1),
    ]
    dec = rows[0]
    assert dec["revenue"] == 278163107000 and dec["revenue_year"] == 2024
    assert dec["revenue_month"] == 12 and dec["country"] == "Taiwan"
    assert dec["stock_id"] == "2330"
    # one call for the whole range, with the data_id and the dates
    assert len(t.calls) == 1
    assert t.calls[0][2] == {
        "dataset": "TaiwanStockMonthRevenue",
        "start_date": "2024-12-01",
        "end_date": "2025-06-30",
        "data_id": "2330",
    }
    assert state.load(ctx.settings, "monthly_revenue")["completed"] == ["2330"]


def test_available_at_rule(tmp_path):
    # Dec 2025 -> 2026-01-10 is a Saturday -> Monday 2026-01-12 18:00.
    # May 2025 -> 2025-06-10 is a Tuesday -> that day 18:00.
    # Mar 2026 -> 2026-04-10 is past the calendar end -> null.
    def src(y, m):
        return {
            "date": "x",
            "stock_id": "2330",
            "country": "Taiwan",
            "revenue": 1,
            "revenue_month": m,
            "revenue_year": y,
            "create_time": "",
        }

    ctx, _ = make_ctx(tmp_path, {"2330": [src(2025, 12), src(2025, 5), src(2026, 3)]})
    mr.run(ctx, START, END)
    rows = read_rows(ctx.settings)
    assert row_for(rows, "2330", date(2025, 12, 1))["available_at"] == tpe(2026, 1, 12)
    assert row_for(rows, "2330", date(2025, 5, 1))["available_at"] == tpe(2025, 6, 10)
    assert row_for(rows, "2330", date(2026, 3, 1))["available_at"] is None
    assert date(2026, 1, 10).weekday() == 5 and date(2025, 6, 10).weekday() == 1


def test_empty_create_time_is_null_and_value_kept(tmp_path):
    withtime = {**FIX_ROWS[0], "create_time": "2025-01-09 10:00:00"}
    ctx, _ = make_ctx(tmp_path, {"2330": [FIX_ROWS[1], withtime]})
    mr.run(ctx, START, END)
    rows = read_rows(ctx.settings)
    assert row_for(rows, "2330", date(2025, 1, 1))["create_time"] is None
    assert row_for(rows, "2330", date(2024, 12, 1))["create_time"] == "2025-01-09 10:00:00"


def test_rerun_writes_nothing(tmp_path):
    ctx, t = make_ctx(tmp_path, {"2330": FIX_ROWS})
    mr.run(ctx, START, END)
    files = sorted((ctx.settings.data_dir / "clean" / "monthly_revenue").rglob("*.parquet"))
    mr.run(ctx, START, END)
    assert len(t.calls) == 1  # the stock is in state, no second call
    # even with the state gone, identical rows are skipped by the writer
    state.paths.state_file(ctx.settings, "monthly_revenue").unlink()
    mr.run(ctx, START, END)
    again = sorted((ctx.settings.data_dir / "clean" / "monthly_revenue").rglob("*.parquet"))
    assert again == files


def test_empty_response_writes_nothing_and_marks_done(tmp_path):
    ctx, _ = make_ctx(tmp_path, {"0050": [], "2330": FIX_ROWS})
    mr.run(ctx, START, END)
    rows = read_rows(ctx.settings)
    assert {r["stock_id"] for r in rows} == {"2330"}
    assert state.load(ctx.settings, "monthly_revenue")["completed"] == ["0050", "2330"]


def test_missing_collection_set_is_a_clear_error(tmp_path):
    ctx, t = make_ctx(tmp_path, {"2330": FIX_ROWS}, seed=False)
    with pytest.raises(mr.MissingCollectionSet, match="collection_set"):
        mr.run(ctx, START, END)
    assert t.calls == []


def test_stock_list_is_distinct_and_sorted(tmp_path):
    ctx, _ = make_ctx(tmp_path, {"2330": [], "0050": []}, seed=False)
    seed_collection_set(ctx.settings, ["2330", "0050"])
    seed_collection_set(ctx.settings, ["2330"])  # same key, identical values: skipped
    CleanWriter(ctx.settings, "collection_set").append(
        [
            {
                "stock_id": "2330",
                "first_month_end": date(2025, 1, 31),
                "last_month_end": date(2025, 5, 31),
                "ever_watchlist": True,
                "is_benchmark": False,
            }
        ],
        datetime.now(UTC),
    )
    assert mr.stock_list(ctx) == ["0050", "2330"]


def test_drift_extra_or_missing_column(tmp_path):
    extra = [{**FIX_ROWS[0], "new_col": 1}]
    ctx, _ = make_ctx(tmp_path, {"2330": extra})
    with pytest.raises(DriftError, match="columns"):
        mr.run(ctx, START, END)
    assert state.load(ctx.settings, "monthly_revenue") is None

    short = [{k: v for k, v in FIX_ROWS[0].items() if k != "country"}]
    ctx2, _ = make_ctx(tmp_path / "b", {"2330": short})
    with pytest.raises(DriftError):
        mr.run(ctx2, START, END)


def test_drift_bad_types(tmp_path):
    bad = [{**FIX_ROWS[0], "revenue": "abc"}]
    ctx, _ = make_ctx(tmp_path, {"2330": bad})
    with pytest.raises(DriftError, match="revenue"):
        mr.run(ctx, START, END)
    bad_month = [{**FIX_ROWS[0], "revenue_month": 13}]
    ctx2, _ = make_ctx(tmp_path / "b", {"2330": bad_month})
    with pytest.raises(DriftError, match="out of range"):
        mr.run(ctx2, START, END)


def test_drift_row_cap_breach(tmp_path):
    ctx, _ = make_ctx(tmp_path, {"2330": FIX_ROWS})
    small = dataclasses.replace(ctx.settings.row_caps, finmind_default=3, datasets={})
    ctx.settings = dataclasses.replace(ctx.settings, row_caps=small)
    ctx.finmind.settings = ctx.settings
    with pytest.raises(DriftError, match="row cap"):
        mr.run(ctx, START, END)
    assert state.load(ctx.settings, "monthly_revenue") is None


def test_resume_after_a_stock_failure(tmp_path):
    calls = []
    by_stock = {
        "1101": with_id(FIX_ROWS, "1101"),
        "2330": HttpResult(402, {}, b'{"msg":"Requests reach the upper limit","status":402}'),
        "2454": with_id(FIX_ROWS, "2454"),
    }
    ctx, _ = make_ctx(tmp_path, by_stock, calls=calls)
    with pytest.raises(BlockedError):
        mr.run(ctx, START, END)
    assert state.load(ctx.settings, "monthly_revenue")["completed"] == ["1101"]
    assert {r["stock_id"] for r in read_rows(ctx.settings)} == {"1101"}
    # second run: the fault is gone, 1101 is not fetched again
    by_stock["2330"] = FIX_ROWS
    calls.clear()
    mr.run(ctx, START, END)
    assert "1101" not in calls
    assert state.load(ctx.settings, "monthly_revenue")["completed"] == ["1101", "2330", "2454"]
    assert {r["stock_id"] for r in read_rows(ctx.settings)} == {"1101", "2330", "2454"}


def test_fetched_at_is_utc_and_no_token_stored(tmp_path):
    ctx, _ = make_ctx(tmp_path, {"2330": FIX_ROWS})
    before = datetime.now(UTC)
    mr.run(ctx, START, END)
    rows = read_rows(ctx.settings)
    assert all(before <= r["fetched_at"] <= datetime.now(UTC) for r in rows)
    blob = b"".join(p.read_bytes() for p in ctx.settings.data_dir.rglob("*.parquet"))
    assert TOKEN.encode() not in blob


def test_datasets_registry():
    assert mr.DATASETS == {"monthly_revenue": mr.run}


class _Twse:
    def __init__(self, rows):
        self.rows = rows

    def openapi(self, path):
        assert path == "/opendata/t187ap05_L"
        return self.rows, None


def test_check_unit_ratio(tmp_path):
    ctx, _ = make_ctx(tmp_path, {"2330": FIX_ROWS}, seed=False)
    # field names are an assumption (no saved sample), value in NT$ thousands
    official = [
        {"公司代號": "2330", "資料年月": "11312", "營業收入-當月營收": "278,163,107"},
        {"公司代號": "2317", "資料年月": "11312", "營業收入-當月營收": "1"},
    ]
    ctx.twse = _Twse(official)
    assert mr.check_unit(ctx, "2330", date(2024, 12, 15)) == pytest.approx(1000.0)


def test_check_unit_missing_official_row_is_drift(tmp_path):
    ctx, _ = make_ctx(tmp_path, {"2330": FIX_ROWS}, seed=False)
    ctx.twse = _Twse([{"公司代號": "2317", "資料年月": "11312", "營業收入-當月營收": "1"}])
    with pytest.raises(DriftError):
        mr.check_unit(ctx, "2330", date(2024, 12, 1))
