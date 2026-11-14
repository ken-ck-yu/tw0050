import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a1_helpers import (  # noqa: E402
    daily_routes,
    empty_mi_index,
    empty_otc,
    fixture_bytes,
    fixture_json,
    jb,
    make_ctx,
    mi_index_body,
    parquet_files,
    query,
)

from twdata.clients.base import DriftError  # noqa: E402
from twdata.common import paths, schema, state  # noqa: E402
from twdata.common.sanity import SanityError  # noqa: E402
from twdata.common.timeutil import TAIPEI  # noqa: E402
from twdata.ingest import daily_official as do  # noqa: E402

D1 = date(2016, 6, 1)


@pytest.fixture(autouse=True)
def clean_eras(monkeypatch):
    monkeypatch.setattr(schema, "ERAS", {})


def one(ctx, sql, params):
    rows = query(ctx, sql, params)
    assert len(rows) == 1, rows
    return rows[0]


def test_datasets_registry():
    assert set(do.DATASETS) == {"daily_official"}


def test_twse_and_tpex_price_mapping(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, daily_routes(), [D1])
    do.run(ctx, D1, D1)
    q = (
        "SELECT stock_name, open, high, low, close, volume_shares, turnover_ntd, trades, "
        "available_at, event_date FROM default_prices_raw WHERE market = ? AND stock_id = ?"
    )
    r = one(ctx, q, ["TWSE", "0050"])
    assert r[:8] == ("元大台灣50", 62.95, 63.85, 62.95, 63.70, 25001628, 1589746611, 3329)
    assert r[8] == datetime(2016, 6, 1, 18, 0, tzinfo=TAIPEI)
    assert r[9] == D1
    # no-trade TWSE row: prices are `--`
    r = one(ctx, q, ["TWSE", "0059"])
    assert r[1:8] == (None, None, None, None, 0, 0, 0)
    r = one(ctx, q, ["TWSE", "1418"])
    assert r[1:8] == (None, None, None, None, 1, 4, 1)
    # TPEx
    r = one(ctx, q, ["TPEx", "1258"])
    assert r[0] == "F-其祥"
    assert r[1:8] == (38.0, 38.25, 37.6, 37.6, 85000, 3225000, 55)
    # TPEx no-trade row: `----`
    r = one(ctx, q, ["TPEx", "3067"])
    assert r[1:8] == (None, None, None, None, 0, 0, 0)
    n = query(ctx, "SELECT count(*) FROM default_prices_raw", [])[0][0]
    assert n == 25 + 22


def test_twse_no_trade_row_with_volume_keeps_values():
    # 1418 in the fixture has a trade of 1 share at 4 NTD but `--` prices: values are kept
    recs = [
        {
            "證券代號": " 1418 ",
            "證券名稱": "東華*",
            "成交股數": "1",
            "成交筆數": "1",
            "成交金額": "4",
            "開盤價": "--",
            "最高價": "--",
            "最低價": "--",
            "收盤價": "--",
        }
    ]
    from datetime import UTC

    rows = do.twse_price_rows(recs, D1, datetime(2016, 6, 1, 12, tzinfo=UTC))
    assert rows[0]["stock_id"] == "1418" and rows[0]["stock_name"] == "東華"
    assert rows[0]["close"] is None and rows[0]["volume_shares"] == 1


def test_empty_volume_on_priced_row_is_parse_error():
    from datetime import UTC

    from twdata.common.parsing import ParseError

    recs = [
        {
            "證券代號": "1",
            "證券名稱": "x",
            "成交股數": "--",
            "成交筆數": "1",
            "成交金額": "4",
            "開盤價": "1.0",
            "最高價": "1.0",
            "最低價": "1.0",
            "收盤價": "1.0",
        }
    ]
    with pytest.raises(ParseError):
        do.twse_price_rows(recs, D1, datetime(2016, 6, 1, tzinfo=UTC))


def test_sanity_error_on_close_outside_range():
    from datetime import UTC

    recs = [
        {
            "證券代號": "1",
            "證券名稱": "x",
            "成交股數": "5",
            "成交筆數": "1",
            "成交金額": "4",
            "開盤價": "1.0",
            "最高價": "1.0",
            "最低價": "0.9",
            "收盤價": "1.5",
        }
    ]
    with pytest.raises(SanityError):
        do.twse_price_rows(recs, D1, datetime(2016, 6, 1, tzinfo=UTC))


def test_shares_issued_mapping(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, daily_routes(), [D1])
    do.run(ctx, D1, D1)
    q = (
        "SELECT isin, shares_issued, available_at FROM default_shares_issued "
        "WHERE market = ? AND stock_id = ?"
    )
    r = one(ctx, q, ["TWSE", "0050"])
    assert r[:2] == ("TW0000050004", 1745500000)
    assert r[2] == datetime(2016, 6, 1, 18, 0, tzinfo=TAIPEI)
    r = one(ctx, q, ["TPEx", "1258"])
    assert r[:2] == (None, 35463884)
    # the TPEx no-trade stock still has an issued-share count
    assert one(ctx, q, ["TPEx", "3067"])[1] == 29025240


def test_tpex_three_eras_and_ex_date_row(tmp_path):
    d2, d3 = date(2020, 6, 1), date(2025, 6, 2)
    files = {
        "2016/06/01": "tpex/otc_20160601.json",
        "2020/06/01": "tpex/otc_20200601.json",
        "2025/06/02": "tpex/otc_20250602.json",
    }
    routes = daily_routes(otc=lambda p: fixture_bytes(files[p["date"]]))
    ctx, _, _ = make_ctx(tmp_path, routes, [D1, d2, d3])
    do.run(ctx, D1, d3)
    assert query(ctx, "SELECT count(*) FROM default_prices_raw WHERE market='TPEx'", [])[0][0] == (
        22 + 22 + 23
    )
    # `除息` change cell does not matter, the close is stored
    r = one(
        ctx,
        "SELECT close, open FROM default_prices_raw WHERE stock_id='6788' AND event_date=?",
        [d3],
    )
    assert r == (211.0, 213.0)
    r = one(
        ctx,
        "SELECT close, trades FROM default_prices_raw WHERE stock_id='00679B' AND event_date=?",
        [d2],
    )
    assert r == (49.71, 283)
    assert state.is_done(ctx.settings, "prices_raw", d2)


