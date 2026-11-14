"""stock_info and delistings with the Lead's FinMind fixtures (offline)."""

import json
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from twdata.clients.base import DriftError
from twdata.common import config, views
from twdata.common.cleanstore import CleanWriter, KeyUniquenessError
from twdata.ingest import delistings, stock_info

FIX = Path(__file__).resolve().parents[1] / "fixtures" / "lead" / "finmind"


def fixture(name):
    return json.loads((FIX / name).read_text("utf-8"))["data"]


class Cache:
    def flush(self):
        pass


class Finmind:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def dataset(self, name, start, end=None, data_id=None):
        self.calls.append((name, start, end, data_id))
        return list(self.data)


def make_ctx(tmp_path, data):
    s = config.load_settings(data_dir_override=str(tmp_path))
    return SimpleNamespace(
        settings=s,
        finmind=Finmind(data),
        cache=Cache(),
        writers=lambda t: CleanWriter(s, t),
    )


def read(ctx, table):
    con = duckdb.connect()
    try:
        views.register_views(con, ctx.settings)
        return con.execute(f"SELECT * FROM default_{table} ORDER BY 1, 2").fetchall()
    finally:
        con.close()


def files(ctx, table):
    return list((ctx.settings.data_dir / "clean" / table).rglob("*.parquet"))


@pytest.fixture
def s6():
    return None


def test_stock_info_mapping_and_rerun(tmp_path, s6):
    data = fixture("TaiwanStockInfo_trimmed.json")
    ctx = make_ctx(tmp_path, data)
    stock_info.run(ctx, date(2015, 6, 1), date(2016, 1, 1))
    assert ctx.finmind.calls[0][0] == "TaiwanStockInfo"
    rows = read(ctx, "stock_info")
    assert len(rows) == len(data)
    src = data[0]  # column order: event_date, fetched_at, stock_id, stock_name, ...
    got = [r for r in rows if r[2] == src["stock_id"]][0]
    assert got[0] == date.fromisoformat(src["date"])
    assert got[3] == src["stock_name"] and got[4] == src["industry_category"]
    assert got[5] == src["type"] == "tpex"
    n = len(files(ctx, "stock_info"))
    stock_info.run(ctx, date(2015, 6, 1), date(2016, 1, 1))
    assert len(files(ctx, "stock_info")) == n
    assert not stock_info.duplicates_path(ctx.settings).exists()
    assert ctx.finmind.calls[0][1:] == (date(2000, 1, 1), None, None)


def test_delistings_mapping(tmp_path, s6):
    data = fixture("TaiwanStockDelisting_trimmed.json")
    ctx = make_ctx(tmp_path, data)
    delistings.run(ctx, date(2015, 6, 1), date(2016, 1, 1))
    assert ctx.finmind.calls[0][0] == "TaiwanStockDelisting"
    rows = read(ctx, "delistings")
    assert len(rows) == len(data)
    src = data[0]
    got = [r for r in rows if r[2] == src["stock_id"]][0]
    assert got[0] == date.fromisoformat(src["date"]) and got[3] == src["stock_name"]
    n = len(files(ctx, "delistings"))
    delistings.run(ctx, date(2015, 6, 1), date(2016, 1, 1))
    assert len(files(ctx, "delistings")) == n


def test_duplicate_key_is_logged_to_s6_and_stops(tmp_path, s6):
    data = fixture("TaiwanStockInfo_trimmed.json")
    ctx = make_ctx(tmp_path, data + [dict(data[0], stock_name="other")])
    with pytest.raises(KeyUniquenessError):
        stock_info.run(ctx, date(2015, 6, 1), date(2016, 1, 1))
    doc = json.loads(stock_info.duplicates_path(ctx.settings).read_text("utf-8"))
    assert [data[0]["stock_id"], data[0]["date"]] in doc["stock_info"]["keys"]
    assert files(ctx, "stock_info") == []
    d = fixture("TaiwanStockDelisting_trimmed.json")
    ctx = make_ctx(tmp_path, d + [d[0]])
    with pytest.raises(KeyUniquenessError):
        delistings.run(ctx, date(2015, 6, 1), date(2016, 1, 1))
    doc = json.loads(stock_info.duplicates_path(ctx.settings).read_text("utf-8"))
    assert "delistings" in doc


def test_column_drift_and_bad_dates_are_skipped(tmp_path, s6):
    data = fixture("TaiwanStockInfo_trimmed.json")
    with pytest.raises(DriftError):
        stock_info.run(make_ctx(tmp_path, [dict(data[0], extra="x")]), date(2015, 6, 1), None)
    ctx = make_ctx(
        tmp_path / "b",
        [
            dict(data[0], date="soon"),
            dict(data[1], date=None),
            dict(data[2], industry_category=None),
        ],
    )
    stock_info.SKIPPED.clear()
    stock_info.run(ctx, date(2015, 6, 1), None)
    assert stock_info.SKIPPED == {"stock_info": 2}
    rows = read(ctx, "stock_info")
    assert len(rows) == 1 and rows[0][4] == ""  # null industry_category becomes ''
    with pytest.raises(DriftError):
        delistings.run(make_ctx(tmp_path, [{"date": "2018-01-02"}]), date(2015, 6, 1), None)


def test_registries():
    assert set(stock_info.DATASETS) == {"stock_info"}
    assert set(delistings.DATASETS) == {"delistings"}
