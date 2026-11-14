import json
from datetime import date, datetime

import pytest
from helpers_b import LEAD, Router, fixture_bytes, make_ctx, query

from twdata.clients.base import DriftError, unique_field_names
from twdata.common import state
from twdata.common.timeutil import TAIPEI
from twdata.ingest import benchmark as bm

D = date(2016, 6, 1)


class FakeFinMind:
    def __init__(self, data):
        self.data = data
        self.calls = []

    def dataset(self, name, start, end=None, data_id=None):
        self.calls.append((name, start, end, data_id))
        return self.data


def mi_router():
    return Router().add("afterTrading/MI_INDEX", fixture_bytes("twse/mi_index_20160601.json"))


def rows(tmp_path):
    return query(tmp_path, "SELECT * FROM default_benchmark_index ORDER BY index_id, event_date")


def test_twse_rows_from_the_index_table(tmp_path):
    r = mi_router()
    ctx = make_ctx(tmp_path, r)
    bm.run(ctx, D, D)
    got = {x["index_id"]: x for x in rows(tmp_path)}
    assert set(got) == {"TAIEX_TR", "TAIWAN50_TR"}  # no FinMind client: TPEX_TR skipped
    assert got["TAIEX_TR"]["value"] == 13609.60
    assert got["TAIWAN50_TR"]["value"] == 10212.75
    assert got["TAIEX_TR"]["event_date"] == D
    assert got["TAIEX_TR"]["available_at"].astimezone(TAIPEI) == datetime(
        2016, 6, 1, 18, 0, tzinfo=TAIPEI
    )
    assert state.is_done(ctx.settings, "benchmark_index", D)
    assert r.count("MI_INDEX") == 1


def test_index_table_field_names_and_selection():
    d = json.loads((LEAD / "twse/mi_index_20160601.json").read_text(encoding="utf-8"))
    tbl = [t for t in d["tables"] if "報酬指數" in t.get("title", "")][0]
    names = unique_field_names(tbl["fields"])
    assert names[:2] == ["報酬指數", "收盤指數"]


def test_missing_index_row_is_drift():
    recs = [{"報酬指數": "發行量加權股價報酬指數", "收盤指數": "1,000.00"}]
    with pytest.raises(DriftError):
        bm.twse_rows(recs, D, datetime(2016, 6, 1, tzinfo=TAIPEI))


def test_unparseable_value_is_drift():
    recs = [
        {"報酬指數": "發行量加權股價報酬指數", "收盤指數": "--"},
        {"報酬指數": "臺灣50報酬指數", "收盤指數": "1.00"},
    ]
    with pytest.raises(DriftError):
        bm.twse_rows(recs, D, datetime(2016, 6, 1, tzinfo=TAIPEI))


def test_tpex_tr_from_finmind(tmp_path):
    data = json.loads(
        (LEAD / "finmind/TaiwanStockTotalReturnIndex_TAIEX_trimmed.json").read_text("utf-8")
    )["data"]
    data = [{**x, "stock_id": "TPEx"} for x in data]  # data_id substituted
    fm = FakeFinMind(data)
    r = Router().add("afterTrading/MI_INDEX", fixture_bytes("twse/mi_index_20160601.json"))
    ctx = make_ctx(tmp_path, r, finmind=fm)
    bm.run(ctx, D, D)
    assert fm.calls == [("TaiwanStockTotalReturnIndex", D, D, "TPEx")]
    got = [x for x in rows(tmp_path) if x["index_id"] == "TPEX_TR"]
    assert [(x["event_date"], x["value"]) for x in got] == [
        (date(2025, 6, 2), 46569.74),
        (date(2025, 6, 3), 46856.93),
        (date(2025, 6, 4), 47947.73),
        (date(2025, 6, 5), 48072.81),
        (date(2025, 6, 6), 48042.29),
    ]
    assert got[0]["available_at"].astimezone(TAIPEI) == datetime(2025, 6, 2, 18, 0, tzinfo=TAIPEI)


def test_tpex_tr_year_chunks(tmp_path):
    fm = FakeFinMind([])
    ctx = make_ctx(tmp_path, Router(), finmind=fm)
    bm.run_tpex(ctx, date(2015, 6, 1), date(2017, 2, 1))
    assert [(c[1], c[2]) for c in fm.calls] == [
        (date(2015, 6, 1), date(2015, 12, 31)),
        (date(2016, 1, 1), date(2016, 12, 31)),
        (date(2017, 1, 1), date(2017, 2, 1)),
    ]


def test_rerun_is_idempotent(tmp_path):
    r = mi_router()
    ctx = make_ctx(tmp_path, r)
    bm.run(ctx, D, D)
    files = sorted(tmp_path.rglob("*.parquet"))
    bm.run(ctx, D, D)
    assert sorted(tmp_path.rglob("*.parquet")) == files and r.count("MI_INDEX") == 1
