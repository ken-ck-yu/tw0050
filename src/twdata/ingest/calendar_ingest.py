"""FinMind trading calendar to the clean table `trading_calendar` (Lead)."""

from __future__ import annotations

from datetime import UTC, date, datetime

from twdata.common import state
from twdata.common.timeutil import TAIPEI

DATASET = "trading_calendar"


def run(ctx, start: date, end: date) -> None:
    rows_src = ctx.finmind.dataset("TaiwanStockTradingDate", start, end)
    fetched_at = datetime.now(UTC)
    rows = [
        {
            "event_date": date.fromisoformat(r["date"]),
            "is_trading": True,
            "source": "finmind",
        }
        for r in rows_src
    ]
    ctx.writers("trading_calendar").append(rows, fetched_at)
    if rows:
        state.mark_dates(
            ctx.settings,
            DATASET,
            min(r["event_date"] for r in rows),
            max(r["event_date"] for r in rows),
        )
    _ = TAIPEI  # the calendar holds dates only, no timestamps to convert


DATASETS = {DATASET: run}
