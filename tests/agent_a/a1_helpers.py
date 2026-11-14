"""Offline helpers for the agent A-1 tests: a routing fake transport, fake limiter and cache,
and a context builder. Nothing here touches the network or a token."""

from __future__ import annotations

import contextlib
import copy
import json
from datetime import date
from pathlib import Path

import duckdb

from twdata.clients.context import build_context
from twdata.clients.transport import HttpResult
from twdata.common import config, views
from twdata.common.tradingcal import TradingCalendar

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "lead"


def fixture_bytes(rel: str) -> bytes:
    return (FIX / rel).read_bytes()


def fixture_json(rel: str):
    return json.loads(fixture_bytes(rel).decode("utf-8"))


def jb(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def mi_index_body(mutate=None) -> bytes:
    obj = fixture_json("twse/mi_index_20160601.json")
    if mutate:
        mutate(obj)
    return jb(obj)


def empty_mi_index() -> bytes:
    def m(obj):
        for t in obj["tables"]:
            if t.get("title") and "每日收盤行情" in t["title"]:
                t["data"] = []

    return mi_index_body(m)


def empty_otc(rel: str = "tpex/otc_20160601.json") -> bytes:
    obj = fixture_json(rel)
    obj["tables"][0]["data"] = []
    return jb(obj)


def qfiis_body(drop_ids=()) -> bytes:
    obj = fixture_json("twse/mi_qfiis_20220601.json")
    obj["data"] = [r for r in obj["data"] if r[0] not in drop_ids]
    return jb(obj)


class FakeLimiter:
    @contextlib.contextmanager
    def slot(self):
        yield

    def update(self, limit_per_hour, user_count):
        pass


class CountingCache:
    """In-memory raw cache with the RawCache surface the clients use."""

    def __init__(self):
        self.store = {}
        self.flushes = 0

    def put(self, source, dataset, request_key, url, params, status, body, fetched_at):
        self.store[(source, dataset, request_key)] = (status, body, fetched_at)

    def get(self, source, dataset, request_key):
        hit = self.store.get((source, dataset, request_key))
        if hit is None:
            return None
        from types import SimpleNamespace

        return SimpleNamespace(status=hit[0], body=hit[1], fetched_at=hit[2], shard="fake")

    def put_quarantine(self, *a, **k):
        pass

    def flush(self):
        self.flushes += 1


class Router:
    """Fake transport: `routes` is a list of (url substring, callable(params) -> body bytes or
    HttpResult). First match wins. Every call is recorded."""

    def __init__(self, routes):
        self.routes = routes
        self.calls = []

    def __call__(self, method, url, params, headers, timeout):
        self.calls.append((url, dict(params)))
        for sub, fn in self.routes:
            if sub in url:
                r = fn(params)
                return r if isinstance(r, HttpResult) else HttpResult(200, {}, r)
        raise AssertionError(f"unrouted url {url}")


def daily_routes(mi=None, otc=None, qfiis=None):
    """Routes for the three daily endpoints. Each argument is bytes or a callable(params)."""

    def pick(x, default):
        x = default if x is None else x
        return x if callable(x) else (lambda params: x)

    return [
        ("MI_INDEX", pick(mi, mi_index_body())),
        ("MI_QFIIS", pick(qfiis, qfiis_body())),
        ("afterTrading/otc", pick(otc, fixture_bytes("tpex/otc_20160601.json"))),
    ]


def settings_for(tmp_path):
    return config.load_settings(data_dir_override=str(tmp_path))


def make_ctx(tmp_path, routes, days):
    s = settings_for(tmp_path)
    transport = Router(routes)
    cache = CountingCache()
    ctx = build_context(
        s,
        transport=transport,
        limiter_factory=lambda host: FakeLimiter(),
        cache_factory=lambda: cache,
        calendar=TradingCalendar(days),
        sleep=lambda x: None,
    )
    return ctx, transport, cache


def query(ctx_or_settings, sql, params=None):
    s = getattr(ctx_or_settings, "settings", ctx_or_settings)
    con = duckdb.connect()
    try:
        views.register_views(con, s)
        return con.execute(sql, params or []).fetchall()
    finally:
        con.close()


def parquet_files(settings, table):
    root = settings.data_dir / "clean" / table
    return sorted(p.name for p in root.rglob("*.parquet"))


def deep(obj):
    return copy.deepcopy(obj)


def day(y, m, d):
    return date(y, m, d)
