from datetime import UTC, date, datetime, timedelta

import pytest
from helpers_b import FIXED_NOW, connect, query

from twdata.common import config
from twdata.common.cleanstore import CleanWriter
from twdata.common.timeutil import TAIPEI, at
from twdata.ingest import adjusted


def settings(tmp_path):
    return config.load_settings(data_dir_override=str(tmp_path))


def put_prices(tmp_path, closes, market="TWSE", stock_id="1111"):
    rows = [
        {
            "market": market,
            "stock_id": stock_id,
            "stock_name": "x",
            "event_date": d,
            "available_at": at(d, 18, 0),
            "open": c,
            "high": c,
            "low": c,
            "close": c,
            "volume_shares": 1000,
            "turnover_ntd": 1000,
            "trades": 1,
        }
        for d, c in closes
    ]
    CleanWriter(settings(tmp_path), "prices_raw").append(rows, FIXED_NOW)


def action(d, kind="ex_dividend", market="TWSE", stock_id="1111", avail="auto", **kw):
    row = {
        "market": market,
        "stock_id": stock_id,
        "event_date": d,
        "action_type": kind,
        "available_at": at(d + timedelta(days=1), 8, 30) if avail == "auto" else avail,
        "prev_close": None,
        "reference_price": None,
        "halt_close": None,
        "ratio": None,
        "cash_dividend": None,
        "stock_dividend_per_1000": None,
        "reduction_reason": None,
    }
    row.update(kw)
    return row


def put_actions(tmp_path, rows):
    CleanWriter(settings(tmp_path), "corporate_actions").append(rows, FIXED_NOW)


def by_date(tbl):
    out = {}
    for r in tbl.to_pylist():
        out[(r["stock_id"], r["event_date"])] = r
    return out


D1, D2, D3 = date(2025, 3, 3), date(2025, 3, 4), date(2025, 3, 5)  # Mon, Tue, Wed


def test_worked_example_from_the_design(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0)])
    # ex-dividend on day 2 (event_date D2) with available_at day 3 08:30
    put_actions(
        tmp_path,
        [action(D2, avail=at(D3, 8, 30), prev_close=100.0, reference_price=95.0)],
    )
    con = connect(tmp_path)
    before = adjusted.adjusted_series(con, as_of=at(D3, 8, 29))
    after = adjusted.adjusted_series(con, as_of=at(D3, 8, 30))
    assert by_date(before)[("1111", D1)]["adjusted_close"] == pytest.approx(100.0)
    assert by_date(after)[("1111", D1)]["adjusted_close"] == pytest.approx(95.0)
    assert by_date(after)[("1111", D1)]["factor"] == pytest.approx(0.95)
    assert by_date(after)[("1111", D2)]["adjusted_close"] == pytest.approx(95.0)  # no event after
    # any earlier time, even before day 1 closes
    early = adjusted.adjusted_series(con, as_of=at(D1, 0, 0))
    assert by_date(early)[("1111", D1)]["adjusted_close"] == pytest.approx(100.0)
    # as_of=None is the full adjustment, the same as the registered view
    full = adjusted.adjusted_series(con)
    assert by_date(full)[("1111", D1)]["adjusted_close"] == pytest.approx(95.0)
    view = query(tmp_path, "SELECT * FROM adjusted_close ORDER BY event_date")
    assert [round(r["adjusted_close"], 6) for r in view] == [95.0, 95.0]
    assert list(view[0]) == [
        "market",
        "stock_id",
        "event_date",
        "close",
        "factor",
        "adjusted_close",
        "is_ex_date_window",
    ]


def test_output_columns_and_types(tmp_path):
    put_prices(tmp_path, [(D1, 100.0)])
    put_actions(tmp_path, [action(D2, prev_close=100.0, reference_price=95.0)])
    tbl = adjusted.adjusted_series(connect(tmp_path), as_of=datetime(2030, 1, 1, tzinfo=UTC))
    assert tbl.column_names == [
        "market",
        "stock_id",
        "event_date",
        "close",
        "factor",
        "adjusted_close",
        "is_ex_date_window",
    ]
    assert str(tbl.schema.field("is_ex_date_window").type) == "bool"


