"""Synthetic research data directory for the H1 strategy tests (offline, deterministic).

Same approach as the evaluator's tests (own copy, not imported from there)."""

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


def month_add(d: date, n: int) -> date:
    idx = d.year * 12 + d.month - 1 + n
    return date(idx // 12, idx % 12 + 1, 1)


def revenue_available(rev_month: date) -> datetime:
    """10th of the following month at 18:00, or the next weekday."""
    d = month_add(rev_month, 1).replace(day=10)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return utc(d)


class World:
    """prices: {stock_id: {date: (open, close)}}.
    members: {month_end: (available_at, [(stock_id, is_benchmark, is_watchlist)])}.
    revenue: [(stock_id, event_date, revenue, available_at | None)]."""

    def __init__(self, tmp_path: Path, days: list[date]):
        self.tmp = tmp_path
        self.days = days
        self.prices: dict = {}
        self.members: dict = {}
        self.revenue: list = []
        self.calendar = days

    def settings(self):
        return load_settings(data_dir_override=str(self.tmp / "data"))

    def set_universe(self, month_end: date, sids, bench=(), watch=(), available_at=None):
        rows = [(s, False, s in watch) for s in sids] + [(s, True, False) for s in bench]
        self.members[month_end] = (available_at or utc(month_end), rows)

    def add_revenue(self, sid: str, month: date, value: int, available_at="default"):
        av = revenue_available(month) if available_at == "default" else available_at
        self.revenue.append((sid, month, value, av))

    def write(self, skip: tuple[str, ...] = ()):
        base = self.tmp / "data" / "research"
        base.mkdir(parents=True, exist_ok=True)
        tables = {
            "universe_membership": self._universe(),
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
            if name not in skip:
                pq.write_table(t, base / f"{name}.parquet")

    def load(self, start: date, end: date):
        self.write()
        return load_dev_data(self.settings(), start, end)

    def _universe(self):
        rows = [(m, sid, b, wl, av) for m, (av, lst) in self.members.items() for sid, b, wl in lst]
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
                "is_watchlist": pa.array([r[3] for r in rows], pa.bool_()),
                "is_benchmark": pa.array([r[2] for r in rows], pa.bool_()),
                "available_at": pa.array([r[4] for r in rows], TS),
            }
        )

    def _rows(self):
        return [(sid, d, o, c) for sid, s in self.prices.items() for d, (o, c) in s.items()]

    def _prices(self):
        rows = self._rows()
        n = len(rows)
        return pa.table(
            {
                "market": pa.array(["TWSE"] * n, pa.string()),
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "event_date": pa.array([r[1] for r in rows], pa.date32()),
                "open": pa.array([r[2] for r in rows], pa.float64()),
                "high": pa.array([max(r[2], r[3]) for r in rows], pa.float64()),
                "low": pa.array([min(r[2], r[3]) for r in rows], pa.float64()),
                "close": pa.array([r[3] for r in rows], pa.float64()),
                "volume_shares": pa.array([1000] * n, pa.int64()),
                "turnover_ntd": pa.array([1000] * n, pa.int64()),
                "trades": pa.array([1] * n, pa.int64()),
                "available_at": pa.array([utc(r[1]) for r in rows], TS),
                "fetched_at": pa.array([FETCHED] * n, TS),
            }
        )

    def _adjusted(self):
        rows = self._rows()
        return pa.table(
            {
                "market": pa.array(["TWSE"] * len(rows), pa.string()),
                "stock_id": pa.array([r[0] for r in rows], pa.string()),
                "event_date": pa.array([r[1] for r in rows], pa.date32()),
                "open": pa.array([r[2] for r in rows], pa.float64()),
                "close": pa.array([r[3] for r in rows], pa.float64()),
                "adjusted_close": pa.array([r[3] for r in rows], pa.float64()),
            }
        )

    def _limits(self):
        return pa.table(
            {
                "market": pa.array([], pa.string()),
                "stock_id": pa.array([], pa.string()),
                "event_date": pa.array([], pa.date32()),
                "limit_up": pa.array([], pa.float64()),
                "limit_down": pa.array([], pa.float64()),
                "available_at": pa.array([], TS),
                "fetched_at": pa.array([], TS),
            }
        )

    def _status(self):
        return pa.table(
            {
                "market": pa.array([], pa.string()),
                "stock_id": pa.array([], pa.string()),
                "status_type": pa.array([], pa.string()),
                "announce_date": pa.array([], pa.date32()),
                "start_date": pa.array([], pa.date32()),
                "end_date": pa.array([], pa.date32()),
                "detail": pa.array([], pa.string()),
                "event_date": pa.array([], pa.date32()),
                "available_at": pa.array([], TS),
                "fetched_at": pa.array([], TS),
            }
        )

    def _revenue(self):
        rows = self.revenue
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
