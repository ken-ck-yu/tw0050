"""Value sanity checks. Limit checks are acceptance check 5, not ingest checks."""

from __future__ import annotations

from datetime import date


class SanityError(Exception):
    pass


def check_price_row(row: dict) -> None:
    o, h, lo, c = (row.get(k) for k in ("open", "high", "low", "close"))
    prices = [p for p in (o, h, lo, c) if p is not None]
    if any(p < 0 for p in prices):
        raise SanityError(f"negative price in {row}")
    if h is not None and lo is not None and h < lo:
        raise SanityError(f"high below low in {row}")
    if c is not None and h is not None and lo is not None and not (lo <= c <= h):
        raise SanityError(f"close outside [low, high] in {row}")


def tick_size(price: float, d: date | None = None, etf: bool = False) -> float:
    """TWSE tick table. Stocks: 0.01 below 10, 0.05 below 50, 0.1 below 100, 0.5 below 500,
    1 below 1000, 5 from 1000. ETFs: 0.01 below 50, 0.05 from 50."""
    if etf:
        return 0.01 if price < 50 else 0.05
    if price < 10:
        return 0.01
    if price < 50:
        return 0.05
    if price < 100:
        return 0.1
    if price < 500:
        return 0.5
    if price < 1000:
        return 1.0
    return 5.0
