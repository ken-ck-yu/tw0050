import os
from datetime import UTC, date, datetime, timedelta

import pyarrow.parquet as pq
import pytest

from twdata.common import config, paths
from twdata.common.cleanstore import (
    ARROW_TYPES,
    CleanWriter,
    KeyUniquenessError,
    PointInTimeError,
    SchemaError,
    arrow_schema,
    current_version,
    set_current,
)
from twdata.common.schema import TABLES


def S(tmp_path):
    return config.load_settings(data_dir_override=str(tmp_path))


def bench(value=1.0, av=None, d=date(2025, 6, 2), index_id="TAIEX_TR"):
    return {"event_date": d, "available_at": av, "index_id": index_id, "value": value}


T0 = datetime(2025, 6, 2, 11, 0, 0, tzinfo=UTC)
AV = datetime(2025, 6, 2, 10, 0, 0, tzinfo=UTC)


def all_files(tmp_path):
    return sorted(p for p in tmp_path.rglob("*") if p.is_file())


def test_every_table_has_valid_key_part_and_types():
    for t in TABLES.values():
        assert set(t.key) <= set(t.columns), t.name
        assert t.part in t.columns, t.name
        assert "fetched_at" in t.columns, t.name
        arrow_schema(t)  # every type maps
    assert set(ARROW_TYPES) == {"DATE", "VARCHAR", "BIGINT", "DOUBLE", "BOOLEAN", "TIMESTAMPTZ"}


def test_append_writes_year_partition_with_utc_schema(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    rows = [bench(1.0, AV), bench(2.0, AV, d=date(2024, 12, 31), index_id="TPEX_TR")]
    files = w.append(rows, T0)
    assert len(files) == 2
    assert {f.parent.name for f in files} == {"year=2025", "year=2024"}
    assert all(f.parent.parent.name == "v1" for f in files)
    for f in files:
        assert f.name.startswith("run-") and f.suffix == ".parquet"
        stamp, uid = f.stem[len("run-") :].rsplit("-", 1)
        assert len(stamp) == 21 and stamp[8] == "T" and len(uid) == 8
    tbl = pq.read_table(files[0])
    assert tbl.schema.field("fetched_at").type == ARROW_TYPES["TIMESTAMPTZ"]
    assert tbl.schema.field("available_at").type == ARROW_TYPES["TIMESTAMPTZ"]
    assert not any(p.name.endswith(".tmp") for p in all_files(tmp_path))


def test_taipei_fetched_at_is_stored_as_utc(tmp_path):
    from zoneinfo import ZoneInfo

    s = S(tmp_path)
    f = CleanWriter(s, "benchmark_index").append(
        [bench(1.0, AV)], datetime(2025, 6, 2, 19, 0, tzinfo=ZoneInfo("Asia/Taipei"))
    )[0]
    got = pq.read_table(f).column("fetched_at").to_pylist()[0]
    assert got == datetime(2025, 6, 2, 11, 0, tzinfo=UTC)


def test_duplicate_key_in_batch_fails_and_writes_nothing(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    with pytest.raises(KeyUniquenessError):
        w.append([bench(1.0, AV), bench(2.0, AV)], T0)
    assert all_files(tmp_path) == []


def test_identical_rerun_writes_nothing(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    assert len(w.append([bench(1.0, AV)], T0)) == 1
    before = all_files(tmp_path)
    # same values, even with a different available_at and fetched_at
    later = AV + timedelta(hours=3)
    assert w.append([bench(1.0, AV)], T0 + timedelta(days=1)) == []
    assert w.append([bench(1.0, later)], T0 + timedelta(days=2)) == []
    assert all_files(tmp_path) == before


def test_changed_value_writes_one_run_file(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0, AV), bench(5.0, AV, index_id="TPEX_TR")], T0)
    out = w.append([bench(1.5, AV), bench(5.0, AV, index_id="TPEX_TR")], T0 + timedelta(days=1))
    assert len(out) == 1
    assert pq.read_table(out[0]).num_rows == 1  # only the changed key


def test_changed_value_compared_with_latest_not_first(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0, AV)], T0)
    w.append([bench(2.0, AV)], T0 + timedelta(days=1))
    assert w.append([bench(2.0, AV)], T0 + timedelta(days=2)) == []
    assert len(w.append([bench(1.0, AV)], T0 + timedelta(days=3))) == 1


