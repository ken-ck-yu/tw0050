"""Latest-only OpenAPI snapshots to `snapshot_<name>` tables (agent A-1, docs/specs/m1_agent_a.md).

Each row of a payload becomes one row (`row_json`). `snapshot_date` is the Taipei date of the
fetch, `first_seen_at` the fetch time, `available_at` equals `first_seen_at`. The stopgap capture
script's files (`data/raw/snapshots`) are imported with their file stamp as the fetch time.
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import UTC, datetime

from twdata.clients.base import DriftError
from twdata.common import paths, schema, state
from twdata.common.timeutil import TAIPEI

log = logging.getLogger(__name__)

# name -> (host, OpenAPI path), section 15.2 of the M0 specs.
SNAPSHOTS: dict[str, tuple[str, str]] = {
    "twse_TWT85U": ("twse", "/exchangeReport/TWT85U"),
    "twse_TWT96U": ("twse", "/SBL/TWT96U"),
    "twse_BFI84U": ("twse", "/exchangeReport/BFI84U"),
    "twse_TWTB4U": ("twse", "/exchangeReport/TWTB4U"),
    "twse_t187ap04_L": ("twse", "/opendata/t187ap04_L"),
    "twse_t187ap09_L": ("twse", "/opendata/t187ap09_L"),
    "twse_t187ap12_L": ("twse", "/opendata/t187ap12_L"),
    "twse_t187ap24_L": ("twse", "/opendata/t187ap24_L"),
    "twse_t187ap25_L": ("twse", "/opendata/t187ap25_L"),
    "twse_t187ap26_L": ("twse", "/opendata/t187ap26_L"),
    "twse_t187ap27_L": ("twse", "/opendata/t187ap27_L"),
    "tpex_spendi_today": ("tpex", "/tpex_spendi_today"),
    "tpex_spendi_history": ("tpex", "/tpex_spendi_history"),
    "tpex_trading_warning_information": ("tpex", "/tpex_trading_warning_information"),
    "tpex_trading_warning_note": ("tpex", "/tpex_trading_warning_note"),
}

for _name in SNAPSHOTS:
    schema.snapshot_table(_name)

STOPGAP_STATE = "snapshots_stopgap"  # state dataset listing the stopgap files already imported


def snapshot_rows(name: str, body: bytes, fetched_at: datetime) -> list[dict]:
    """Rows of one payload. A payload that is not a JSON list of objects is `DriftError`."""
    try:
        payload = json.loads(body.decode("utf-8"))
    except ValueError as e:
        raise DriftError(f"snapshot {name}: body is not JSON ({e})") from None
    if not isinstance(payload, list) or not all(isinstance(r, dict) for r in payload):
        raise DriftError(f"snapshot {name}: payload is not a JSON list of objects")
    sha = hashlib.sha256(body).hexdigest()
    seen_at = fetched_at.astimezone(TAIPEI)
    day = seen_at.date()
    return [
        {
            "event_date": day,
            "available_at": fetched_at,
            "fetched_at": fetched_at,
            "snapshot_date": day,
            "first_seen_at": fetched_at,
            "payload_sha256": sha,
            "row_seq": i,
            "row_json": json.dumps(r, ensure_ascii=False, sort_keys=True),
        }
        for i, r in enumerate(payload)
    ]


def _write(ctx, name: str, rows: list[dict], days: set) -> None:
    """Append rows (first fetch wins for a repeated key) and record the days in state."""
    rows = sorted(rows, key=lambda r: (r["fetched_at"], r["row_seq"]))
    seen, unique = set(), []
    for r in rows:
        k = (r["payload_sha256"], r["snapshot_date"], r["row_seq"])
        if k not in seen:
            seen.add(k)
            unique.append(r)
    if unique:
        ctx.writers(f"snapshot_{name}").append(unique)
    for d in sorted(days):
        state.mark_dates(ctx.settings, f"snapshot_{name}", d, d)


def import_stopgap(ctx) -> dict[str, int]:
    """Import the stopgap capture files listed in the manifest. Idempotent. Returns files per
    name that were imported in this call."""
    root = paths.snapshot_dir(ctx.settings)
    manifest = root / "manifest.jsonl"
    if not manifest.exists():
        return {}
    done = set((state.load(ctx.settings, STOPGAP_STATE) or {}).get("completed", []))
    by_name: dict[str, list[tuple[str, datetime, bytes]]] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        e = json.loads(line)
        name, rel = e["name"], e["file"]
        if name not in SNAPSHOTS:
            log.warning("stopgap import: unknown snapshot name %r skipped", name)
            continue
        if rel in done or int(e.get("status", 200)) != 200:
            continue
        body = (root / rel).read_bytes()
        if "sha256" in e and hashlib.sha256(body).hexdigest() != e["sha256"]:
            raise DriftError(f"stopgap file {rel}: sha256 differs from the manifest")
        at = datetime.strptime(e["fetched_at"], "%Y-%m-%dT%H%M%S").replace(tzinfo=TAIPEI)
        by_name.setdefault(name, []).append((rel, at, body))
    counts: dict[str, int] = {}
    for name, files in by_name.items():
        rows, days = [], set()
        for _rel, at, body in files:
            rows += snapshot_rows(name, body, at)
            days.add(at.date())
        _write(ctx, name, rows, days)
        state.mark_stocks(ctx.settings, STOPGAP_STATE, [rel for rel, _, _ in files])
        counts[name] = len(files)
    return counts


def fetch_live(ctx, name: str) -> None:
    host, path = SNAPSHOTS[name]
    client = ctx.twse if host == "twse" else ctx.tpex
    _, resp = client.openapi(path)  # bypasses the cache by default
    at = resp.fetched_at or datetime.now(UTC)
    _write(ctx, name, snapshot_rows(name, resp.body, at), {at.astimezone(TAIPEI).date()})


def run(ctx) -> None:
    """The `snapshot` CLI command: import the stopgap files, then fetch the 15 endpoints."""
    import_stopgap(ctx)
    for name in SNAPSHOTS:
        fetch_live(ctx, name)
    ctx.cache.flush()


def run_dataset(ctx, start=None, end=None) -> None:
    """`fetch --dataset snapshots`: the range is ignored (latest-only sources)."""
    run(ctx)


DATASETS = {"snapshots": run_dataset}
