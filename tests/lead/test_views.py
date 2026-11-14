from datetime import UTC, date, datetime, timedelta

import duckdb
import pytest

from twdata.common import config
from twdata.common.cleanstore import (
    CleanWriter,
    KeyUniquenessError,
    check_unique,
    set_current,
)
from twdata.common.views import register_view, register_views

T0 = datetime(2025, 6, 2, 11, 0, 0, tzinfo=UTC)
AV = datetime(2025, 6, 2, 10, 0, 0, tzinfo=UTC)
D = date(2025, 6, 2)


def S(tmp_path):
    return config.load_settings(data_dir_override=str(tmp_path))


def bench(value=1.0, av=AV, d=D, index_id="TAIEX_TR"):
    return {"event_date": d, "available_at": av, "index_id": index_id, "value": value}


def q(con, sql):
    """Fetch through Arrow: DuckDB's Python TIMESTAMPTZ conversion needs pytz, which is absent."""
    tbl = con.sql(sql).to_arrow_table()
    cols = [c.to_pylist() for c in tbl.columns]
    return list(zip(*cols, strict=True)) if cols else []


def day(n):
    return T0 + timedelta(days=n)


def views(s, table="benchmark_index"):
    con = duckdb.connect()
    assert table in register_views(con, s)
    out = {}
    for v in ("as_first_seen", "as_latest_corrected", "revisions", "default"):
        out[v] = q(
            con,
            f"SELECT index_id, value, available_at, fetched_at FROM {v}_{table} "
            "ORDER BY event_date, index_id, fetched_at",
        )
    return con, out


def test_no_views_without_files(tmp_path):
    con = duckdb.connect()
    assert register_views(con, S(tmp_path)) == []
    assert con.execute("SELECT count(*) FROM duckdb_views() WHERE NOT internal").fetchone() == (0,)


def test_single_row(tmp_path):
    s = S(tmp_path)
    CleanWriter(s, "benchmark_index").append([bench(1.0)], T0)
    _, v = views(s)
    row = [("TAIEX_TR", 1.0, AV, T0)]
    assert v["as_first_seen"] == row and v["as_latest_corrected"] == row
    assert v["revisions"] == []


def test_changed_value_views_differ(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0)], T0)
    assert len(w.append([bench(2.0)], day(3))) == 1
    con, v = views(s)
    assert v["as_first_seen"][0][1] == 1.0
    assert v["as_latest_corrected"][0][1] == 2.0
    assert len(v["revisions"]) == 1 and v["revisions"][0][1] == 2.0
    # source_error table: default is latest-corrected
    assert v["default"] == v["as_latest_corrected"]
    check_unique(con, "benchmark_index")


def test_default_view_for_economic_table_is_first_seen(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "valuation_ratios")

    def row(per):
        return {
            "event_date": D,
            "available_at": AV,
            "stock_id": "2330",
            "dividend_yield": None,
            "PER": per,
            "PBR": None,
        }

    w.append([row(10.0)], T0)
    w.append([row(12.0)], day(2))
    con = duckdb.connect()
    register_views(con, s)
    assert con.execute('SELECT "PER" FROM default_valuation_ratios').fetchall() == [(10.0,)]
    assert con.execute('SELECT "PER" FROM as_latest_corrected_valuation_ratios').fetchall() == [
        (12.0,)
    ]


def test_pending_available_at_filled_later(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0, av=None)], T0)
    con, v = views(s)
    assert v["as_first_seen"][0][2] is None  # still pending
    assert len(w.append([bench(1.0, av=AV)], day(2))) == 1  # fill
    _, v = views(s)
    assert v["as_first_seen"] == [("TAIEX_TR", 1.0, AV, T0)]  # first fetched_at, filled value
    assert v["as_latest_corrected"][0][2] == AV
    assert v["revisions"] == []


def test_revision_available_at_is_max_of_available_at_and_fetched_at(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0)], T0)
    # available_at earlier than fetched_at: revision is available at fetched_at
    w.append([bench(2.0, av=AV)], day(5))
    # available_at later than fetched_at: stays
    late = day(30) + timedelta(hours=6)
    w.append([bench(3.0, av=late)], day(30))
    _, v = views(s)
    assert [(r[1], r[2]) for r in v["revisions"]] == [(2.0, day(5)), (3.0, late)]
    # the latest-corrected row is not joinable before it was fetched either
    assert v["as_latest_corrected"][0][1:3] == (3.0, late)
    assert v["as_first_seen"][0][2] == AV


