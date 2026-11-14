"""Offline fakes for Agent B tests: a URL-routed transport, a cache and a RunContext builder."""

from __future__ import annotations

import contextlib
import dataclasses
import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import duckdb

from twdata.clients.context import RunContext
from twdata.clients.tpex import TpexClient
from twdata.clients.transport import HttpResult
from twdata.clients.twse import TwseClient
from twdata.common import config, views
from twdata.common.cleanstore import CleanWriter
from twdata.common.tradingcal import TradingCalendar

LEAD = Path(__file__).resolve().parents[1] / "fixtures" / "lead"
FIXED_NOW = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)


def fixture_bytes(rel: str) -> bytes:
    return (LEAD / rel).read_bytes()


def weekday_calendar(first=date(2015, 1, 1), last=date(2026, 12, 31)) -> TradingCalendar:
    days, d = [], first
    while d <= last:
        if d.weekday() < 5:
            days.append(d)
        d += timedelta(days=1)
    return TradingCalendar(days)


class Router:
    """Transport that answers by a substring of the URL; records every call."""

    def __init__(self):
        self.routes: list[tuple[str, object]] = []
        self.calls: list[tuple[str, dict]] = []

    def add(self, needle: str, body) -> Router:
        """`body` is bytes or a callable params -> bytes."""
        self.routes.append((needle, body))
        return self

    def __call__(self, method, url, params, headers, timeout):
        self.calls.append((url, dict(params)))
        for needle, body in self.routes:
            if needle in url:
                b = body(params) if callable(body) else body
                return HttpResult(200, {}, b)
        return HttpResult(404, {}, b"")

    def count(self, needle: str) -> int:
        return sum(1 for u, _ in self.calls if needle in u)


class FakeLimiter:
    @contextlib.contextmanager
    def slot(self):
        yield


@dataclasses.dataclass
class Cached:
    status: int
    body: bytes
    fetched_at: datetime
    shard: str = "fake"


class FakeCache:
    def __init__(self):
        self.store = {}

    def put(self, source, dataset, request_key, url, params, status, body, fetched_at):
        self.store[(source, dataset, request_key)] = Cached(status, body, fetched_at)

    def get(self, source, dataset, request_key):
        return self.store.get((source, dataset, request_key))

    def put_quarantine(self, *a, **k):
        pass

    def flush(self):
        pass


def make_ctx(tmp_path, router, calendar=None, finmind=None) -> RunContext:
    s = config.load_settings(data_dir_override=str(tmp_path))
    cal = calendar if calendar is not None else weekday_calendar()
    cache = FakeCache()
    now = lambda: FIXED_NOW  # noqa: E731
    tw = TwseClient(s, FakeLimiter(), cache, router, calendar=cal, now=now)
    tp = TpexClient(s, FakeLimiter(), cache, router, calendar=cal, now=now)
    return RunContext(s, cal, tw, tp, finmind, cache, lambda t: CleanWriter(s, t))


def query(tmp_path, sql: str, params=None):
    """Run SQL over the views of the data_dir under tmp_path; return a list of dict rows."""
    s = config.load_settings(data_dir_override=str(tmp_path))
    con = duckdb.connect()
    try:
        views.register_views(con, s)
        cur = con.execute(sql, params or [])
        names = [c[0] for c in cur.description]
        return [dict(zip(names, r, strict=True)) for r in cur.fetchall()]
    finally:
        con.close()


def connect(tmp_path):
    s = config.load_settings(data_dir_override=str(tmp_path))
    con = duckdb.connect()
    views.register_views(con, s)
    return con


def jb(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")
