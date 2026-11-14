"""Cost arithmetic. All rates apply to trade notional."""

from __future__ import annotations

import re

from twdata.research.evaluator.constants import (
    COMMISSION,
    SELL_TAX_ETF,
    SELL_TAX_STOCK,
    SLIPPAGE,
    STOCK_CODE_PATTERN,
)

_STOCK = re.compile(STOCK_CODE_PATTERN)


def is_etf(stock_id: str) -> bool:
    return _STOCK.match(stock_id) is None


def buy_rate() -> float:
    return COMMISSION + SLIPPAGE


def sell_rate(stock_id: str) -> float:
    tax = SELL_TAX_ETF if is_etf(stock_id) else SELL_TAX_STOCK
    return COMMISSION + SLIPPAGE + tax


def buy_cost(notional: float) -> float:
    return notional * buy_rate()


def sell_cost(stock_id: str, notional: float) -> float:
    return notional * sell_rate(stock_id)
