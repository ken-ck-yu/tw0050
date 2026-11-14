"""Experiment log (research/experiment_log.jsonl), budget and the evaluator hash."""

from __future__ import annotations

import fcntl
import hashlib
import json
import math
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path

from twdata.common.config import repo_root
from twdata.research.evaluator import metrics
from twdata.research.evaluator.constants import ANNUALIZATION, BudgetError

EVALUATOR_DIR = Path(__file__).resolve().parent
LOG_PATH = repo_root() / "research" / "experiment_log.jsonl"  # tests monkeypatch this
HASH_PATH = repo_root() / "research" / "EVALUATOR_SHA256"


def evaluator_files() -> list[Path]:
    return sorted(EVALUATOR_DIR.glob("*.py"), key=lambda p: p.name)


def evaluator_sha256() -> str:
    """SHA-256 of the concatenated bytes of the evaluator's .py files in sorted name order."""
    h = hashlib.sha256()
    for p in evaluator_files():
        h.update(p.read_bytes())
    return h.hexdigest()


def params_hash(params: dict) -> str:
    text = json.dumps(params, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _default(o):
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    raise TypeError(f"not JSON serialisable: {type(o).__name__}")


def _clean(o):
    """Replace non-finite floats (invalid JSON) by None, recursively."""
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    return o


def dumps(obj: dict) -> str:
    return json.dumps(_clean(obj), sort_keys=True, default=_default)


@contextmanager
def locked_log():
    LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_PATH, "a+", encoding="utf-8") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        try:
            yield fh
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def _rows(fh) -> list[dict]:
    fh.seek(0)
    rows = []
    for line in fh.read().splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            rows.append({"status": "unparseable"})  # still counted, never silently dropped
    return rows


def read_log() -> list[dict]:
    with locked_log() as fh:
        return _rows(fh)


def runs_in_cycle(cycle: int) -> int:
    return sum(1 for r in read_log() if r.get("cycle") == cycle)


def check_budget(research_cfg) -> None:
    """Raise BudgetError when this would be run number max_runs_per_cycle + 1 of the cycle.
    Error lines count as runs. A refused call writes nothing."""
    n = runs_in_cycle(research_cfg.cycle)
    if n >= research_cfg.max_runs_per_cycle:
        raise BudgetError(
            f"cycle {research_cfg.cycle} already has {n} runs "
            f"(budget {research_cfg.max_runs_per_cycle})"
        )


def append_ok(record: dict, net_sharpe_annual: float, n_obs: int, skew: float, kurt: float) -> dict:
    """Fill n_trials and deflated_sharpe from the log (under the lock) and append the line.
    Returns the completed record dict."""
    with locked_log() as fh:
        rows = _rows(fh)
        n_trials = len(rows) + 1
        trials = [
            r["net_sharpe"] / math.sqrt(ANNUALIZATION)
            for r in rows
            if r.get("status") == "ok" and isinstance(r.get("net_sharpe"), (int, float))
        ]
        trials.append(net_sharpe_annual / math.sqrt(ANNUALIZATION))
        record["n_trials"] = n_trials
        record["deflated_sharpe"] = metrics.deflated_sharpe(
            net_sharpe_annual / math.sqrt(ANNUALIZATION), n_obs, skew, kurt, n_trials, trials
        )
        fh.write(dumps(record) + "\n")
        fh.flush()
    return record


def append_error(line: dict) -> None:
    with locked_log() as fh:
        fh.write(dumps(line) + "\n")
        fh.flush()
