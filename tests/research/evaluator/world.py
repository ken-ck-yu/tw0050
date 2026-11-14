"""Synthetic research data directory for the evaluator tests (offline, deterministic)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

from twdata.common.config import load_settings
from twdata.common.timeutil import UTC, at
from twdata.research.evaluator import load_dev_data
from twdata.research.evaluator.constants import TABLES

TS = pa.timestamp("us", tz="UTC")
FETCHED = datetime(2030, 1, 1, tzinfo=UTC)


def weekdays(start: date, n: int) -> list[date]:
    out, d = [], start
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def utc(d: date, h: int = 18, m: int = 0) -> datetime:
    return at(d, h, m).astimezone(UTC)


def flat(price: float, days: list[date]) -> dict:
    return {d: (price, price) for d in days}


class World:
    """prices: {stock_id: {date: (open, close)}}; a missing date means no prices_raw row.
    adj_close defaults to close; override with {stock_id: {date: adjusted_close}}."""

    def __init__(self, tmp_path: Path, days: list[date]):
        self.tmp = tmp_path
        self.days = days
        self.prices: dict = {}
        self.adj_close: dict = {}
        self.limits: dict = {}  # {stock_id: {date: (limit_up, limit_down)}}
        self.status: list = []  # (stock_id, type, start, end, available_at | "default")
        self.members: dict = {}  # {month_end: (available_at, [stock ids])}
        self.revenue: list = []
        self.calendar = days
        self.members_default = True

    def add(self, sid: str, series: dict, adj: dict | None = None):
        self.prices[sid] = series
        if adj:
            self.adj_close[sid] = adj

    def settings(self):
        return load_settings(data_dir_override=str(self.tmp / "data"))

    def write(self):
        base = self.tmp / "data" / "research"
        base.mkdir(parents=True, exist_ok=True)
        members = self.members
        if not members and self.members_default:
            members = {date(2022, 12, 31): (utc(date(2022, 12, 31)), sorted(self.prices))}
        tables = {
            "universe_membership": self._universe(members),
            "prices_raw": self._prices(),
            "adjusted_prices": self._adjusted(),
            "price_limits": self._limits(),
            "status_events": self._status(),
            "monthly_revenue": self._revenue(),
            "benchmark_index": pa.table(
                {
                    "index_id": pa.array(["TAIWAN50_TR"]),
                    "event_date": pa.array([self.days[0]], pa.date32()),
                    "value": pa.array([1.0]),
                    "available_at": pa.array([utc(self.days[0])], TS),
                    "fetched_at": pa.array([FETCHED], TS),
                }
            ),
            "trading_calendar": pa.table(
                {
                    "event_date": pa.array(self.calendar, pa.date32()),
                    "is_trading": pa.array([True] * len(self.calendar)),
                    "source": pa.array(["finmind"] * len(self.calendar)),
                    "fetched_at": pa.array([FETCHED] * len(self.calendar), TS),
                }
            ),
        }
        assert set(tables) == set(TABLES)
        for name, t in tables.items():
            pq.write_table(t, base / f"{name}.parquet")

    def load(self, start: date | None = None, end: date | None = None):
        self.write()
        return load_dev_data(self.settings(), start or self.days[0], end or self.days[-1])

    def _universe(self, members):
        rows = [(m, sid, av) for m, (av, sids) in members.items() for sid in sids]
        n = len(rows)
        return pa.table(
            {
                "month_end": pa.array([r[0] for r in rows], pa.date32()),
                "stock_id": pa.array([r[1] for r in rows], pa.string()),
                "isin": pa.array([None] * n, pa.string()),
                "market": pa.array(["TWSE"] * n),
                "rank": pa.array([1] * n, pa.int64()),
                "market_cap_ntd": pa.array([1.0e9] * n),
                "median_turnover_60d": pa.array([1.0e8] * n),
                "is_watchlist": pa.array([False] * n),
                "is_benchmark": pa.array([False] * n),
                "available_at": pa.array([r[2] for r in rows], TS),
            }
        )

    def _prices(self):
        rows = [(sid, d, o, c) for sid, s in self.prices.items() for d, (o, c) in s.items()]
        n = len(rows)
        return pa.table(
            {
                "market": pa.array(["TWSE"] * n, pa.string()),
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "event_date": pa.array([r[1] for r in rows], pa.date32()),
                "open": pa.array([r[2] for r in rows], pa.float64()),
                "high": pa.array([max(r[2] or 0, r[3] or 0) for r in rows], pa.float64()),
                "low": pa.array([min(r[2] or 0, r[3] or 0) for r in rows], pa.float64()),
                "close": pa.array([r[3] for r in rows], pa.float64()),
                "volume_shares": pa.array([1000] * n, pa.int64()),
                "turnover_ntd": pa.array([1000] * n, pa.int64()),
                "trades": pa.array([1] * n, pa.int64()),
                "available_at": pa.array([utc(r[1]) for r in rows], TS),
                "fetched_at": pa.array([FETCHED] * n, TS),
            }
        )

    def _adjusted(self):
        rows = []
        for sid, s in self.prices.items():
            for d, (o, c) in s.items():
                rows.append((sid, d, o, c, self.adj_close.get(sid, {}).get(d, c)))
        return pa.table(
            {
                "market": pa.array(["TWSE"] * len(rows), pa.string()),
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "event_date": pa.array([r[1] for r in rows], pa.date32()),
                "open": pa.array([r[2] for r in rows], pa.float64()),
                "close": pa.array([r[3] for r in rows], pa.float64()),
                "adjusted_close": pa.array([r[4] for r in rows], pa.float64()),
            }
        )

    def _limits(self):
        rows = [(sid, d, lu, ld) for sid, s in self.limits.items() for d, (lu, ld) in s.items()]
        n = len(rows)
        return pa.table(
            {
                "market": pa.array(["TWSE"] * n, pa.string()),
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "event_date": pa.array([r[1] for r in rows], pa.date32()),
                "limit_up": pa.array([r[2] for r in rows], pa.float64()),
                "limit_down": pa.array([r[3] for r in rows], pa.float64()),
                "available_at": pa.array([utc(r[1], 8, 30) for r in rows], TS),
                "fetched_at": pa.array([FETCHED] * n, TS),
            }
        )

    def _status(self):
        rows = self.status
        n = len(rows)
        return pa.table(
            {
                "market": pa.array(["TWSE"] * n, pa.string()),
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "status_type": pa.array([r[1] for r in rows], pa.string()),
                "announce_date": pa.array([None] * n, pa.date32()),
                "start_date": pa.array([r[2] for r in rows], pa.date32()),
                "end_date": pa.array([r[3] for r in rows], pa.date32()),
                "detail": pa.array([None] * n, pa.string()),
                "event_date": pa.array([r[2] for r in rows], pa.date32()),
                "available_at": pa.array([r[4] for r in rows], TS),
                "fetched_at": pa.array([FETCHED] * n, TS),
            }
        )

    def _revenue(self):
        rows = self.revenue  # (stock_id, event_date, revenue, available_at | None)
        n = len(rows)
        return pa.table(
            {
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "country": pa.array(["Taiwan"] * n, pa.string()),
                "revenue_year": pa.array([r[1].year for r in rows], pa.int64()),
                "revenue_month_num": pa.array([r[1].month for r in rows], pa.int64()),
                "revenue": pa.array([r[2] for r in rows], pa.int64()),
                "create_time": pa.array([None] * n, pa.string()),
                "event_date": pa.array([r[1] for r in rows], pa.date32()),
                "available_at": pa.array([r[3] for r in rows], TS),
                "fetched_at": pa.array([FETCHED] * n, TS),
            }
        )