def test_field_list_outside_eras_is_drift(tmp_path):
    def mutate(obj):
        obj["tables"][0]["fields"][2] = "收盤價X"

    body = jb(_mutated("tpex/otc_20160601.json", mutate))
    ctx, _, _ = make_ctx(tmp_path, daily_routes(otc=body), [D1])
    with pytest.raises(DriftError):
        do.run(ctx, D1, D1)
    assert not state.is_done(ctx.settings, "prices_raw", D1)
    assert parquet_files(ctx.settings, "prices_raw") == []


def _mutated(rel, mutate):
    obj = fixture_json(rel)
    mutate(obj)
    return obj


def test_era_registration_does_not_duplicate_lead_eras(tmp_path):
    sentinel = schema.Era(None, None, ("a",))
    schema.ERAS["tpex.otc"] = [sentinel]
    do.ensure_eras()
    assert schema.ERAS["tpex.otc"] == [sentinel]
    assert len(schema.ERAS["twse.mi_index"]) == 1


def test_rerun_writes_nothing_new(tmp_path):
    ctx, transport, cache = make_ctx(tmp_path, daily_routes(), [D1])
    do.run(ctx, D1, D1)
    before = (
        parquet_files(ctx.settings, "prices_raw"),
        parquet_files(ctx.settings, "shares_issued"),
    )
    calls = len(transport.calls)
    assert calls == 3
    do.run(ctx, D1, D1)  # state says done: no request, no file
    assert len(transport.calls) == calls
    # state wiped: raw cache serves the responses, identical rows are skipped by the writer
    for name in ("prices_raw", "shares_issued"):
        paths.state_file(ctx.settings, name).unlink()
    do.run(ctx, D1, D1)
    assert len(transport.calls) == calls
    after = (
        parquet_files(ctx.settings, "prices_raw"),
        parquet_files(ctx.settings, "shares_issued"),
    )
    assert after == before


def test_calendar_discrepancy_day_is_non_trading(tmp_path):
    d2 = date(2016, 6, 2)

    # 06-02 is a trading day in the calendar but both markets answer with no rows
    def by_date(full, empty, fmt):
        return lambda p: empty if p["date"] == d2.strftime(fmt) else full

    routes = daily_routes(
        mi=by_date(mi_index_body(), empty_mi_index(), "%Y%m%d"),
        otc=by_date(fixture_bytes("tpex/otc_20160601.json"), empty_otc(), "%Y/%m/%d"),
    )
    ctx, transport, _ = make_ctx(tmp_path, routes, [D1, d2])
    do.run(ctx, D1, d2)
    ledger = paths.calendar_ledger(ctx.settings).read_text(encoding="utf-8").splitlines()
    assert len(ledger) == 1 and '"2016-06-02"' in ledger[0]
    assert query(ctx, "SELECT count(DISTINCT event_date) FROM default_prices_raw", [])[0][0] == 1
    qfiis_calls = [c for c in transport.calls if "MI_QFIIS" in c[0]]
    assert len(qfiis_calls) == 1  # none for the discrepancy day
    assert state.is_done(ctx.settings, "prices_raw", d2)
    assert state.is_done(ctx.settings, "shares_issued", d2)


def test_only_one_market_empty_is_drift(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, daily_routes(otc=empty_otc()), [D1])
    with pytest.raises(DriftError):
        do.run(ctx, D1, D1)


def test_batches_of_twenty_days(tmp_path):
    days = []
    d = date(2016, 6, 1)
    while len(days) < 45:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    ctx, transport, cache = make_ctx(tmp_path, daily_routes(), days)
    do.run(ctx, days[0], days[-1])
    # 45 days: batches of 20, 20 and 5, one append and one cache flush each
    assert len(parquet_files(ctx.settings, "prices_raw")) == 3
    assert len(parquet_files(ctx.settings, "shares_issued")) == 3
    assert cache.flushes == 3
    assert len(transport.calls) == 45 * 3
    assert all(state.is_done(ctx.settings, "prices_raw", x) for x in days)
    # a resumed run over a wider range only fetches what is missing
    calls = len(transport.calls)
    do.run(ctx, days[0], days[-1])
    assert len(transport.calls) == calls


def test_listing_status_view(tmp_path):
    d2 = date(2016, 6, 2)
    routes = daily_routes(
        mi=lambda p: mi_index_body(
            lambda obj: _drop(obj, "1418") if p["date"] == "20160602" else None
        )
    )
    ctx, _, _ = make_ctx(tmp_path, routes, [D1, d2])
    do.run(ctx, D1, d2)
    rows = {
        (m, s): (a, b)
        for m, s, a, b in query(
            ctx, "SELECT market, stock_id, first_date, last_date FROM listing_status", []
        )
    }
    assert rows[("TWSE", "0050")] == (D1, d2)
    assert rows[("TWSE", "1418")] == (D1, D1)
    assert rows[("TPEx", "1258")] == (D1, d2)


def _drop(obj, stock_id):
    for t in obj["tables"]:
        if t.get("title") and "每日收盤行情" in t["title"]:
            t["data"] = [r for r in t["data"] if r[0] != stock_id]
