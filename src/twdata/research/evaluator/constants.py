"""Frozen constants and exception types of the evaluator."""

from __future__ import annotations

from datetime import date

COMMISSION = 0.001425  # per side, full list price
SELL_TAX_STOCK = 0.003
SELL_TAX_ETF = 0.001
SLIPPAGE = 0.001  # per side
ANNUALIZATION = 244
MAX_WEIGHT = 0.10
MAX_GROSS = 1.0
WEIGHT_TOL = 1e-9  # float tolerance on the weight checks only
STOCK_CODE_PATTERN = r"^[1-9][0-9]{3}$"  # anything else is treated as an ETF
BENCHMARK_ID = "0050"
MAX_SELL_DEFER_DAYS = 5  # a limit-down-locked sell is forced at the 5th open
DECISION_HOUR = 18  # Asia/Taipei, the information cutoff on the decision date
EPS = 1e-12  # NAV units, below this a position or trade is zero
DEV_START = date(2015, 6, 1)
WINDOWS = ("train", "validation", "dev")
DROPPED_DETAIL_CAP = 200  # dropped targets listed in the log line (the count is exact)

TABLES = (
    "universe_membership",
    "prices_raw",
    "adjusted_prices",
    "price_limits",
    "status_events",
    "monthly_revenue",
    "benchmark_index",
    "trading_calendar",
)


class HoldoutError(Exception):
    """A requested range ends after settings.research.dev_end."""


class BookError(Exception):
    """A target book or the backtest request is invalid (never clipped silently)."""


class BudgetError(Exception):
    """The cycle already holds max_runs_per_cycle runs."""


class DataError(Exception):
    """The research data directory is missing a table or a needed value."""
