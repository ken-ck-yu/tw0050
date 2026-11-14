from datetime import date

import pytest

from twdata.common import endpoints as E
from twdata.common import schema as S
from twdata.common.sanity import SanityError, check_price_row, tick_size


def test_sanity_rows():
    check_price_row({"open": 10, "high": 11, "low": 9, "close": 10})
    check_price_row({"open": None, "high": None, "low": None, "close": None})
    with pytest.raises(SanityError):
        check_price_row({"open": 10, "high": 9, "low": 11, "close": 10})
    with pytest.raises(SanityError):
        check_price_row({"open": 10, "high": 11, "low": 9, "close": 12})
    with pytest.raises(SanityError):
        check_price_row({"open": -1, "high": 1, "low": 0, "close": 1})


def test_tick_size():
    assert [tick_size(p) for p in (5, 20, 80, 300, 700, 1500)] == [0.01, 0.05, 0.1, 0.5, 1.0, 5.0]


def test_tables_registered_with_valid_keys():
    assert "prices_raw" in S.TABLES and "universe_membership" in S.TABLES
    for t in S.TABLES.values():
        assert all(k in t.columns for k in t.key), t.name
        assert t.part in t.columns, t.name
        assert "fetched_at" in t.columns
        if t.klass == "joinable":
            assert {"event_date", "available_at"} <= set(t.columns)
    assert S.TABLES["securities_lending"].key[-1] == "seq"
    assert S.TABLES["prices_raw"].columns["close"].endswith("?")


def test_snapshot_table_and_era_matching():
    t = S.snapshot_table("twse_TWT85U")
    assert t.name == "snapshot_twse_TWT85U" and t.klass == "joinable"
    S.register_era("test.ep", S.Era(None, date(2020, 4, 29), ("a ", "b")))
    S.register_era("test.ep", S.Era(date(2020, 4, 30), None, ("a", "b", "c")))
    assert S.fields_valid("test.ep", date(2019, 1, 1), ["a", " b"])
    assert not S.fields_valid("test.ep", date(2021, 1, 1), ["a", "b"])
    assert S.fields_valid("test.ep", date(2021, 1, 1), ["a", "b", "c"])
    assert S.fields_valid("unregistered", date(2021, 1, 1), ["x"])


def test_request_construction():
    url, p = E.build_request(E.ENDPOINTS["twse.mi_index"], on=date(2016, 6, 1))
    assert url == "https://www.twse.com.tw/rwd/zh/afterTrading/MI_INDEX"
    assert p == {"response": "json", "type": "ALLBUT0999", "date": "20160601"}
    url, p = E.build_request(E.ENDPOINTS["tpex.otc"], on=date(2016, 6, 1))
    assert url.endswith("afterTrading/otc") and p["date"] == "2016/06/01" and p["type"] == "EW"
    url, p = E.build_request(
        E.ENDPOINTS["twse.twt49u"], start=date(2015, 6, 1), end=date(2026, 11, 13)
    )
    assert p["startDate"] == "20150601" and p["endDate"] == "20261113"
    url, p = E.build_request(
        E.ENDPOINTS["tpex.disposal"], start=date(2020, 6, 1), end=date(2020, 6, 30)
    )
    assert p["startDate"] == "2020/06/01" and p["type"] == "all"
    url, p = E.build_request(E.ENDPOINTS["twse.stock_day"], on=date(2019, 5, 1), stockNo="2475")
    assert p["stockNo"] == "2475" and p["date"] == "20190501"
    url, p = E.build_request(E.ENDPOINTS["tpex.deListed"], on=date(2018, 3, 1))
    assert p["date"] == "2018" and p["reason"] == "-1" and p["code"] == ""
    with pytest.raises(ValueError):
        E.build_request(E.ENDPOINTS["twse.mi_index"])
    with pytest.raises(ValueError):
        E.build_request(E.ENDPOINTS["twse.stock_day"], on=date(2019, 5, 1))
    spec = E.openapi_spec("twse", "/exchangeReport/TWT85U")
    assert spec.url == "https://openapi.twse.com.tw/v1/exchangeReport/TWT85U"
    assert spec.kind == "snapshot" and spec.stat_ok is None
