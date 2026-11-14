"""Settings loader. All keys are required (docs/specs/m0_specs.md section 4)."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, fields
from datetime import date
from pathlib import Path

import yaml


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class Spacing:
    twse: float
    tpex: float


@dataclass(frozen=True)
class Timeouts:
    twse: float
    tpex: float
    finmind: float


@dataclass(frozen=True)
class FinMindCfg:
    target_fraction: float
    user_info_refresh_requests: int


@dataclass(frozen=True)
class RowCaps:
    finmind_default: int
    twse: int
    tpex: int
    datasets: dict


@dataclass(frozen=True)
class Checks:
    coverage: float
    close_sample: int
    adj_sample: int
    adj_return_tolerance: float
    check4_max_mismatch: int
    unexplained_move: float
    churn_min: float
    churn_max: float
    qa_seed: int


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    start_date: date
    window_start: date
    liquidity_floor_ntd: int
    min_observed_days: int
    universe_size: int
    spacing_s: Spacing
    timeout_s: Timeouts
    retry_waits_s: tuple
    user_agent: str
    finmind: FinMindCfg
    row_caps: RowCaps
    raw_shard_max_responses: int
    disk_report_fraction: float
    checks: Checks
    backup_dir: Path | None


_NESTED = {
    "spacing_s": Spacing,
    "timeout_s": Timeouts,
    "finmind": FinMindCfg,
    "row_caps": RowCaps,
    "checks": Checks,
}


def repo_root() -> Path:
    """The directory containing pyproject.toml, found from this file's location."""
    here = Path(__file__).resolve()
    for parent in here.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    raise ConfigError("pyproject.toml not found above " + str(here))


def _build(cls, raw: dict, where: str):
    names = {f.name for f in fields(cls)}
    missing = names - set(raw)
    unknown = set(raw) - names
    if missing:
        raise ConfigError(f"missing key(s) in {where}: {sorted(missing)}")
    if unknown:
        raise ConfigError(f"unknown key(s) in {where}: {sorted(unknown)}")
    return raw


def load_settings(path: str | Path | None = None, data_dir_override: str | None = None) -> Settings:
    root = repo_root()
    cfg_path = Path(path) if path else root / "config" / "settings.yaml"
    raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8")) or {}
    _build(Settings, raw, "settings.yaml")
    kwargs = dict(raw)
    for key, cls in _NESTED.items():
        sub = kwargs[key]
        _build(cls, sub, key)
        kwargs[key] = cls(**sub)
    data_dir = data_dir_override or os.environ.get("TWDATA_DATA_DIR") or kwargs["data_dir"]
    data_dir = Path(data_dir)
    kwargs["data_dir"] = data_dir if data_dir.is_absolute() else root / data_dir
    kwargs["retry_waits_s"] = tuple(kwargs["retry_waits_s"])
    bd = kwargs["backup_dir"]
    kwargs["backup_dir"] = Path(bd) if bd else None
    for k in ("start_date", "window_start"):
        v = kwargs[k]
        kwargs[k] = v if isinstance(v, date) else date.fromisoformat(str(v))
    return Settings(**kwargs)


_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def load_env(path: str | Path | None = None) -> list[str]:
    """Load KEY=VALUE lines from .env into os.environ without overriding. Returns key names only."""
    p = Path(path) if path else repo_root() / ".env"
    loaded: list[str] = []
    if not p.exists():
        return loaded
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        m = _ENV_LINE.match(line)
        if not m:
            continue
        key, value = m.group(1), m.group(2)
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
