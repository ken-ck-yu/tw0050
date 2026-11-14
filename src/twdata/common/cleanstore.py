"""Append-only clean Parquet store (docs/specs/m0_specs.md section 5).

Rows are appended as new files under ``data/clean/<table>/v<N>/year=YYYY/``. No existing file is
modified or deleted. Timestamps are stored as UTC (``timestamp('us', tz='UTC')``).
"""

from __future__ import annotations

import math
import os
import uuid
from collections import defaultdict
from datetime import UTC, date, datetime
from pathlib import Path

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from twdata.common import paths
from twdata.common.config import Settings
from twdata.common.schema import TABLES, Table
from twdata.common.timeutil import TAIPEI

UTC_TS = pa.timestamp("us", tz="UTC")

# The one place where the spec's type names map to pyarrow types.
ARROW_TYPES: dict[str, pa.DataType] = {
    "DATE": pa.date32(),
    "VARCHAR": pa.string(),
    "BIGINT": pa.int64(),
    "DOUBLE": pa.float64(),
    "BOOLEAN": pa.bool_(),
    "TIMESTAMPTZ": UTC_TS,
}

NON_VALUE_COLUMNS = ("event_date", "fetched_at", "available_at", "first_seen_at")


class KeyUniquenessError(Exception):
    """The primary key is not unique."""


class PointInTimeError(Exception):
    """A non-null available_at is before its event_date."""


class SchemaError(ValueError):
    """A row does not match the table's columns, types or nullability."""


def split_type(type_text: str) -> tuple[str, bool]:
    """'DOUBLE?' -> ('DOUBLE', True)."""
    nullable = type_text.endswith("?")
    base = type_text[:-1] if nullable else type_text
    if base not in ARROW_TYPES:
        raise SchemaError(f"unknown column type {type_text!r}")
    return base, nullable


def arrow_schema(table: Table) -> pa.Schema:
    fields = []
    for name, typ in table.columns.items():
        base, nullable = split_type(typ)
        fields.append(pa.field(name, ARROW_TYPES[base], nullable=nullable))
    return pa.schema(fields)


def value_columns(table: Table) -> list[str]:
    """Columns compared to detect a changed value (section 15.3).

    Everything except the key columns, event_date, available_at, fetched_at and first_seen_at.
    """
    return [c for c in table.columns if c not in NON_VALUE_COLUMNS and c not in table.key]


def _resolve(table) -> Table:
    return table if isinstance(table, Table) else TABLES[table]


def _check_value(table: Table, col: str, base: str, v):
    where = f"{table.name}.{col}"
    if base == "DATE":
        if isinstance(v, datetime) or not isinstance(v, date):
            raise SchemaError(f"{where}: expected date, got {type(v).__name__}")
        return v
    if base == "VARCHAR":
        if not isinstance(v, str):
            raise SchemaError(f"{where}: expected str, got {type(v).__name__}")
        return v
    if base == "BIGINT":
        if isinstance(v, bool) or not isinstance(v, int):
            raise SchemaError(f"{where}: expected int, got {type(v).__name__}")
        if not -(2**63) <= v < 2**63:
            raise SchemaError(f"{where}: int out of BIGINT range")
        return v
    if base == "DOUBLE":
        if isinstance(v, bool) or not isinstance(v, int | float):
            raise SchemaError(f"{where}: expected float, got {type(v).__name__}")
        return float(v)
    if base == "BOOLEAN":
        if not isinstance(v, bool):
            raise SchemaError(f"{where}: expected bool, got {type(v).__name__}")
        return v
    if base == "TIMESTAMPTZ":
        if not isinstance(v, datetime) or v.tzinfo is None or v.utcoffset() is None:
            raise SchemaError(f"{where}: expected timezone-aware datetime")
        return v.astimezone(UTC)
    raise SchemaError(f"{where}: unknown type {base}")  # pragma: no cover


def validate_rows(table: Table, rows: list[dict]) -> list[dict]:
    """Return normalised copies of rows (UTC timestamps, floats), or raise SchemaError."""
    expected = [c for c in table.columns if c != "fetched_at"]
    expected_set = set(expected)
    out = []
    for i, row in enumerate(rows):
        got = set(row) - {"fetched_at"}  # a row may carry its own fetched_at (section 15.4)
        if got != expected_set:
            missing = sorted(expected_set - got)
            extra = sorted(got - expected_set)
            raise SchemaError(f"{table.name} row {i}: missing columns {missing}, extra {extra}")
        norm = {}
        for col in expected:
            base, nullable = split_type(table.columns[col])
            v = row[col]
            if v is None:
                if not nullable:
                    raise SchemaError(f"{table.name}.{col}: NULL in a NOT NULL column (row {i})")
                norm[col] = None
            else:
                norm[col] = _check_value(table, col, base, v)
        if row.get("fetched_at") is not None:
            norm["fetched_at"] = _check_value(table, "fetched_at", "TIMESTAMPTZ", row["fetched_at"])
        out.append(norm)
    return out


def _check_point_in_time(table: Table, rows: list[dict]) -> None:
    if "available_at" not in table.columns or "event_date" not in table.columns:
        return
    ecol = "event_date"
    for row in rows:
        av = row["available_at"]
        if av is None:
            continue
        # event_date is a Taipei calendar date; its first instant is Taipei midnight.
        start = datetime.combine(row[ecol], datetime.min.time(), tzinfo=TAIPEI)
        if av < start:
            raise PointInTimeError(
                f"{table.name}: available_at {av.isoformat()} is before {ecol} {row[ecol]}"
            )


def _key_of(table: Table, row: dict) -> tuple:
    return tuple(row[k] for k in table.key)


