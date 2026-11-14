import dataclasses
from datetime import date

import pytest
from fixtures_inline import (
    FIELDS,
    HOLIDAY,
    NO_DATA,
    TRADING,
    FakeCache,
    FakeLimiter,
    FakeTransport,
    jb,
    mi_index,
    ok,
    settings,
    tpex,
    twse_top,
)

from twdata.clients import context
from twdata.clients.tpex import TpexClient
from twdata.clients.twse import TwseClient
from twdata.common import schema
from twdata.common.endpoints import ENDPOINTS


@pytest.fixture(autouse=True)
def no_eras(monkeypatch):
    monkeypatch.setattr(schema, "ERAS", {})


def mk(tmp_path, cls, body_result):
    from fixtures_inline import CAL

    t = FakeTransport(body_result)
    c = cls(settings(tmp_path), FakeLimiter(), FakeCache(), t, calendar=CAL, sleep=lambda s: None)
    return c, t


D = TRADING
S, E = date(2025, 1, 1), date(2025, 6, 30)


def test_twse_per_date_requests(tmp_path):
    cases = [
        ("mi_index", (D,), "afterTrading/MI_INDEX", {"date": "20250603", "type": "ALLBUT0999"}),
        ("mi_qfiis", (D,), "fund/MI_QFIIS", {"date": "20250603", "selectType": "ALLBUT0999"}),
        ("twt84u", (D,), "variation/TWT84U", {"date": "20250603"}),
        ("bwibbu_d", (D,), "afterTrading/BWIBBU_d", {"date": "20250603", "selectType": "ALL"}),
    ]
    for name, args, path, extra in cases:
        body = mi_index() if name == "mi_index" else twse_top()
        c, t = mk(tmp_path, TwseClient, ok(body))
        rows, resp = getattr(c, name)(*args)
        assert rows == [dict(zip(FIELDS, ["2330", "台積電", "1,000.00"], strict=True))]
        _, url, params, headers, timeout = t.calls[0]
        assert url == "https://www.twse.com.tw/rwd/zh/" + path
        assert params == {"response": "json", **extra}
        assert headers["User-Agent"] and timeout == 150


def test_twse_stock_day_and_ranges(tmp_path):
    c, t = mk(tmp_path, TwseClient, ok(twse_top()))
    c.stock_day(date(2016, 12, 5), "3474")
    assert t.calls[0][2] == {"response": "json", "date": "20161205", "stockNo": "3474"}
    for name, path in [
        ("twt49u", "exRight/TWT49U"),
        ("twtauu", "reducation/TWTAUU"),
        ("twtawu", "afterTrading/TWTAWU"),
        ("punish", "announcement/punish"),
        ("notice", "announcement/notice"),
    ]:
        c, t = mk(tmp_path, TwseClient, ok(twse_top()))
        rows, _ = getattr(c, name)(S, E)
        assert len(rows) == 1
        assert t.calls[0][1].endswith(path)
        assert t.calls[0][2] == {"response": "json", "startDate": "20250101", "endDate": "20250630"}


def test_twse_empty_range_reply_is_empty_rows(tmp_path):
    c, _ = mk(tmp_path, TwseClient, ok(NO_DATA))
    rows, resp = c.twt49u(S, E)
    assert rows == [] and resp.klass == "ok"
    c, _ = mk(tmp_path, TwseClient, ok(NO_DATA))
    assert c.stock_day(date(2016, 12, 5), "3474")[0] == []


def test_mi_index_tr_selects_index_table_from_same_request(tmp_path):
    c, t = mk(tmp_path, TwseClient, ok(mi_index(titles=("報酬指數", "每日收盤行情(全部)"))))
    rows, resp = c.mi_index(D)
    assert rows[0]["證券代號"] == "2330"
    rows, resp = c.mi_index_tr(D)
    assert rows == [{"a": "x"}] and resp.from_cache
    assert len(t.calls) == 1  # same request key, served from the cache


def test_twse_openapi_snapshot(tmp_path):
    c, t = mk(tmp_path, TwseClient, ok(jb([{"Code": "2330"}, {"Code": "2317"}])))
    rows, _ = c.openapi("/exchangeReport/TWT85U")
    assert rows == [{"Code": "2330"}, {"Code": "2317"}]
    assert t.calls[0][1] == "https://openapi.twse.com.tw/v1/exchangeReport/TWT85U"
    assert t.calls[0][2] == {}


def test_tpex_per_date(tmp_path):
    for name, path, extra in [
        ("otc", "afterTrading/otc", {"type": "EW"}),
        ("chtm", "afterTrading/chtm", {}),
    ]:
        c, t = mk(tmp_path, TpexClient, ok(tpex()))
        rows, _ = getattr(c, name)(D)
        assert rows[0]["證券代號"] == "2330"
        _, url, params, _, timeout = t.calls[0]
        assert url == "https://www.tpex.org.tw/www/zh-tw/" + path and timeout == 60
        assert params == {"response": "json", "date": "2025/06/03", **extra}


