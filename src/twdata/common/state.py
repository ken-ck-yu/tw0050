"""Per-dataset state files: completed ranges or stock ids, atomic writes, under a file lock."""

from __future__ import annotations

import json
import os
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from filelock import FileLock

from twdata.common import paths
from twdata.common.config import Settings


def _lock(path: Path) -> FileLock:
    paths.ensure(path.parent)
    return FileLock(str(path) + ".lock")


def _write(path: Path, doc: dict) -> None:
    tmp = path.with_suffix(path.suffix + f".tmp{os.getpid()}")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    os.replace(tmp, path)


def load(s: Settings, dataset: str) -> dict | None:
    p = paths.state_file(s, dataset)
    if not p.exists():
        return None
    return json.loads(p.read_text(encoding="utf-8"))


def _merge(ranges: list[tuple[date, date]]) -> list[tuple[date, date]]:
    out: list[tuple[date, date]] = []
    for lo, hi in sorted(ranges):
        if out and lo <= out[-1][1] + timedelta(days=1):
            out[-1] = (out[-1][0], max(out[-1][1], hi))
        else:
            out.append((lo, hi))
    return out


def mark_dates(
    s: Settings, dataset: str, start: date, end: date, *, era: str | None = None, shards=()
) -> None:
    p = paths.state_file(s, dataset)
    with _lock(p):
        doc = load(s, dataset) or {
            "dataset": dataset,
            "key_type": "date",
            "completed": [],
            "era": None,
            "shards": [],
        }
        cur = [(date.fromisoformat(a), date.fromisoformat(b)) for a, b in doc["completed"]]
        cur.append((start, end))
        doc["completed"] = [[a.isoformat(), b.isoformat()] for a, b in _merge(cur)]
        doc["era"] = era if era is not None else doc.get("era")
        doc["shards"] = sorted(set(doc["shards"]) | set(shards))
        doc["updated_at"] = datetime.now(UTC).isoformat()
        paths.ensure(p.parent)
        _write(p, doc)


def mark_stocks(s: Settings, dataset: str, stock_ids, *, shards=()) -> None:
    p = paths.state_file(s, dataset)
    with _lock(p):
        doc = load(s, dataset) or {
            "dataset": dataset,
            "key_type": "stock",
            "completed": [],
            "era": None,
            "shards": [],
        }
        doc["completed"] = sorted(set(doc["completed"]) | set(stock_ids))
        doc["shards"] = sorted(set(doc["shards"]) | set(shards))
        doc["updated_at"] = datetime.now(UTC).isoformat()
        paths.ensure(p.parent)
        _write(p, doc)


def is_done(s: Settings, dataset: str, d: date) -> bool:
    doc = load(s, dataset)
    if not doc or doc["key_type"] != "date":
        return False
    return any(date.fromisoformat(a) <= d <= date.fromisoformat(b) for a, b in doc["completed"])


def missing(s: Settings, dataset: str, start: date, end: date, calendar) -> list[date]:
    return [d for d in calendar.days_between(start, end) if not is_done(s, dataset, d)]


def entries(s: Settings) -> list[dict]:
    d = s.data_dir / "state"
    out = []
    if d.exists():
        for p in sorted(d.glob("*.json")):
            out.append(json.loads(p.read_text(encoding="utf-8")))
    return out
