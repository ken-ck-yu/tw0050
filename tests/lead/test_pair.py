import json

import pytest
from fixtures_inline import (
    CAL,
    HOLIDAY,
    NO_DATA,
    OUTSIDE,
    TRADING,
    FakeCache,
    FakeLimiter,
    FakeTransport,
    ok,
    settings,
    tpex,
    twse_top,
)

from twdata.clients.base import DriftError
from twdata.clients.pair import fetch_daily_pair
from twdata.clients.tpex import TpexClient
from twdata.clients.twse import TwseClient
from twdata.common import schema


@pytest.fixture(autouse=True)
def no_eras(monkeypatch):
    monkeypatch.setattr(schema, "ERAS", {})


def clients(tmp_path, tw_body, tp_body, calendar=CAL):
    s = settings(tmp_path)
    cache = FakeCache()
    tw = TwseClient(s, FakeLimiter(), cache, FakeTransport(ok(tw_body)), calendar=calendar)
    tp = TpexClient(s, FakeLimiter(), cache, FakeTransport(ok(tp_body)), calendar=calendar)
    return tw, tp, tmp_path / "ledger.jsonl"


def test_both_with_rows(tmp_path):
    tw, tp, led = clients(tmp_path, twse_top(), tpex())
    a, b = fetch_daily_pair(tw, tp, TRADING, "twse.mi_qfiis", "tpex.otc", led)
    assert a.rows and b.rows and not led.exists()


def test_both_empty_on_trading_day_writes_ledger_once(tmp_path):
    tw, tp, led = clients(tmp_path, twse_top(rows=[]), tpex(rows=[]))
    a, b = fetch_daily_pair(tw, tp, TRADING, "twse.mi_qfiis", "tpex.otc", led)
    assert a.klass == b.klass == "ok" and a.rows == [] and b.rows == []
    lines = [json.loads(x) for x in led.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 1
    assert lines[0]["date"] == "2025-06-03"
    assert lines[0]["twse_endpoint"] == "twse.mi_qfiis" and lines[0]["tpex_endpoint"] == "tpex.otc"
    assert "recorded_at" in lines[0]
    fetch_daily_pair(tw, tp, TRADING, "twse.mi_qfiis", "tpex.otc", led)  # rerun: no duplicate
    assert len(led.read_text(encoding="utf-8").splitlines()) == 1


def test_one_empty_raises_either_way(tmp_path):
    tw, tp, led = clients(tmp_path, twse_top(), tpex(rows=[]))
    with pytest.raises(DriftError):
        fetch_daily_pair(tw, tp, TRADING, "twse.mi_qfiis", "tpex.otc", led)
    tw, tp, led = clients(tmp_path, twse_top(rows=[]), tpex())
    with pytest.raises(DriftError):
        fetch_daily_pair(tw, tp, TRADING, "twse.mi_qfiis", "tpex.otc", led)
    assert not led.exists()


def test_both_empty_on_non_trading_day_no_ledger(tmp_path):
    tw, tp, led = clients(tmp_path, NO_DATA, tpex(rows=[]))
    fetch_daily_pair(tw, tp, HOLIDAY, "twse.mi_qfiis", "tpex.otc", led)
    assert not led.exists()


def test_both_empty_outside_calendar_is_drift(tmp_path):
    tw, tp, led = clients(tmp_path, twse_top(rows=[]), tpex(rows=[]))
    with pytest.raises(DriftError):
        fetch_daily_pair(tw, tp, OUTSIDE, "twse.mi_qfiis", "tpex.otc", led)
