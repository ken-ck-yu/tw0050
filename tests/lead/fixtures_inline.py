"""Tiny synthetic bodies and fakes for the client tests (offline)."""

import contextlib
import dataclasses
import json
from datetime import date

from twdata.clients.transport import HttpResult
from twdata.common import config
from twdata.common.tradingcal import TradingCalendar

TOKEN = "FAKE-TOKEN-0123456789"
FIELDS = ["證券代號", "證券名稱", "收盤價"]
ROW = ["2330", "台積電", "1,000.00"]
TRADING = date(2025, 6, 3)
HOLIDAY = date(2025, 6, 4)  # inside the calendar, not a trading day
OUTSIDE = date(2026, 1, 5)  # past the calendar end
CAL = TradingCalendar([date(2025, 6, 2), TRADING, date(2025, 6, 5)])


def jb(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False).encode("utf-8")


def twse_top(rows=None, stat="OK", fields=FIELDS):
    return jb({"stat": stat, "fields": fields, "data": [ROW] if rows is None else rows})


def mi_index(rows=None, stat="OK", titles=("指數", "每日收盤行情(全部)")):
    tables = []
    for t in titles:
        if "每日收盤行情" in t:
            tables.append({"title": t, "fields": FIELDS, "data": [ROW] if rows is None else rows})
        else:
            tables.append({"title": t, "fields": ["a"], "data": [["x"]]})
    return jb({"stat": stat, "tables": tables})


def tpex(rows=None, stat="ok", fields=FIELDS):
    table = {"fields": fields, "data": [ROW] if rows is None else rows}
    return jb({"stat": stat, "tables": [table]})


NO_DATA = jb({"stat": "很抱歉，沒有符合條件的資料!", "total": 0})


def ok(body, headers=None):
    return HttpResult(200, headers or {}, body)


def settings(tmp_path, **kw):
    s = config.load_settings(data_dir_override=str(tmp_path))
    return dataclasses.replace(s, retry_waits_s=(5, 10, 20, 40, 80), **kw)


class FakeTransport:
    """Replays scripted HttpResults (the last one repeats), records every call."""

    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def __call__(self, method, url, params, headers, timeout):
        self.calls.append((method, url, dict(params), dict(headers), timeout))
        r = self.results.pop(0) if len(self.results) > 1 else self.results[0]
        if callable(r):
            r = r(url, params)
        return r


class FakeLimiter:
    def __init__(self):
        self.slots = 0
        self.depth = 0
        self.updates = []

    @contextlib.contextmanager
    def slot(self):
        self.slots += 1
        self.depth += 1
        try:
            yield
        finally:
            self.depth -= 1

    def update(self, limit_per_hour, user_count):
        self.updates.append((limit_per_hour, user_count))


@dataclasses.dataclass
class Cached:
    status: int
    body: bytes
    fetched_at: object = None
    shard: str = "fake"


class FakeCache:
    def __init__(self):
        self.store = {}
        self.puts = []
        self.quarantined = []

    def put(self, source, dataset, request_key, url, params, status, body, fetched_at):
        self.store[(source, dataset, request_key)] = Cached(status, body)
        self.puts.append((source, dataset, request_key, url, params, status, body))

    def get(self, source, dataset, request_key):
        return self.store.get((source, dataset, request_key))

    def put_quarantine(self, source, dataset, request_key, url, params, status, body, fetched_at):
        self.quarantined.append((source, dataset, request_key, url, params, status, body))

    def flush(self):
        pass


def make(tmp_path, cls, transport, *, calendar=CAL, waits=None, settings_kw=None):
    """Build (client, limiter, cache, sleeps) around a transport. `cls` is a source client
    class (TwseClient, TpexClient, FinMindClient) or a host name for the generic Client."""
    from twdata.clients.base import Client

    s = settings(tmp_path, **(settings_kw or {}))
    if waits is not None:
        s = dataclasses.replace(s, retry_waits_s=waits)
    lim, cache, sleeps = FakeLimiter(), FakeCache(), []
    if isinstance(cls, str):
        c = Client(s, cls, lim, cache, transport, calendar=calendar, sleep=sleeps.append)
    else:
        c = cls(s, lim, cache, transport, calendar=calendar, sleep=sleeps.append)
    return c, lim, cache, sleeps
