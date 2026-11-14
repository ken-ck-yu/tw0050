"""DuckDB views over the current clean version (docs/specs/m0_specs.md section 5).

For each table with clean files, ``register_views`` creates ``as_first_seen_<t>``,
``as_latest_corrected_<t>``, ``revisions_<t>`` and ``default_<t>``.

Definitions (rows of one key ordered by ``fetched_at``, ties by file name):

* first row: the earliest. Its ``available_at`` is the earliest non-null ``available_at`` among the
  rows of that key whose value columns equal the first row's, so a fill supplies a pending value.
* latest row: the latest, with the same substitution against the latest row's values. When the
  latest values differ from the first row's (a revision), its ``available_at`` is
  ``max(available_at, fetched_at of the first row with those values)``, so the corrected
  value is never joined before it was fetched.
* value columns: all columns except key columns, event_date, available_at, fetched_at and
  first_seen_at.
* revision: a row whose values differ from the previous row's and from the first row's. A fill
  (same values as the previous row, new ``available_at``) is not a revision. Its ``available_at``
  is ``max(earliest non-null available_at of its run of equal rows, fetched_at)``, null if pending.
"""

from __future__ import annotations

import re
from pathlib import Path

from twdata.common import paths
from twdata.common.cleanstore import current_version, sql_str, value_columns
from twdata.common.config import Settings
from twdata.common.schema import TABLES, Table

_IDENT = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


def _q(col: str) -> str:
    return '"' + col.replace('"', '""') + '"'


_EXTRA_VIEWS: dict[str, str] = {}


def register_view(name: str, sql: str) -> None:
    """Store an extra view definition (section 15.13); register_views creates it per connection."""
    if not _IDENT.match(name):
        raise ValueError(f"invalid view name {name!r}")
    _EXTRA_VIEWS[name] = sql


def _create(con, name: str, sql: str) -> None:
    con.execute(f"CREATE OR REPLACE VIEW {name} AS {sql}")


def has_clean_files(s: Settings, table: Table) -> bool:
    root = paths.clean_dir(s, table.name, current_version(s, table))
    return root.is_dir() and any(root.glob("year=*/*.parquet"))


def _glob(s: Settings, table: Table) -> Path:
    return paths.clean_dir(s, table.name, current_version(s, table)) / "year=*" / "*.parquet"


def _base_sql(s: Settings, table: Table) -> str:
    """SQL text of a query with the flags needed by the four views (one row per stored row)."""
    keys = ", ".join(_q(k) for k in table.key)
    vals = value_columns(table)
    has_av = "available_at" in table.columns
    cols = ", ".join(_q(c) for c in table.columns)
    eq_first = (
        " AND ".join(f"{_q(v)} IS NOT DISTINCT FROM first_value({_q(v)}) OVER wf" for v in vals)
        or "TRUE"
    )
    eq_last = (
        " AND ".join(f"{_q(v)} IS NOT DISTINCT FROM last_value({_q(v)}) OVER wf" for v in vals)
        or "TRUE"
    )
    chg = " OR ".join(f"{_q(v)} IS DISTINCT FROM lag({_q(v)}) OVER w" for v in vals) or "FALSE"
    glob = sql_str(str(_glob(s, table)))
    av_first = av_last = av_run = "NULL::TIMESTAMPTZ"
    if has_av:
        av_first = f"min(CASE WHEN eq_first THEN available_at END) OVER (PARTITION BY {keys})"
        av_last = f"min(CASE WHEN eq_last THEN available_at END) OVER (PARTITION BY {keys})"
        av_run = f"min(available_at) OVER (PARTITION BY {keys}, grp)"
    return f"""
WITH src AS (
  SELECT {cols}, filename
  FROM read_parquet({glob}, hive_partitioning = false, union_by_name = true, filename = true)
),
c1 AS (
  SELECT {cols}, filename,
    row_number() OVER w AS rn,
    count(*) OVER (PARTITION BY {keys}) AS n,
    ({eq_first}) AS eq_first,
    ({eq_last}) AS eq_last,
    ({chg}) AS chg
  FROM src
  WINDOW w AS (PARTITION BY {keys} ORDER BY fetched_at, filename),
         wf AS (PARTITION BY {keys} ORDER BY fetched_at, filename
                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
),
c2 AS (
  SELECT *,
    sum(CASE WHEN rn > 1 AND chg THEN 1 ELSE 0 END)
      OVER (PARTITION BY {keys} ORDER BY rn ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW)
      AS grp
  FROM c1
),
c3 AS (
  SELECT *, {av_first} AS av_first, {av_last} AS av_last, {av_run} AS av_run,
    min(fetched_at) OVER (PARTITION BY {keys}, grp) AS f_run
  FROM c2
)
"""


def _select(table: Table, av_expr: str | None) -> str:
    parts = []
    for c in table.columns:
        if c == "available_at" and av_expr is not None:
            parts.append(f"{av_expr} AS available_at")
        else:
            parts.append(_q(c))
    return ", ".join(parts)


def _view_sqls(s: Settings, table: Table) -> dict[str, str]:
    base = _base_sql(s, table)
    has_av = "available_at" in table.columns
    first_av = "av_first" if has_av else None
    latest_av = rev_av = None
    if has_av:
        latest_av = (
            "CASE WHEN av_last IS NULL THEN NULL "
            "WHEN NOT eq_first THEN greatest(av_last, f_run) ELSE av_last END"
        )
        rev_av = "CASE WHEN av_run IS NULL THEN NULL ELSE greatest(av_run, fetched_at) END"
    return {
        "as_first_seen": f"{base} SELECT {_select(table, first_av)} FROM c3 WHERE rn = 1",
        "as_latest_corrected": f"{base} SELECT {_select(table, latest_av)} FROM c3 WHERE rn = n",
        "revisions": (
            f"{base} SELECT {_select(table, rev_av)} FROM c3 WHERE rn > 1 AND chg AND NOT eq_first"
        ),
    }


def register_views(con, settings: Settings) -> list[str]:
    """Create the views for every table that has clean files; return those table names."""
    done = []
    for table in TABLES.values():
        if not has_clean_files(settings, table):
            continue
        t = table.name
        sqls = _view_sqls(settings, table)
        for prefix, sql in sqls.items():
            _create(con, f"{prefix}_{t}", sql)
        default = "as_first_seen" if table.restatement == "economic" else "as_latest_corrected"
        _create(con, f"default_{t}", f"SELECT * FROM {default}_{t}")
        done.append(t)
    for name, sql in _EXTRA_VIEWS.items():
        try:
            _create(con, name, sql)
        except Exception as e:  # an extra view over a table that has no files yet is skipped
            if "does not exist" not in str(e):
                raise
    return done