def test_fill_of_pending_available_at(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    assert len(w.append([bench(1.0, None)], T0)) == 1
    assert w.append([bench(1.0, None)], T0 + timedelta(days=1)) == []  # still pending
    out = w.append([bench(1.0, AV)], T0 + timedelta(days=2))
    assert len(out) == 1  # the fill
    assert w.append([bench(1.0, AV)], T0 + timedelta(days=3)) == []


def test_available_at_before_event_date_raises(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    with pytest.raises(PointInTimeError):
        w.append([bench(1.0, datetime(2025, 6, 1, 8, 0, tzinfo=UTC))], T0)
    assert all_files(tmp_path) == []
    # Taipei midnight of the event date is the first allowed instant
    ok = datetime(2025, 6, 1, 16, 0, tzinfo=UTC)
    assert len(w.append([bench(1.0, ok)], T0)) == 1


def test_two_appends_in_same_second_write_distinct_files(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    a = w.append([bench(1.0, AV)], T0)
    b = w.append([bench(2.0, AV)], T0)  # same fetched_at, changed value
    c = w.append([bench(3.0, AV)], T0)
    assert len({*a, *b, *c}) == 3
    assert all(p.exists() for p in (*a, *b, *c))


def test_no_existing_file_is_modified(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0, None)], T0)
    snap = {p: (p.stat().st_mtime_ns, p.read_bytes()) for p in all_files(tmp_path)}
    w.append([bench(1.0, AV)], T0 + timedelta(days=1))
    w.append([bench(9.0, AV)], T0 + timedelta(days=2))
    for p, (mt, data) in snap.items():
        assert p.exists() and p.stat().st_mtime_ns == mt and p.read_bytes() == data
    assert len(all_files(tmp_path)) == 3


def test_validation_errors(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    bad = [
        {**bench(1.0, AV), "extra": 1},  # extra column
        {k: v for k, v in bench(1.0, AV).items() if k != "value"},  # missing column
        {**bench(1.0, AV), "value": "1.0"},  # wrong type
        {**bench(1.0, AV), "value": None},  # NOT NULL
        {**bench(1.0, AV), "value": True},  # bool is not a DOUBLE
        {**bench(1.0, AV), "event_date": datetime(2025, 6, 2)},  # datetime is not a DATE
        {**bench(1.0, AV), "available_at": datetime(2025, 6, 3, 9)},  # naive timestamp
        {**bench(1.0, AV), "fetched_at": datetime(2025, 6, 2, 11)},  # naive row fetched_at
    ]
    for row in bad:
        with pytest.raises(SchemaError):
            w.append([row], T0)
    with pytest.raises(SchemaError):
        w.append([bench(1.0, AV)], datetime(2025, 6, 2, 11))  # naive fetched_at
    assert all_files(tmp_path) == []


def test_bigint_and_nullable_types(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "prices_raw")
    row = {
        "event_date": date(2025, 6, 2),
        "available_at": None,
        "market": "TWSE",
        "stock_id": "2330",
        "open": None,
        "high": None,
        "low": None,
        "close": None,
        "volume_shares": 0,
        "turnover_ntd": 0,
        "trades": 0,
    }
    assert len(w.append([row], T0)) == 1
    assert w.append([row], T0 + timedelta(days=1)) == []
    with pytest.raises(SchemaError):
        w.append([{**row, "stock_id": "2317", "volume_shares": 1.5}], T0)
    with pytest.raises(SchemaError):
        w.append([{**row, "stock_id": "2317", "volume_shares": None}], T0)
    # int is accepted for a DOUBLE column and compares equal to the stored float
    r2 = {**row, "stock_id": "2330", "close": 100}
    assert len(w.append([r2], T0 + timedelta(days=2))) == 1
    assert w.append([{**r2, "close": 100.0}], T0 + timedelta(days=3)) == []


def test_table_without_available_at(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "trading_calendar")
    row = {"event_date": date(2025, 6, 2), "is_trading": True, "source": "finmind"}
    assert len(w.append([row], T0)) == 1
    assert w.append([row], T0 + timedelta(days=1)) == []
    assert len(w.append([{**row, "is_trading": False}], T0 + timedelta(days=2))) == 1


def test_non_event_date_partition(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "universe_membership")
    row = {
        "month_end": date(2025, 5, 30),
        "available_at": datetime(2025, 6, 2, 0, 30, tzinfo=UTC),
        "stock_id": "2330",
        "isin": None,
        "market": "TWSE",
        "rank": 1,
        "market_cap_ntd": 1.0,
        "median_turnover_60d": 2.0,
        "is_watchlist": False,
        "is_benchmark": False,
    }
    (f,) = w.append([row], T0)
    assert f.parent.name == "year=2025"
    assert w.append([row], T0) == []
    # no event_date column: the point-in-time check is skipped (spec section 15.3)
    early = datetime(2025, 5, 1, tzinfo=UTC)
    assert len(w.append([{**row, "stock_id": "2317", "available_at": early}], T0)) == 1


def test_latest_row_read_from_that_years_files_only(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    w.append([bench(1.0, AV, d=date(2024, 6, 3))], T0)
    # Corrupt another year's directory with an unreadable file: it must not be opened.
    other = tmp_path / "clean" / "benchmark_index" / "v1" / "year=2023"
    other.mkdir(parents=True)
    (other / "run-bad.parquet").write_bytes(b"not parquet")
    assert w.append([bench(1.0, AV, d=date(2024, 6, 3))], T0 + timedelta(days=1)) == []


def test_current_version_and_set_current(tmp_path):
    s = S(tmp_path)
    assert current_version(s, "benchmark_index") == 1
    with pytest.raises(FileNotFoundError):
        set_current(s, "benchmark_index", 2)
    assert not paths.current_file(s, "benchmark_index").exists()
    CleanWriter(s, "benchmark_index").append([bench(1.0, AV)], T0)
    CleanWriter(s, "benchmark_index", version=2).append([bench(7.0, AV)], T0)
    set_current(s, "benchmark_index", 2)
    assert current_version(s, "benchmark_index") == 2
    assert paths.current_file(s, "benchmark_index").read_text().strip() == "2"
    # a new default writer targets v2 and compares against v2 only
    w = CleanWriter(s, "benchmark_index")
    assert w.version == 2
    assert w.append([bench(7.0, AV)], T0) == []
    assert len(w.append([bench(1.0, AV)], T0)) == 1
    assert not [
        p
        for p in os.listdir(paths.current_file(s, "benchmark_index").parent)
        if p.startswith("CURRENT.tmp")
    ]


def test_bad_current_file(tmp_path):
    s = S(tmp_path)
    p = paths.current_file(s, "benchmark_index")
    p.parent.mkdir(parents=True)
    p.write_text("abc\n")
    with pytest.raises(ValueError):
        current_version(s, "benchmark_index")


def test_row_fetched_at_wins_and_missing_fetched_at_fails(tmp_path):
    s = S(tmp_path)
    w = CleanWriter(s, "benchmark_index")
    own = T0 - timedelta(days=3)
    (f,) = w.append([{**bench(1.0, AV), "fetched_at": own}, bench(2.0, AV, index_id="B")], T0)
    got = {r["index_id"]: r["fetched_at"] for r in pq.read_table(f).to_pylist()}
    assert got == {"TAIEX_TR": own, "B": T0}
    (g,) = w.append([{**bench(5.0, AV), "fetched_at": own + timedelta(days=1)}])
    assert pq.read_table(g).column("fetched_at").to_pylist() == [own + timedelta(days=1)]
    with pytest.raises(SchemaError):
        w.append([bench(9.0, AV)])


def test_value_columns_exclude_keys_and_first_seen_at():
    from twdata.common.cleanstore import value_columns
    from twdata.common.schema import snapshot_table

    assert value_columns(TABLES["benchmark_index"]) == ["value"]
    assert value_columns(snapshot_table("zz")) == ["snapshot_date", "row_json"] or value_columns(
        snapshot_table("zz")
    ) == ["row_json"]
    assert "first_seen_at" not in value_columns(snapshot_table("zz"))
