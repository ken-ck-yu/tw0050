"""Daily TWSE plus TPEx pair with the calendar discrepancy ledger (spec section 8)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from datetime import date as Date
from pathlib import Path

from twdata.clients.base import DriftError, Response


def _ledger_has(path: Path, d: Date, twse_key: str, tpex_key: str) -> bool:
    if not path.exists():
        return False
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            e = json.loads(line)
        except ValueError:
            continue
        if (
            e.get("date") == d.isoformat()
            and e.get("twse_endpoint") == twse_key
            and e.get("tpex_endpoint") == tpex_key
        ):
            return True
    return False


def _calendar_trading(calendar, d: Date) -> bool | None:
    if calendar is None or not calendar.covers(d):
        return None
    return bool(calendar.is_trading(d))


def fetch_daily_pair(
    twse_client,
    tpex_client,
    d: Date,
    twse_key: str,
    tpex_key: str,
    ledger_path: Path,
) -> tuple[Response, Response]:
    """Fetch the TWSE and TPEx per-date endpoints for `d`, TWSE first.

    Both empty on a trading day: ledger line, two empty ok responses. Exactly one empty:
    DriftError. Both empty where the calendar gives no verdict: DriftError (as the classifier).
    """
    tw = twse_client.per_date(twse_key, d, allow_empty=True)
    tp = tpex_client.per_date(tpex_key, d, allow_empty=True)
    tw_empty, tp_empty = not tw.rows, not tp.rows
    if tw_empty != tp_empty:
        empty = twse_key if tw_empty else tpex_key
        raise DriftError(f"only one market is empty on {d}: {empty}")
    if not tw_empty:
        return tw, tp
    verdict = _calendar_trading(twse_client.calendar, d)
    if verdict is False:
        return tw, tp
    if verdict is None:
        raise DriftError(f"both markets empty on {d} and the calendar gives no verdict")
    ledger_path = Path(ledger_path)
    if not _ledger_has(ledger_path, d, twse_key, tpex_key):
        ledger_path.parent.mkdir(parents=True, exist_ok=True)
        entry = {
            "date": d.isoformat(),
            "twse_endpoint": twse_key,
            "tpex_endpoint": tpex_key,
            "recorded_at": datetime.now(UTC).isoformat(),
        }
        with ledger_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return tw, tp