def test_tpex_empty_holiday(tmp_path):
    c, _ = mk(tmp_path, TpexClient, ok(tpex(rows=[])))
    rows, resp = c.otc(HOLIDAY)
    assert rows == [] and resp.klass == "ok"


def test_tpex_ranges_stock_month_and_delisted(tmp_path):
    for name, path, extra in [
        ("ex_daily", "bulletin/exDailyQ", {}),
        ("revivt", "bulletin/revivt", {}),
        ("disposal", "bulletin/disposal", {"type": "all"}),
        ("attention", "bulletin/attention", {}),
    ]:
        c, t = mk(tmp_path, TpexClient, ok(tpex()))
        c_rows, _ = getattr(c, name)(S, E)
        assert len(c_rows) == 1
        assert t.calls[0][1] == "https://www.tpex.org.tw/www/zh-tw/" + path
        assert t.calls[0][2] == {
            "response": "json",
            "startDate": "2025/01/01",
            "endDate": "2025/06/30",
            **extra,
        }
    c, t = mk(tmp_path, TpexClient, ok(tpex()))
    c.trading_stock(date(2025, 6, 1), "6488")
    assert t.calls[0][2] == {"response": "json", "date": "2025/06/01", "code": "6488"}
    c, t = mk(tmp_path, TpexClient, ok(tpex()))
    c.deListed(date(2024, 3, 3))
    assert t.calls[0][2] == {"response": "json", "date": "2024", "code": "", "reason": "-1"}


def test_tpex_openapi(tmp_path):
    c, t = mk(tmp_path, TpexClient, ok(jb([{"a": 1}])))
    rows, _ = c.openapi("/tpex_spendi_today")
    assert rows == [{"a": 1}]
    assert t.calls[0][1] == "https://www.tpex.org.tw/openapi/v1/tpex_spendi_today"


def test_roc_dates_stay_strings(tmp_path):
    body = jb({"stat": "OK", "fields": ["日期", "x"], "data": [["114/06/03", "1"]]})
    c, _ = mk(tmp_path, TwseClient, ok(body))
    rows, _ = c.twt49u(S, E)
    assert rows == [{"日期": "114/06/03", "x": "1"}]


def test_every_spec_row_has_a_method():
    methods = {k.split(".", 1)[1] for k in ENDPOINTS if k.startswith("twse.")}
    assert methods <= set(dir(TwseClient))
    tm = {k.split(".", 1)[1] for k in ENDPOINTS if k.startswith("tpex.")}
    assert tm <= set(dir(TpexClient))


def test_build_context_with_injected_fakes(tmp_path):
    s = settings(tmp_path)
    t = FakeTransport(ok(twse_top()))
    cache = FakeCache()
    ctx = context.build_context(
        s,
        transport=t,
        limiter_factory=lambda host: FakeLimiter(),
        cache_factory=lambda: cache,
        writers=lambda table: ("writer", table),
    )
    assert ctx.finmind is None and ctx.cache is cache and ctx.calendar is None
    assert ctx.writers("prices_raw") == ("writer", "prices_raw")
    assert ctx.twse.host == "twse" and ctx.tpex.host == "tpex"
    ctx.twse.twt84u  # noqa: B018 - attribute exists


def test_build_context_finmind_reads_user_info_once(tmp_path, monkeypatch):
    monkeypatch.setenv("FINMIND_TOKEN", "FAKE-TOKEN")
    limiters = {}

    def lf(host):
        limiters[host] = FakeLimiter()
        return limiters[host]

    info = jb({"status": 200, "level_title": "Free", "api_request_limit": 600, "user_count": 3})
    ctx = context.build_context(
        settings(tmp_path),
        transport=FakeTransport(ok(info)),
        finmind=True,
        limiter_factory=lf,
        cache_factory=FakeCache,
        writers=lambda t: t,
    )
    assert ctx.finmind is not None and limiters["finmind"].updates == [(600, 3)]
    assert dataclasses.is_dataclass(ctx)


def test_openapi_bypasses_the_cache_by_default(tmp_path):
    """Two runs on different days must both reach the network (snapshots depend on it)."""
    for cls, path in ((TwseClient, "/exchangeReport/TWT85U"), (TpexClient, "/tpex_spendi_today")):
        s = settings(tmp_path)
        t = FakeTransport(ok(jb([{"a": 1}])), ok(jb([{"a": 2}])))
        c = cls(s, FakeLimiter(), FakeCache(), t, calendar=None, sleep=lambda x: None)
        r1, _ = c.openapi(path)
        r2, _ = c.openapi(path)
        assert r1 == [{"a": 1}] and r2 == [{"a": 2}]
        assert len(t.calls) == 2
        # an explicit use_cache=True still reads the cache
        r3, _ = c.openapi(path, use_cache=True)
        assert len(t.calls) == 2 and r3 in ([{"a": 1}], [{"a": 2}])
