"""FinMind `TaiwanStockDelisting` to the reference table `delistings`.

`event_date` is the source `date`. The row count has differed between probes (690 against 726,
spike S6), so a duplicate key stops the run and is logged in docs/spikes/S6.md.
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from twdata.common.cleanstore import KeyUniquenessError
from twdata.ingest.stock_info import (
    FULL_START,
    check_columns,
    duplicate_keys,
    parse_date,
    record_duplicates,
)

DATASET = "delistings"
SOURCE = "TaiwanStockDelisting"
COLUMNS = ("date", "stock_id", "stock_name")


SKIPPED: dict[str, int] = {}


def to_rows(records: list[dict]) -> list[dict]:
    check_columns(records, COLUMNS, SOURCE)
    out = []
    for r in records:
        d = parse_date(r["date"], SOURCE)
        if d is None:
            SKIPPED[DATASET] = SKIPPED.get(DATASET, 0) + 1
            continue
        out.append(
            {
                "event_date": d,
                "stock_id": str(r["stock_id"]).strip(),
                "stock_name": str(r["stock_name"] or "").strip(),
            }
        )
    return out


def run(ctx, start: date, end: date) -> None:
    """The whole table is fetched whatever the range (it is small, history from 2000)."""
    records = ctx.finmind.dataset(SOURCE, FULL_START)
    fetched_at = datetime.now(UTC)
    rows = to_rows(records)
    try:
        ctx.writers(DATASET).append(rows, fetched_at)
    except KeyUniquenessError:
        record_duplicates(ctx.settings, DATASET, duplicate_keys(rows, ("stock_id", "event_date")))
        raise
    ctx.cache.flush()


DATASETS = {"delistings": run}
