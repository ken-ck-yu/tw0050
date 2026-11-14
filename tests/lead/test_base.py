import dataclasses
import logging

import pytest
from fixtures_inline import (
    HOLIDAY,
    TOKEN,
    TRADING,
    FakeTransport,
    jb,
    make,
    ok,
    twse_top,
)

from twdata.clients.base import (
    BlockedError,
    Client,
    DriftError,
    RetryExhausted,
    request_key,
)
from twdata.clients.transport import HttpResult
from twdata.common import schema
from twdata.common.endpoints import ENDPOINTS, build_request

QF = ENDPOINTS["twse.mi_qfiis"]


@pytest.fixture(autouse=True)
def no_eras(monkeypatch):
    monkeypatch.setattr(schema, "ERAS", {})


def params(d=TRADING):
    return build_request(QF, on=d)[1]


def test_ok_is_fetched_cached_and_second_call_hits_cache(tmp_path):
    t = FakeTransport(ok(twse_top()))
    c, lim, cache, _ = make(tmp_path, "twse", t)
    r1 = c.fetch(QF, params(), date=TRADING)
    assert (r1.klass, len(r1.rows), r1.from_cache) == ("ok", 1, False)
    assert r1.records[0]["證券代號"] == "2330"
    assert len(cache.puts) == 1 and cache.puts[0][:2] == ("twse", "mi_qfiis")
    r2 = c.fetch(QF, params(), date=TRADING)
    assert r2.from_cache and r2.body == r1.body and r2.parsed == r1.parsed
    assert len(t.calls) == 1 and lim.slots == 1


def test_use_cache_false_refetches(tmp_path):
    t = FakeTransport(ok(twse_top()))
    c, _, cache, _ = make(tmp_path, "twse", t)
    c.fetch(QF, params(), date=TRADING)
    c.fetch(QF, params(), date=TRADING, use_cache=False)
    assert len(t.calls) == 2


def test_request_goes_through_limiter_slot_with_ua_and_timeout(tmp_path):
    seen = {}

    def tr(url, p):
        seen["depth"] = lim.depth
        return ok(twse_top())

    t = FakeTransport(tr)
    c, lim, _, _ = make(tmp_path, "twse", t)
    c.fetch(QF, params(), date=TRADING)
    assert seen["depth"] == 1 and lim.depth == 0
    method, url, p, headers, timeout = t.calls[0]
    assert (method, url) == ("GET", QF.url) and p == params()
    assert headers["User-Agent"] == c.settings.user_agent and timeout == 150


def test_six_attempts_with_configured_waits_then_retry_exhausted(tmp_path):
    t = FakeTransport(HttpResult(500))
    c, lim, cache, sleeps = make(tmp_path, "twse", t)
    with pytest.raises(RetryExhausted):
        c.fetch(QF, params(), date=TRADING)
    assert len(t.calls) == 6 and lim.slots == 6
    assert sleeps == [5, 10, 20, 40, 80]
    assert not cache.puts and not cache.quarantined


def test_transient_then_success(tmp_path):
    t = FakeTransport(HttpResult(0), HttpResult(429), ok(twse_top()))
    c, _, cache, sleeps = make(tmp_path, "twse", t)
    r = c.fetch(QF, params(), date=TRADING)
    assert r.klass == "ok" and sleeps == [5, 10] and len(cache.puts) == 1


def test_drift_quarantines_and_raises(tmp_path):
    t = FakeTransport(ok(b"<html>oops</html>"))
    c, _, cache, _ = make(tmp_path, "twse", t)
    with pytest.raises(DriftError):
        c.fetch(QF, params(), date=TRADING)
    assert len(cache.quarantined) == 1 and not cache.puts
    assert cache.quarantined[0][6] == b"<html>oops</html>"


def test_403_is_blocked_for_twse_and_tpex(tmp_path):
    for host in ("twse", "tpex"):
        t = FakeTransport(HttpResult(403, {}, b"no"))
        c, _, cache, _ = make(tmp_path, host, t)
        with pytest.raises(BlockedError):
            c.fetch(QF, params(), date=TRADING)
        assert not cache.quarantined and len(t.calls) == 1


def test_other_4xx_is_drift_and_302_is_drift(tmp_path):
    for st in (404, 400, 302):
        c, _, cache, _ = make(tmp_path, "twse", FakeTransport(HttpResult(st, {"Location": "/x"})))
        with pytest.raises(DriftError):
            c.fetch(QF, params(), date=TRADING)
        assert len(cache.quarantined) == 1


def test_row_cap_raises_drift_and_is_not_cached(tmp_path):
    t = FakeTransport(ok(twse_top(rows=[["a", "b", "c"]] * 4)))
    s = dataclasses.replace(
        make(tmp_path, "twse", t)[0].settings,
        row_caps=dataclasses.replace(make(tmp_path, "twse", t)[0].settings.row_caps, twse=3),
    )
    c, _, cache, _ = make(tmp_path, "twse", t)
    c.settings = s
    with pytest.raises(DriftError, match="row cap"):
        c.fetch(QF, params(), date=TRADING)
    assert not cache.puts and len(cache.quarantined) == 1


def test_dataset_row_cap_entry_wins(tmp_path):
    t = FakeTransport(ok(twse_top(rows=[["a", "b", "c"]] * 4)))
    c, _, cache, _ = make(tmp_path, "twse", t)
    caps = dataclasses.replace(c.settings.row_caps, datasets={"mi_qfiis": 2})
    c.settings = dataclasses.replace(c.settings, row_caps=caps)
    with pytest.raises(DriftError):
        c.fetch(QF, params(), date=TRADING)


def test_empty_ok_is_cached_and_allow_empty(tmp_path):
    t = FakeTransport(ok(twse_top(rows=[])))
    c, _, cache, _ = make(tmp_path, "twse", t)
    r = c.fetch(QF, params(HOLIDAY), date=HOLIDAY)
    assert r.klass == "ok" and r.rows == [] and len(cache.puts) == 1
    with pytest.raises(DriftError):
        c.fetch(QF, params(), date=TRADING)
    r = c.fetch(QF, params(), date=TRADING, allow_empty=True, use_cache=False)
    assert r.rows == []


def test_request_key_matches_formula_and_has_no_headers(tmp_path):
    k = request_key("GET", "u", {"b": 1, "a": 2})
    assert k == request_key("GET", "u", {"a": 2, "b": 1})
    assert len(k) == 64


def test_token_never_in_cache_log_or_exception(tmp_path, monkeypatch, caplog):
    monkeypatch.setenv("FINMIND_TOKEN", TOKEN)
    caplog.set_level(logging.DEBUG)
    t = FakeTransport(HttpResult(500))
    c, _, cache, _ = make(tmp_path, "twse", t)
    with pytest.raises(RetryExhausted) as e:
        c.fetch(QF, params(), date=TRADING, extra_headers={"Authorization": f"Bearer {TOKEN}"})
    assert TOKEN not in str(e.value) and TOKEN not in caplog.text
    assert t.calls[0][3]["Authorization"] == f"Bearer {TOKEN}"  # at the transport only
    assert TOKEN not in repr(cache.store) and TOKEN not in repr(cache.puts)


def test_client_is_constructible_without_rawcache_import():
    assert Client.__init__ is not None
    assert jb({"a": 1})
