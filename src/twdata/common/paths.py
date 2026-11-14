"""The only module that builds data paths."""

from __future__ import annotations

from pathlib import Path

from twdata.common.config import Settings


def ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_dir(s: Settings, source: str, dataset: str, area: str = "raw") -> Path:
    if area == "raw":
        return s.data_dir / "raw" / source / dataset
    if area == "qa":
        return s.data_dir / "raw" / "qa" / source / dataset
    raise ValueError(f"unknown area {area!r}")


def quarantine_dir(s: Settings, source: str, dataset: str) -> Path:
    return s.data_dir / "raw" / "quarantine" / source / dataset


def clean_dir(s: Settings, table: str, version: int) -> Path:
    return s.data_dir / "clean" / table / f"v{version}"


def current_file(s: Settings, table: str) -> Path:
    return s.data_dir / "clean" / table / "CURRENT"


def state_file(s: Settings, dataset: str) -> Path:
    return s.data_dir / "state" / f"{dataset}.json"


def manifest_file(s: Settings, source: str, dataset: str) -> Path:
    return s.data_dir / "state" / "manifest" / source / f"{dataset}.jsonl"


def host_lock_file(s: Settings, host: str) -> Path:
    return s.data_dir / "state" / "locks" / f"{host}.lock"


def host_state_file(s: Settings, host: str) -> Path:
    return s.data_dir / "state" / "locks" / f"{host}.json"


def calendar_ledger(s: Settings) -> Path:
    return s.data_dir / "state" / "calendar_discrepancy.jsonl"


def snapshot_dir(s: Settings) -> Path:
    return s.data_dir / "raw" / "snapshots"
