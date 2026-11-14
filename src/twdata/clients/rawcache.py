"""Checksummed raw response cache (docs/specs/m0_specs.md section 8).

No credential is ever an input to ``put``; request headers never reach this module.
"""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.parquet as pq
from filelock import FileLock

from twdata.common import paths
from twdata.common.config import Settings

SHARD_SCHEMA = pa.schema(
    [
        ("request_key", pa.string()),
        ("url", pa.string()),
        ("params", pa.string()),
        ("fetched_at", pa.timestamp("us", tz="UTC")),
        ("status", pa.int64()),
        ("body", pa.binary()),
        ("body_sha256", pa.string()),
    ]
)


def request_key(method: str, url: str, params: dict) -> str:
    text = method + "\n" + url + "\n" + json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class CachedResponse:
    status: int
    body: bytes
    fetched_at: datetime
    shard: str | None  # None when served from the in-memory buffer


@dataclass(frozen=True)
class Problem:
    kind: str  # "missing", "sha256_mismatch", "unlisted", "bad_manifest_line"
    file: str
    detail: str = ""


def _utc(ts: datetime) -> datetime:
    if ts.tzinfo is None:
        raise ValueError("fetched_at must be timezone-aware")
    return ts.astimezone(UTC)


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _file_stamp() -> str:
    return datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:8]


def _write_parquet_atomic(path: Path, rows: list[dict]) -> None:
    table = pa.Table.from_pylist(rows, schema=SHARD_SCHEMA)
    tmp = path.with_name(f".tmp-{path.name}")
    try:
        pq.write_table(table, tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


class RawCache:
    def __init__(self, settings: Settings, area: str = "raw") -> None:
        self.settings = settings
        self.area = area
        paths.raw_dir(settings, "x", "x", area)  # validates the area
        self._buffers: dict[tuple[str, str], list[dict]] = {}
        # (source, dataset) -> [manifest lines consumed, {request_key: (fetched_at, shard)}]
        self._index: dict[tuple[str, str], list] = {}

    # -- paths ---------------------------------------------------------------------------
    def _dir(self, source: str, dataset: str) -> Path:
        return paths.raw_dir(self.settings, source, dataset, self.area)

    def _manifest(self, source: str, dataset: str) -> Path:
        return paths.manifest_file(self.settings, source, dataset, self.area)

    # -- writing -------------------------------------------------------------------------
    @staticmethod
    def _row(key, url, params, status, body, fetched_at) -> dict:
        return {
            "request_key": key,
            "url": url,
            "params": json.dumps(params, sort_keys=True, separators=(",", ":")),
            "fetched_at": _utc(fetched_at),
            "status": int(status),
            "body": bytes(body),
            "body_sha256": hashlib.sha256(body).hexdigest(),
        }

    def put(
        self,
        source: str,
        dataset: str,
        request_key: str,  # noqa: F811 - the spec's parameter name
        url: str,
        params: dict,
        status: int,
        body: bytes,
        fetched_at: datetime,
    ) -> None:
        buf = self._buffers.setdefault((source, dataset), [])
        buf.append(self._row(request_key, url, params, status, body, fetched_at))
        if len(buf) >= self.settings.raw_shard_max_responses:
            self._flush_one(source, dataset)

    def flush(self) -> None:
        for source, dataset in list(self._buffers):
            self._flush_one(source, dataset)

    def _flush_one(self, source: str, dataset: str) -> None:
        rows = self._buffers.get((source, dataset))
        if not rows:
            return
        directory = paths.ensure(self._dir(source, dataset))
        name = f"shard-{_file_stamp()}.parquet"
        final = directory / name
        _write_parquet_atomic(final, rows)  # on failure the buffer is kept for a retry
        times = [r["fetched_at"] for r in rows]
        line = {
            "file": name,
            "rows": len(rows),
            "sha256": _sha256_file(final),
            "first_fetched_at": min(times).isoformat(),
            "last_fetched_at": max(times).isoformat(),
        }
        manifest = self._manifest(source, dataset)
        paths.ensure(manifest.parent)
        try:
            with FileLock(str(manifest) + ".lock"), open(manifest, "a", encoding="utf-8") as f:
                f.write(json.dumps(line) + "\n")
                f.flush()
                os.fsync(f.fileno())
        except BaseException:
            final.unlink(missing_ok=True)
            raise
        self._buffers[(source, dataset)] = []

    def put_quarantine(
        self,
        source: str,
        dataset: str,
        request_key: str,  # noqa: F811
        url: str,
        params: dict,
        status: int,
        body: bytes,
        fetched_at: datetime,
    ) -> Path:
        directory = paths.ensure(paths.quarantine_dir(self.settings, source, dataset))
        path = directory / f"quarantine-{_file_stamp()}.parquet"
        _write_parquet_atomic(path, [self._row(request_key, url, params, status, body, fetched_at)])
        return path

    # -- reading -------------------------------------------------------------------------
    def _manifest_lines(self, source: str, dataset: str) -> list[dict]:
        out: list[dict] = []
        try:
            text = self._manifest(source, dataset).read_text(encoding="utf-8")
        except FileNotFoundError:
            return out
        for raw in text.splitlines():
            if not raw.strip():
                continue
            try:
                out.append(json.loads(raw))
            except ValueError:
                out.append({"_bad": raw})
        return out

    def _refresh_index(self, source: str, dataset: str) -> dict:
        entry = self._index.setdefault((source, dataset), [0, {}])
        lines = self._manifest_lines(source, dataset)
        directory = self._dir(source, dataset)
        for line in lines[entry[0] :]:
            shard = line.get("file")
            path = directory / shard if shard else None
            if path is not None and path.exists():
                t = pq.read_table(path, columns=["request_key", "fetched_at"])
                for k, ts in zip(t.column(0).to_pylist(), t.column(1).to_pylist(), strict=True):
                    cur = entry[1].get(k)
                    if cur is None or ts >= cur[0]:
                        entry[1][k] = (ts, shard)
        entry[0] = len(lines)
        return entry[1]

    def get(self, source: str, dataset: str, request_key: str) -> CachedResponse | None:  # noqa: F811
        best: CachedResponse | None = None
        for row in self._buffers.get((source, dataset), []):
            if row["request_key"] == request_key and (
                best is None or row["fetched_at"] >= best.fetched_at
            ):
                best = CachedResponse(row["status"], row["body"], row["fetched_at"], None)
        stored = self._refresh_index(source, dataset).get(request_key)
        if stored is not None and (best is None or stored[0] > best.fetched_at):
            shard = stored[1]
            t = pq.read_table(self._dir(source, dataset) / shard)
            rows = t.filter(pc.equal(t["request_key"], request_key)).to_pylist()
            rows.sort(key=lambda r: r["fetched_at"])
            r = rows[-1]
            best = CachedResponse(r["status"], r["body"], r["fetched_at"], shard)
        return best

    def verify(self, source: str, dataset: str) -> list[Problem]:
        problems: list[Problem] = []
        directory = self._dir(source, dataset)
        listed: set[str] = set()
        for line in self._manifest_lines(source, dataset):
            if "_bad" in line:
                problems.append(Problem("bad_manifest_line", "", line["_bad"][:80]))
                continue
            name = line.get("file", "")
            listed.add(name)
            path = directory / name
            if not path.exists():
                problems.append(Problem("missing", name))
            elif _sha256_file(path) != line.get("sha256"):
                problems.append(Problem("sha256_mismatch", name))
        if directory.exists():
            for p in sorted(directory.glob("shard-*.parquet")):
                if p.name not in listed:
                    problems.append(Problem("unlisted", p.name))
        return problems