def _check_batch_unique(table: Table, rows: list[dict]) -> None:
    seen = set()
    for row in rows:
        k = _key_of(table, row)
        if k in seen:
            raise KeyUniquenessError(f"{table.name}: duplicate key {k} in batch")
        seen.add(k)


def _name(table) -> str:
    return table.name if isinstance(table, Table) else table


def current_version(s: Settings, table) -> int:
    p = paths.current_file(s, _name(table))
    if not p.exists():
        return 1
    text = p.read_text(encoding="utf-8").strip()
    try:
        v = int(text)
    except ValueError as e:
        raise ValueError(f"{p}: CURRENT must hold one integer, got {text!r}") from e
    if v < 1:
        raise ValueError(f"{p}: CURRENT must be >= 1, got {v}")
    return v


def set_current(s: Settings, table, version: int) -> None:
    name = _name(table)
    if not paths.clean_dir(s, name, version).is_dir():
        raise FileNotFoundError(f"{name}: version v{version} does not exist")
    p = paths.current_file(s, name)
    paths.ensure(p.parent)
    tmp = p.with_name(f"CURRENT.tmp{os.getpid()}-{uuid.uuid4().hex[:8]}")
    tmp.write_text(f"{version}\n", encoding="utf-8")
    os.replace(tmp, p)


def _same(a, b) -> bool:
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and math.isnan(b):
        return True
    return a == b


def sql_str(text: str) -> str:
    return "'" + text.replace("'", "''") + "'"


class CleanWriter:
    def __init__(self, settings: Settings, table, version: int | None = None):
        self.settings = settings
        self.table = _resolve(table)
        self.version = version if version is not None else current_version(settings, self.table)
        self.schema = arrow_schema(self.table)

    @property
    def root(self) -> Path:
        return paths.clean_dir(self.settings, self.table.name, self.version)

    def _latest_stored(self, year: int, rows: list[dict]) -> dict[tuple, dict]:
        """Latest stored row per key, for the keys in rows, from that year's files only."""
        year_dir = self.root / f"year={year}"
        if not year_dir.is_dir() or not any(year_dir.glob("*.parquet")):
            return {}
        t = self.table
        keys_tbl = pa.Table.from_pylist(
            [{k: r[k] for k in t.key} for r in rows],
            schema=pa.schema([self.schema.field(k) for k in t.key]),
        )
        cols = ", ".join(f't."{c}"' for c in t.columns)
        on = " AND ".join(f't."{k}" = k."{k}"' for k in t.key)
        part = ", ".join(f't."{k}"' for k in t.key)
        glob = sql_str(str(year_dir / "*.parquet"))
        sql = (
            f"SELECT {cols} FROM read_parquet({glob}, hive_partitioning=false, "
            f"union_by_name=true, filename=true) t JOIN batch_keys k ON {on} "
            f"QUALIFY row_number() OVER (PARTITION BY {part} "
            f'ORDER BY t."fetched_at" DESC, t.filename DESC) = 1'
        )
        con = duckdb.connect()
        try:
            con.register("batch_keys", keys_tbl)
            got = con.sql(sql).to_arrow_table()
        finally:
            con.close()
        got = got.cast(pa.schema([self.schema.field(c) for c in got.column_names]))
        return {_key_of(t, r): r for r in got.to_pylist()}

    def _decide(self, row: dict, stored: dict | None) -> bool:
        """True if the row must be written (new key, changed value, or a fill)."""
        if stored is None:
            return True
        for c in value_columns(self.table):
            if not _same(row[c], stored[c]):
                return True
        if "available_at" in self.table.columns:
            if stored["available_at"] is None and row["available_at"] is not None:
                return True  # fill
        return False

    def append(self, rows: list[dict], fetched_at: datetime | None = None) -> list[Path]:
        """Append rows. fetched_at is the batch value; a row's own 'fetched_at' wins."""
        t = self.table
        fetched_utc = None
        if fetched_at is not None:
            fetched_utc = _check_value(t, "fetched_at", "TIMESTAMPTZ", fetched_at)
        rows = validate_rows(t, rows)
        if fetched_utc is None and any(r.get("fetched_at") is None for r in rows):
            raise SchemaError(f"{t.name}: fetched_at missing (batch value or per row)")
        _check_batch_unique(t, rows)
        _check_point_in_time(t, rows)
        by_year: dict[int, list[dict]] = defaultdict(list)
        for r in rows:
            by_year[r[t.part].year].append(r)
        written: list[Path] = []
        for year in sorted(by_year):
            batch = by_year[year]
            stored = self._latest_stored(year, batch)
            todo = [r for r in batch if self._decide(r, stored.get(_key_of(t, r)))]
            if not todo:
                continue
            for r in todo:
                if r.get("fetched_at") is None:
                    r["fetched_at"] = fetched_utc
            tbl = pa.Table.from_pylist(todo, schema=self.schema)
            written.append(self._write(year, tbl))
        return written

    def _write(self, year: int, tbl: pa.Table) -> Path:
        d = paths.ensure(self.root / f"year={year}")
        stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f")
        name = f"run-{stamp}-{uuid.uuid4().hex[:8]}.parquet"
        final = d / name
        tmp = d / f".{name}.tmp"
        pq.write_table(tbl, tmp)
        os.replace(tmp, final)
        return final


def check_unique(con, table) -> None:
    """Primary-key uniqueness on the as_first_seen view; raises KeyUniquenessError."""
    t = _resolve(table)
    keys = ", ".join(f'"{k}"' for k in t.key)
    view = f"as_first_seen_{t.name}"
    dup = con.execute(
        f"SELECT {keys}, count(*) AS n FROM {view} GROUP BY {keys} HAVING count(*) > 1 LIMIT 1"
    ).fetchall()
    if dup:
        raise KeyUniquenessError(f"{t.name}: duplicate key {dup[0][:-1]} in {view}")
