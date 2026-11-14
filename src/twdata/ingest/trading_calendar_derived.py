"""Second trading calendar derived from the official daily files (agent A-1).

A date is derived-trading when `prices_raw` has at least one row on it. `diff` compares that set
with the FinMind calendar (`ctx.calendar`) and writes `data/state/calendar_diff.json`.
"""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime

import duckdb

from twdata.common import paths, views

DATASETS: dict = {}

NAME = "calendar_diff"


def derived_days(settings, start: date, end: date) -> set[date]:
    con = duckdb.connect()
    try:
        tables = views.register_views(con, settings)
        if "prices_raw" not in tables:
            return set()
        rows = con.execute(
            "SELECT DISTINCT event_date FROM default_prices_raw WHERE event_date BETWEEN ? AND ?",
            [start, end],
        ).fetchall()
    finally:
        con.close()
    return {r[0] for r in rows}


def diff(ctx, start: date, end: date) -> dict:
    """Return {"finmind_only": [...], "derived_only": [...]} (ISO date strings, sorted).

    finmind_only: calendar trading days in the range with no prices_raw row.
    derived_only: dates with prices_raw rows that the calendar does not list as trading days.
    """
    cal_days = set(ctx.calendar.days_between(start, end))
    der = derived_days(ctx.settings, start, end)
    result = {
        "finmind_only": [d.isoformat() for d in sorted(cal_days - der)],
        "derived_only": [d.isoformat() for d in sorted(der - cal_days)],
    }
    # The file doubles as a state document so that `status` can list every file in data/state.
    doc = {
        "dataset": NAME,
        "key_type": "diff",
        "completed": [],
        "era": None,
        "shards": [],
        "updated_at": datetime.now(UTC).isoformat(),
        "start": start.isoformat(),
        "end": end.isoformat(),
        **result,
    }
    path = paths.state_file(ctx.settings, NAME)
    paths.ensure(path.parent)
    tmp = path.with_suffix(f".json.tmp{os.getpid()}")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)
    return result