def test_is_ex_date_window(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0), (D3, 96.0)])
    put_actions(
        tmp_path,
        [action(D2, avail=at(D3, 8, 30), prev_close=100.0, reference_price=95.0)],
    )
    con = connect(tmp_path)
    pending = by_date(adjusted.adjusted_series(con, as_of=at(D2, 20, 0)))
    assert pending[("1111", D2)]["is_ex_date_window"] is True
    assert pending[("1111", D1)]["is_ex_date_window"] is False
    assert pending[("1111", D3)]["is_ex_date_window"] is False
    known = by_date(adjusted.adjusted_series(con, as_of=at(D3, 8, 30)))
    assert not any(r["is_ex_date_window"] for r in known.values())
    full = by_date(adjusted.adjusted_series(con))
    assert not any(r["is_ex_date_window"] for r in full.values())


def test_pending_event_with_null_available_at_is_a_window(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0)])
    put_actions(tmp_path, [action(D2, avail=None, prev_close=100.0, reference_price=95.0)])
    got = by_date(adjusted.adjusted_series(connect(tmp_path), as_of=at(D3, 12, 0)))
    assert got[("1111", D1)]["adjusted_close"] == pytest.approx(100.0)
    assert got[("1111", D2)]["is_ex_date_window"] is True


def test_two_same_day_events_multiply(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 90.0)])
    put_actions(
        tmp_path,
        [
            action(D2, "ex_dividend", prev_close=100.0, reference_price=95.0),
            action(
                D2, "capital_reduction", prev_close=100.0, halt_close=100.0, reference_price=80.0
            ),
        ],
    )
    got = by_date(adjusted.adjusted_series(connect(tmp_path)))
    assert got[("1111", D1)]["factor"] == pytest.approx(0.95 * 0.8)
    assert got[("1111", D1)]["adjusted_close"] == pytest.approx(76.0)


def test_factors_of_several_dates_chain_and_stocks_stay_apart(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 50.0), (D3, 50.0)])
    put_prices(tmp_path, [(D1, 10.0), (D2, 10.0)], stock_id="2222")
    put_actions(
        tmp_path,
        [
            action(D2, prev_close=100.0, reference_price=50.0),
            action(D3, prev_close=50.0, reference_price=45.0),
        ],
    )
    got = by_date(adjusted.adjusted_series(connect(tmp_path)))
    assert got[("1111", D1)]["adjusted_close"] == pytest.approx(100 * 0.5 * 0.9)
    assert got[("1111", D2)]["adjusted_close"] == pytest.approx(50 * 0.9)
    assert got[("1111", D3)]["adjusted_close"] == pytest.approx(50.0)
    assert got[("2222", D1)]["factor"] == 1.0
    only = adjusted.adjusted_series(connect(tmp_path), stock_ids=["2222"])
    assert {r["stock_id"] for r in only.to_pylist()} == {"2222"}


def test_null_reference_price_uses_one_over_ratio(tmp_path):
    ev = date(2025, 6, 18)
    put_prices(tmp_path, [(date(2025, 6, 17), 188.65), (ev, 47.57)], stock_id="0050")
    put_actions(
        tmp_path,
        [
            action(
                ev,
                "split",
                stock_id="0050",
                avail=at(date(2025, 6, 19), 8, 30),
                prev_close=188.65,
                halt_close=188.65,
                ratio=4.0,
            )
        ],
    )
    con = connect(tmp_path)
    after = by_date(adjusted.adjusted_series(con, as_of=at(date(2025, 6, 19), 8, 30)))
    before = by_date(adjusted.adjusted_series(con, as_of=at(date(2025, 6, 19), 8, 29)))
    prior = date(2025, 6, 17)
    assert after[("0050", prior)]["factor"] == pytest.approx(0.25)
    assert after[("0050", prior)]["adjusted_close"] == pytest.approx(188.65 * 0.25, abs=1e-9)
    assert before[("0050", prior)]["adjusted_close"] == pytest.approx(188.65, abs=1e-9)
    assert before[("0050", ev)]["is_ex_date_window"] is True