def test_fill_of_a_revision_is_not_a_second_revision(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0)], T0)
    w.append([bench(2.0, av=None)], day(1))
    w.append([bench(2.0, av=AV)], day(2))  # fill of the revision
    _, v = views(s)
    assert len(v["revisions"]) == 1
    assert v["revisions"][0][1] == 2.0
    assert v["revisions"][0][2] == day(1)  # max(AV, fetched_at of the revision row)
    assert v["as_latest_corrected"][0][1:3] == (2.0, day(1))


def test_pending_revision_stays_null(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0)], T0)
    w.append([bench(2.0, av=None)], day(1))
    _, v = views(s)
    assert v["revisions"][0][2] is None and v["as_latest_corrected"][0][2] is None


def test_ties_in_fetched_at_broken_by_file_name(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0)], T0)
    w.append([bench(2.0)], T0)  # same fetched_at, later file name
    _, v = views(s)
    assert v["as_first_seen"][0][1] == 1.0
    assert v["as_latest_corrected"][0][1] == 2.0


def test_multiple_keys_and_years_with_union_by_name(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append(
        [
            bench(1.0, index_id="A"),
            bench(2.0, index_id="B"),
            bench(3.0, d=date(2024, 6, 3), av=datetime(2024, 6, 3, 10, tzinfo=UTC), index_id="A"),
        ],
        T0,
    )
    w.append([bench(2.5, index_id="B")], day(1))
    con, v = views(s)
    assert len(v["as_first_seen"]) == 3 and len(v["as_latest_corrected"]) == 3
    latest = {(r[0], r[1]) for r in v["as_latest_corrected"]}
    assert ("B", 2.5) in latest and ("B", 2.0) not in latest
    assert [r[0] for r in v["revisions"]] == ["B"]


def test_views_use_current_version_only(tmp_path):
    s = S(tmp_path)
    CleanWriter(s, "benchmark_index").append([bench(1.0)], T0)
    CleanWriter(s, "benchmark_index", version=2).append([bench(9.0)], day(1))
    _, v = views(s)
    assert v["as_first_seen"][0][1] == 1.0  # CURRENT absent means v1
    set_current(s, "benchmark_index", 2)
    _, v = views(s)
    assert v["as_first_seen"][0][1] == 9.0 and v["revisions"] == []


def test_table_without_available_at(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "trading_calendar")
    row = {"event_date": D, "is_trading": True, "source": "finmind"}
    w.append([row], T0)
    w.append([{**row, "is_trading": False}], day(1))
    con = duckdb.connect()
    register_views(con, s)
    assert q(con, "SELECT is_trading FROM as_first_seen_trading_calendar") == [(True,)]
    assert q(con, "SELECT is_trading FROM default_trading_calendar") == [(False,)]
    assert con.execute("SELECT count(*) FROM revisions_trading_calendar").fetchone() == (1,)


def test_null_values_compare_as_equal(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "valuation_ratios")
    row = {
        "event_date": D,
        "available_at": None,
        "stock_id": "2330",
        "dividend_yield": None,
        "PER": None,
        "PBR": 1.0,
    }
    w.append([row], T0)
    w.append([{**row, "available_at": AV}], day(1))
    con = duckdb.connect()
    register_views(con, s)
    assert q(con, "SELECT count(*) FROM revisions_valuation_ratios") == [(0,)]
    assert q(con, "SELECT available_at FROM as_first_seen_valuation_ratios") == [(AV,)]


def test_register_view_and_name_check(tmp_path):
    CleanWriter(S(tmp_path), "benchmark_index").append([bench(1.0)], T0)
    register_view("answer_x", "SELECT count(*) AS x FROM as_first_seen_benchmark_index")
    con = duckdb.connect()
    register_views(con, S(tmp_path))
    assert con.execute("SELECT x FROM answer_x").fetchone() == (1,)
    with pytest.raises(ValueError):
        register_view("bad name; DROP", "SELECT 1")


def test_check_unique_raises_on_duplicate_keys(tmp_path):
    con = duckdb.connect()
    con.execute("CREATE TABLE t AS SELECT 'A' AS index_id, DATE '2025-06-02' AS event_date")
    con.execute("INSERT INTO t VALUES ('A', DATE '2025-06-02')")
    con.execute("CREATE VIEW as_first_seen_benchmark_index AS SELECT * FROM t")
    with pytest.raises(KeyUniquenessError):
        check_unique(con, "benchmark_index")


def test_per_row_fetched_at_wins(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    early = T0 - timedelta(days=10)
    w.append([{**bench(1.0), "fetched_at": early}], T0)
    w.append([bench(2.0, index_id="B")], T0)
    _, v = views(s)
    assert {(r[0], r[3]) for r in v["as_first_seen"]} == {("TAIEX_TR", early), ("B", T0)}
