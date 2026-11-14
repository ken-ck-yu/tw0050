"""Append monthly_revenue rows for months after a stock's first full pull.

`twdata fetch --dataset monthly_revenue` skips stocks already marked done, so a later end date
collects nothing for them. This re-fetches a window for every stock in collection_set; identical
rows are skipped by the writer. Usage: revenue_catchup.py START END (YYYY-MM-DD)."""

import sys
from datetime import date

from twdata import cli
from twdata.common import config
from twdata.ingest import monthly_revenue as mr


def main(start: date, end: date) -> None:
    config.load_env()
    settings = config.load_settings()
    ctx = cli._context(settings, True)
    mr._need_calendar(ctx)
    writer = ctx.writers(mr.DATASET)
    for stock_id in mr.stock_list(ctx):
        mr._fetch_write(ctx, writer, stock_id, start, end)
        ctx.cache.flush()


if __name__ == "__main__":
    main(date.fromisoformat(sys.argv[1]), date.fromisoformat(sys.argv[2]))
