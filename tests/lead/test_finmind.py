import dataclasses
import logging
from datetime import date

import pytest
from fixtures_inline import TOKEN, FakeTransport, jb, make, ok

from twdata.clients.base import (
    AuthError,
    BlockedError,
    DriftError,
    RetryExhausted,
)
from twdata.clients.finmind import FinMindClient
from twdata.clients.transport import HttpResult

PRICE = {"date": "2025-06-03", "stock_id": "2330", "close": 1000.0}
BODY = jb({"msg": "success", "status": 200, "data": [PRICE]})
INFO = jb(
    {
        "msg": "success",
        "status": 200,
        "level_title": "Free",
        "api_request_limit": 600,
        "user_count": 12,
    }
)


@pytest.fixture(autouse=True)
def token(monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", TOKEN)


def fm(tmp_path, *results, **kw):
    t = FakeTransport(*results)
    c, lim, cache, sleeps = make(tmp_path, FinMindClient, t, **kw)
    return c, t, lim, cache, sleeps


def test_dataset_request_and_rows(tmp_path):
    c, t, lim, cache, _ = fm(tmp_path, ok(BODY))
    rows = c.dataset("TaiwanStockPrice", date(2025, 6, 3), date(2025, 6, 10), "2330")
    assert rows == [PRICE]
    method, url, params, headers, timeout = t.calls[0]
    assert url == "https://api.finmindtrade.com/api/v4/data" and timeout == 60
    assert params == {
        "dataset": "TaiwanStockPrice",
        "start_date": "2025-06-03",
        "end_date": "2025-06-10",
        "data_id": "2330",
    }
    assert headers["Authorization"] == f"Bearer {TOKEN}"
    assert cache.puts[0][:2] == ("finmind", "TaiwanStockPrice")
    assert lim.slots == 1


def test_end_date_omitted_when_none_and_cache_first(tmp_path):
    c, t, *_ = fm(tmp_path, ok(BODY))
    c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    assert "end_date" not in t.calls[0][2] and "data_id" not in t.calls[0][2]
    c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    assert len(t.calls) == 1


def test_header_only_at_transport_never_stored_or_logged(tmp_path, caplog):
    caplog.set_level(logging.DEBUG)
    c, t, lim, cache, _ = fm(tmp_path, ok(BODY))
    c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    assert TOKEN not in repr(cache.store) and TOKEN not in repr(cache.puts)
    assert TOKEN not in caplog.text
    assert TOKEN not in repr(vars(c)) and TOKEN not in repr(c.settings)
    for key in cache.store:
        assert TOKEN not in "".join(map(str, key))


@pytest.mark.parametrize(
    "http,body,exc",
    [
        (400, b'{"msg":"TokenIllegal","status":400}', AuthError),
        (401, b'{"msg":"x","status":401}', AuthError),
        (402, b'{"msg":"Requests reach the upper limit","status":402}', BlockedError),
        (403, b'{"msg":"permission","status":403}', BlockedError),
        (429, b'{"msg":"slow","status":429}', BlockedError),
        (404, b"{}", BlockedError),
    ],
)
def test_http_errors_stop_with_the_right_exception(tmp_path, http, body, exc):
    c, t, *_, cache, sleeps = fm(tmp_path, HttpResult(http, {}, body))
    with pytest.raises(exc) as e:
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    assert TOKEN not in str(e.value)
    assert len(t.calls) == 1 and not sleeps and not cache.puts


def test_in_body_status_other_than_200_is_an_error(tmp_path):
    c, *_ = fm(tmp_path, ok(b'{"msg":"limit","status":402}'))
    with pytest.raises(BlockedError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    c, *_ = fm(tmp_path, ok(b'{"msg":"bad token","status":400}'))
    with pytest.raises(AuthError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    c, *_, cache, _ = fm(tmp_path, ok(b'{"msg":"?","status":302}'))
    with pytest.raises(DriftError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    c, *_ = fm(tmp_path, ok(b'{"msg":"no status","data":[]}'))
    with pytest.raises(DriftError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))


def test_body_5xx_and_http_5xx_are_transient(tmp_path):
    c, t, *_, cache, sleeps = fm(tmp_path, ok(b'{"msg":"oops","status":500}'), ok(BODY))
    assert c.dataset("TaiwanStockPrice", date(2025, 6, 3)) == [PRICE]
    assert sleeps == [5] and len(t.calls) == 2
    c, t, *_, sleeps = fm(tmp_path, HttpResult(0))
    with pytest.raises(RetryExhausted):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    assert len(t.calls) == 6 and sleeps == [5, 10, 20, 40, 80]


def test_row_cap(tmp_path):
    c, *_ = fm(tmp_path, ok(jb({"status": 200, "data": [PRICE] * 5})))
    caps = dataclasses.replace(c.settings.row_caps, datasets={"TaiwanStockPrice": 4})
    c.settings = dataclasses.replace(c.settings, row_caps=caps)
    with pytest.raises(DriftError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    c, *_ = fm(tmp_path, ok(jb({"status": 200, "data": [PRICE] * 5})))
    caps = dataclasses.replace(c.settings.row_caps, finmind_default=4)
    c.settings = dataclasses.replace(c.settings, row_caps=caps)
    with pytest.raises(DriftError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))


def test_user_info_updates_quota_limiter_and_is_not_cached(tmp_path):
    c, t, lim, cache, _ = fm(tmp_path, ok(INFO))
    q = c.user_info()
    assert (q.level, q.limit, q.user_count) == ("Free", 600, 12)
    assert lim.updates == [(600, 12)] and not cache.puts
    assert t.calls[0][1] == "https://api.web.finmindtrade.com/v2/user_info"
    c.user_info()
    assert len(t.calls) == 2


def test_user_info_refresh_every_n_requests(tmp_path):
    def reply(url, params):
        return ok(INFO) if "user_info" in url else ok(BODY)

    s_kw = None
    c, t, lim, *_ = fm(tmp_path, reply, settings_kw=s_kw)
    fin = dataclasses.replace(c.settings.finmind, user_info_refresh_requests=2)
    c.settings = dataclasses.replace(c.settings, finmind=fin)
    for d in (3, 4, 5):
        c.dataset("TaiwanStockPrice", date(2025, 6, d))
    assert len(lim.updates) == 1
    assert sum("user_info" in call[1] for call in t.calls) == 1


def test_missing_token_raises_auth_without_request(tmp_path, monkeypatch):
    monkeypatch.delenv("FINMIND_TOKEN")
    c, t, *_ = fm(tmp_path, ok(BODY))
    with pytest.raises(AuthError):
        c.dataset("TaiwanStockPrice", date(2025, 6, 3))
    assert not t.calls
