"""FinMind `TaiwanStockInfo` to the reference table `stock_info` (no `available_at`).

`event_date` is the source `date`, whose meaning is unverified (spike S6), so the table is a
reference and is never joined as a feature.
"""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, date, datetime
from pathlib import Path

from twdata.clients.base import DriftError
from twdata.common.cleanstore import KeyUniquenessError

DATASET = "stock_info"
SOURCE = "TaiwanStockInfo"
COLUMNS = ("industry_category", "stock_id", "stock_name", "type", "date")
FULL_START = date(2000, 1, 1)


def duplicates_path(settings) -> Path:
    return settings.data_dir / "state" / "stock_info_duplicates.json"


def record_duplicates(settings, table: str, keys: list[tuple]) -> None:
    """Write the offending primary keys for spike S6 (under data/state, not docs/) and stop."""
    p = duplicates_path(settings)
    p.parent.mkdir(parents=True, exist_ok=True)
    doc = json.loads(p.read_text("utf-8")) if p.exists() else {}
    doc[table] = {
        "recorded_at": datetime.now(UTC).isoformat(),
        "keys": [[str(x) for x in k] for k in keys],
    }
    p.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def parse_date(text, where: str) -> date | None:
    """ISO date, or None for a null or unparseable value (the row is skipped and counted)."""
    try:
        return date.fromisoformat(str(text))
    except ValueError:
        return None


def check_columns(records: list[dict], expected: tuple[str, ...], where: str) -> None:
    for rec in records:
        if set(rec) != set(expected):
            raise DriftError(f"{where}: columns {sorted(rec)} differ from {sorted(expected)}")


def duplicate_keys(rows: list[dict], key: tuple[str, ...]) -> list[tuple]:
    c = Counter(tuple(r[k] for k in key) for r in rows)
    return sorted(k for k, n in c.items() if n > 1)


SKIPPED: dict[str, int] = {}  # rows skipped for a null or unparseable date, per table


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
                "industry_category": str(r["industry_category"] or "").strip(),
                "type": str(r["type"] or "").strip(),
            }
        )
    return out


def run(ctx, start: date, end: date) -> None:
    """The whole table is fetched whatever the range (it is small and carries no history key)."""
    records = ctx.finmind.dataset(SOURCE, FULL_START, None)
    fetched_at = datetime.now(UTC)
    rows = to_rows(records)
    try:
        ctx.writers(DATASET).append(rows, fetched_at)
    except KeyUniquenessError:
        record_duplicates(ctx.settings, DATASET, duplicate_keys(rows, ("stock_id", "event_date")))
        raise
    ctx.cache.flush()


DATASETS = {"stock_info": run}
