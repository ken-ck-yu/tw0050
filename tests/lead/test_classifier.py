from datetime import date

import pytest
from fixtures_inline import (
    CAL,
    FIELDS,
    HOLIDAY,
    NO_DATA,
    OUTSIDE,
    TRADING,
    jb,
    mi_index,
    ok,
    tpex,
    twse_top,
)

from twdata.clients.classifier import classify
from twdata.clients.transport import HttpResult
from twdata.common import schema
from twdata.common.endpoints import ENDPOINTS, openapi_spec

MI = ENDPOINTS["twse.mi_index"]
OTC = ENDPOINTS["tpex.otc"]
QF = ENDPOINTS["twse.mi_qfiis"]
RNG = ENDPOINTS["twse.twt49u"]
SM = ENDPOINTS["twse.stock_day"]


@pytest.fixture(autouse=True)
def eras(monkeypatch):
    E = schema.Era
    monkeypatch.setattr(
        schema,
        "ERAS",
        {
            "twse.mi_index": [E(None, None, tuple(FIELDS))],
            "tpex.otc": [E(None, None, tuple(FIELDS))],
        },
    )


def c(spec, res, d=None, **kw):
    return classify(spec, res, date=d, calendar=CAL, **kw)


@pytest.mark.parametrize("st", [0, 500, 503, 429])
def test_transient(st):
    assert c(MI, HttpResult(st), TRADING).klass == "transient"


@pytest.mark.parametrize("st", [302, 400, 403, 404])
def test_drift_status(st):
    assert c(MI, HttpResult(st, {"Location": "/x"}), TRADING).klass == "drift"


def test_html_and_invalid_json():
    assert c(MI, ok(b"<html>err</html>"), TRADING).klass == "drift"
    assert c(MI, ok(b"{not json"), TRADING).klass == "drift"
    assert c(MI, ok(b"\xff\xfe"), TRADING).klass == "drift"


def test_ok_with_rows_and_mi_index_table_selection():
    r = c(MI, ok(mi_index()), TRADING)
    assert (r.klass, r.rows) == ("ok", 1)
    r = c(MI, ok(mi_index(rows=[["a", "b", "c"], ["d", "e", "f"]])), TRADING)
    assert r.rows == 2
    assert c(MI, ok(mi_index(titles=("指數",))), TRADING).klass == "drift"


def test_stat_not_ok_trading_day_is_drift_holiday_is_ok_empty():
    body = jb({"stat": "很抱歉，沒有符合條件的資料!", "total": 0})
    assert c(QF, ok(body), TRADING).klass == "drift"
    r = c(QF, ok(body), HOLIDAY)
    assert (r.klass, r.rows) == ("ok", 0)
    assert c(QF, ok(body), OUTSIDE).klass == "drift"
    assert c(QF, ok(body), TRADING, allow_empty=True).klass == "ok"


def test_known_no_data_on_range_and_stock_month():
    for spec in (RNG, SM):
        r = classify(spec, ok(NO_DATA))
        assert (r.klass, r.rows) == ("ok", 0)
    assert classify(RNG, ok(jb({"stat": "bad", "total": 0}))).klass == "drift"
    assert classify(RNG, ok(jb({"stat": "很抱歉", "total": 0, "x": 1}))).klass == "ok"


def test_tpex_lowercase_ok_and_uppercase_is_drift():
    assert c(OTC, ok(tpex()), TRADING).klass == "ok"
    assert c(OTC, ok(tpex(stat="OK")), TRADING).klass == "drift"


def test_tpex_empty_holiday():
    r = c(OTC, ok(tpex(rows=[])), HOLIDAY)
    assert (r.klass, r.rows) == ("ok", 0)
    assert c(OTC, ok(tpex(rows=[])), TRADING).klass == "drift"
    assert c(OTC, ok(tpex(rows=[])), TRADING, allow_empty=True).klass == "ok"
    assert c(OTC, ok(jb({"stat": "ok", "tables": []})), HOLIDAY).klass == "ok"


def test_zero_rows_outside_calendar_is_drift_unless_allowed():
    assert c(QF, ok(twse_top(rows=[])), OUTSIDE).klass == "drift"
    assert c(QF, ok(twse_top(rows=[])), OUTSIDE, allow_empty=True).klass == "ok"
    assert classify(QF, ok(twse_top(rows=[])), date=TRADING).klass == "drift"


def test_empty_range_snapshot_stock_month_ok():
    assert classify(RNG, ok(twse_top(rows=[]))).klass == "ok"
    assert classify(SM, ok(twse_top(rows=[]))).klass == "ok"
    snap = openapi_spec("twse", "/exchangeReport/TWT85U")
    assert classify(snap, ok(b"[]")).klass == "ok"
    assert classify(snap, ok(jb([{"a": 1}, {"a": 2}]))).rows == 2
    assert classify(snap, ok(jb({"a": 1}))).klass == "drift"


def test_field_list_outside_every_era(monkeypatch):
    E = schema.Era
    monkeypatch.setitem(
        schema.ERAS,
        "tpex.otc",
        [E(None, date(2020, 4, 29), tuple(FIELDS)), E(date(2020, 4, 30), None, (*FIELDS, "x"))],
    )
    assert c(OTC, ok(tpex(fields=["x", "y", "z"])), TRADING).klass == "drift"
    d2 = date(2025, 6, 5)  # era 2 is open from 2020-04-30
    assert c(OTC, ok(tpex()), d2).klass == "drift"
    assert c(OTC, ok(tpex(fields=[*FIELDS, "x"])), d2).klass == "ok"
    assert c(OTC, ok(tpex()), date(2019, 6, 5)).klass == "ok"
    monkeypatch.setitem(schema.ERAS, "tpex.otc", [E(None, None, tuple(FIELDS))])
    assert c(OTC, ok(tpex(fields=["證券 代號", "證券名稱", " 收盤價 "])), TRADING).klass == "ok"


def test_missing_shape_is_drift():
    assert c(QF, ok(jb({"stat": "OK"})), TRADING).klass == "drift"
    assert c(OTC, ok(jb({"stat": "ok"})), TRADING).klass == "drift"


def test_twse_holiday_reply_shape_is_known_no_data():
    """The real TWSE reply on a holiday has keys stat and type, no total (observed 2025-10-10)."""
    import json
    from datetime import date

    from twdata.clients.classifier import classify
    from twdata.clients.transport import HttpResult
    from twdata.common.endpoints import ENDPOINTS
    from twdata.common.tradingcal import TradingCalendar

    body = json.dumps({"stat": "很抱歉，沒有符合條件的資料!", "type": "ALLBUT0999"}).encode()
    res = HttpResult(200, {}, body)
    spec = ENDPOINTS["twse.mi_index"]
    cal = TradingCalendar([date(2025, 10, 9), date(2025, 10, 13)])
    holiday = date(2025, 10, 10)
    assert classify(spec, res, date=holiday, calendar=cal).klass == "ok"
    # on a trading day it is drift unless allow_empty is set
    assert classify(spec, res, date=date(2025, 10, 9), calendar=cal).klass == "drift"
    assert classify(spec, res, date=date(2025, 10, 9), calendar=cal, allow_empty=True).klass == "ok"
    # outside the calendar it is drift unless allow_empty is set (the 2015 stub passes it)
    assert classify(spec, res, date=date(2015, 3, 3), calendar=cal).klass == "drift"
    assert classify(spec, res, date=date(2015, 3, 3), calendar=cal, allow_empty=True).klass == "ok"
