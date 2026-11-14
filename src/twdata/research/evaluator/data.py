"""Development data loader. Reads only Parquet under <data_dir>/research/, never data/clean/."""

from __future__ import annotations

import bisect
from datetime import date, datetime
from pathlib import Path

import pyarrow.parquet as pq

from twdata.common.timeutil import UTC, at
from twdata.common.tradingcal import TradingCalendar
from twdata.research.evaluator.constants import (
    DECISION_HOUR,
    TABLES,
    DataError,
    HoldoutError,
)


def cutoff_for(decision_date: date) -> datetime:
    """The information cutoff: 18:00 Asia/Taipei on the decision date."""
    return at(decision_date, DECISION_HOUR, 0)


def _aware(v, table: str):
    if v is None:
        return None
    if isinstance(v, datetime):
        if v.tzinfo is None:
            raise DataError(f"{table}: naive timestamp in available_at")
        return v
    raise DataError(f"{table}: available_at is not a timestamp: {v!r}")


class AsOf:
    """Rows visible at a decision date. Adjusted prices are deliberately absent (they embed
    future corporate actions); use prices_raw for any feature."""

    def __init__(self, data: DevData, decision_date: date):
        self.decision_date = decision_date
        self.cutoff = cutoff_for(decision_date)
        self._data = data

    def table(self, name: str) -> list[dict]:
        if name == "adjusted_prices":
            raise DataError("adjusted_prices is not point-in-time; it is not served by as_of")
        if name not in self._data._sorted:
            raise DataError(f"unknown table {name!r}")
        keys, rows = self._data._sorted[name]
        if name == "trading_calendar":
            i = bisect.bisect_right(keys, self.decision_date)
        else:
            i = bisect.bisect_right(keys, self.cutoff)
        return rows[:i]


class DevData:
    def __init__(self, settings, start: date, end: date, tables: dict[str, list[dict]]):
        self.settings = settings
        self.start = start
        self.end = end
        self.tables = tables
        self._sorted: dict[str, tuple[list, list[dict]]] = {}
        for name, rows in tables.items():
            if name == "trading_calendar":
                srt = sorted(rows, key=lambda r: r["event_date"])
                self._sorted[name] = ([r["event_date"] for r in srt], srt)
            else:
                # rows with a null available_at are never visible point-in-time
                srt = sorted(
                    (r for r in rows if r.get("available_at") is not None),
                    key=lambda r: r["available_at"],
                )
                self._sorted[name] = ([r["available_at"] for r in srt], srt)
        self.calendar = TradingCalendar(
            r["event_date"] for r in tables["trading_calendar"] if r["is_trading"]
        )
        self.prices = {(r["stock_id"], r["event_date"]): r for r in tables["prices_raw"]}
        self.adjusted = {(r["stock_id"], r["event_date"]): r for r in tables["adjusted_prices"]}
        self.limits = {(r["stock_id"], r["event_date"]): r for r in tables["price_limits"]}

    def as_of(self, decision_date: date) -> AsOf:
        return AsOf(self, decision_date)

    def next_trading_day(self, d: date) -> date | None:
        return self.calendar.next_after(d)

    def raw_open(self, stock_id: str, d: date) -> float | None:
        row = self.prices.get((stock_id, d))
        return None if row is None else row.get("open")

    def adj_open(self, stock_id: str, d: date) -> float | None:
        """open * adjusted_close / close, on the fully adjusted scale."""
        row = self.adjusted.get((stock_id, d))
        if row is None:
            return None
        o, c, a = row.get("open"), row.get("close"), row.get("adjusted_close")
        if o is None or c is None or a is None or c == 0:
            return None
        return o * a / c

    def adj_close(self, stock_id: str, d: date) -> float | None:
        row = self.adjusted.get((stock_id, d))
        return None if row is None else row.get("adjusted_close")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        raise DataError(f"missing research table file: {path.name}")
    return pq.read_table(path).to_pylist()


def load_dev_data(settings, start: date, end: date) -> DevData:
    if end > settings.research.dev_end:
        raise HoldoutError(
            f"range ends {end}, after dev_end {settings.research.dev_end}: the holdout is sealed"
        )
    if start > end:
        raise DataError("start after end")
    base = Path(settings.data_dir) / "research"
    last_cut = cutoff_for(end).astimezone(UTC)
    tables: dict[str, list[dict]] = {}
    for name in TABLES:
        keep: list[dict] = []
        for r in _read(base / f"{name}.parquet"):
            if "available_at" in r:
                r["available_at"] = _aware(r["available_at"], name)
            if name == "universe_membership":
                ok = r["month_end"] <= end
            elif name in ("monthly_revenue", "status_events", "trading_calendar"):
                # history before `start` is needed (year-on-year, running status windows)
                ok = r["event_date"] <= end
            else:
                ok = start <= r["event_date"] <= end
            av = r.get("available_at")
            if ok and av is not None and name != "adjusted_prices":
                ok = av.astimezone(UTC) <= last_cut
            if ok:
                keep.append(r)
        tables[name] = keep
    return DevData(settings, start, end, tables)
