"""Cross-process rate limiters (docs/specs/m0_specs.md section 8)."""

from __future__ import annotations

import json
import math
import os
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from pathlib import Path

from filelock import FileLock

WINDOW_S = 3600.0


def _read_json(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_json(path: Path, data: dict) -> None:
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data), encoding="utf-8")
    os.replace(tmp, path)


class HostLimiter:
    """One request in flight per host across processes, spaced from the last completion."""

    def __init__(
        self,
        host: str,
        min_interval_s: float,
        lock_path: Path,
        state_path: Path,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.host = host
        self.min_interval_s = float(min_interval_s)
        self.lock_path = Path(lock_path)
        self.state_path = Path(state_path)
        self._now = now
        self._sleep = sleep
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self.lock_path))

    @contextmanager
    def slot(self) -> Iterator[None]:
        with self._lock:
            last = _read_json(self.state_path).get("last_completion")
            if isinstance(last, int | float):
                wait = last + self.min_interval_s - self._now()
                # Cap at the interval: a clock jump (WSL2 sleep) must not stall the run.
                wait = min(max(wait, 0.0), self.min_interval_s)
                if wait > 0:
                    self._sleep(wait)
            try:
                yield
            finally:
                _write_json(self.state_path, {"last_completion": self._now()})


class QuotaLimiter:
    """Persisted sliding 3,600 s window, kept at or under limit_per_hour * target_fraction."""

    def __init__(
        self,
        limit_per_hour: int,
        target_fraction: float,
        state_path: Path,
        lock_path: Path,
        now: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self.limit_per_hour = int(limit_per_hour)
        self.target_fraction = float(target_fraction)
        self.state_path = Path(state_path)
        self.lock_path = Path(lock_path)
        self._now = now
        self._sleep = sleep
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = FileLock(str(self.lock_path))

    @property
    def cap(self) -> int:
        return math.floor(self.limit_per_hour * self.target_fraction)

    def _stamps(self, now: float) -> list[float]:
        raw = _read_json(self.state_path).get("stamps", [])
        return sorted(t for t in raw if isinstance(t, int | float) and now - WINDOW_S < t <= now)

    def update(self, limit_per_hour: int, user_count: int) -> None:
        """Apply a user-info reading. Requests the server counted but we did not are added."""
        with self._lock:
            self.limit_per_hour = int(limit_per_hour)
            now = self._now()
            stamps = self._stamps(now)
            missing = int(user_count) - len(stamps)
            if missing > 0:
                stamps = sorted(stamps + [now] * missing)
            _write_json(self.state_path, {"stamps": stamps})

    @contextmanager
    def slot(self) -> Iterator[None]:
        while True:
            with self._lock:
                now = self._now()
                stamps = self._stamps(now)
                cap = self.cap
                if len(stamps) < cap:
                    stamps.append(now)
                    _write_json(self.state_path, {"stamps": stamps})
                    break
                _write_json(self.state_path, {"stamps": stamps})
                # The request fits once the (len - cap + 1)th oldest stamp leaves the window.
                free_at = stamps[len(stamps) - cap] + WINDOW_S if cap > 0 else now + WINDOW_S
                wait = max(free_at - now, 0.001)
            self._sleep(wait)
        yield