def test_split_ignores_reference_price_uses_ratio(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 25.0)])
    put_actions(
        tmp_path,
        [action(D2, "par_value_change", prev_close=100.0, reference_price=26.0, ratio=4.0)],
    )
    got = by_date(adjusted.adjusted_series(connect(tmp_path)))
    assert got[("1111", D1)]["factor"] == pytest.approx(0.25)


def test_uncomputable_factor_is_one_and_counted(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0)])
    put_actions(tmp_path, [action(D2, prev_close=None, reference_price=95.0)])
    before = adjusted.UNCOMPUTABLE_EVENTS
    got = by_date(adjusted.adjusted_series(connect(tmp_path)))
    assert got[("1111", D1)]["factor"] == 1.0
    assert adjusted.UNCOMPUTABLE_EVENTS == before + 1


def test_null_reference_without_ratio_is_one_and_counted(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0)])
    put_actions(tmp_path, [action(D2, prev_close=100.0)])
    before = adjusted.UNCOMPUTABLE_EVENTS
    got = by_date(adjusted.adjusted_series(connect(tmp_path)))
    assert got[("1111", D1)]["factor"] == 1.0
    assert adjusted.UNCOMPUTABLE_EVENTS == before + 1


def test_as_of_none_equals_the_view(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0), (D3, 96.0)])
    put_prices(tmp_path, [(D1, 10.0), (D2, 10.0)], stock_id="2222")
    put_actions(
        tmp_path,
        [
            action(D2, prev_close=100.0, reference_price=95.0),
            action(D3, "split", ratio=2.0, prev_close=95.0),
        ],
    )
    con = connect(tmp_path)
    tbl = adjusted.adjusted_series(con)
    view = con.sql("SELECT * FROM adjusted_close ORDER BY market, stock_id, event_date")
    assert tbl.to_pylist() == view.to_arrow_table().to_pylist()


def test_no_trade_row_keeps_null_close(tmp_path):
    put_prices(tmp_path, [(D1, 100.0)])
    rows = [
        {
            "market": "TWSE",
            "stock_id": "1111",
            "stock_name": "x",
            "event_date": D2,
            "available_at": at(D2, 18, 0),
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume_shares": 0,
            "turnover_ntd": 0,
            "trades": 0,
        }
    ]
    CleanWriter(settings(tmp_path), "prices_raw").append(rows, FIXED_NOW)
    put_actions(tmp_path, [action(D3, prev_close=100.0, reference_price=95.0)])
    got = by_date(adjusted.adjusted_series(connect(tmp_path)))
    assert got[("1111", D2)]["close"] is None and got[("1111", D2)]["adjusted_close"] is None


def test_only_available_prices_option(tmp_path):
    put_prices(tmp_path, [(D1, 100.0), (D2, 95.0)])
    put_actions(tmp_path, [action(D3, prev_close=95.0, reference_price=90.0)])
    con = connect(tmp_path)
    cut = at(D1, 19, 0)  # day 2 close is not yet published
    assert len(adjusted.adjusted_series(con, as_of=cut)) == 2
    assert len(adjusted.adjusted_series(con, as_of=cut, only_available_prices=True)) == 1


def test_as_of_must_be_timezone_aware(tmp_path):
    put_prices(tmp_path, [(D1, 100.0)])
    with pytest.raises(ValueError):
        adjusted.adjusted_series(connect(tmp_path), as_of=datetime(2025, 3, 5, 8, 30))


def test_view_is_registered_and_labelled():
    from twdata.common import views

    assert "adjusted_close" in views._EXTRA_VIEWS
    assert "not a feature input" in adjusted.LABEL
    assert TAIPEI is not None
