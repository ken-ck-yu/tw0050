import json
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

from a1_helpers import daily_routes, make_ctx  # noqa: E402

from twdata.common import paths, schema, state  # noqa: E402
from twdata.common.tradingcal import TradingCalendar  # noqa: E402
from twdata.ingest import daily_official  # noqa: E402
from twdata.ingest import trading_calendar_derived as tcd

D1, D2, D3 = date(2016, 6, 1), date(2016, 6, 2), date(2016, 6, 3)


@pytest.fixture(autouse=True)
def clean_eras(monkeypatch):
    monkeypatch.setattr(schema, "ERAS", {})


def test_no_datasets():
    assert tcd.DATASETS == {}


def test_diff_lists_one_sided_days_and_writes_file(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, daily_routes(), [D1, D2])
    daily_official.run(ctx, D1, D2)
    # the FinMind calendar has 06-03 (no prices) and lacks 06-02 (prices exist)
    ctx.calendar = TradingCalendar([D1, D3])
    result = tcd.diff(ctx, D1, D3)
    assert result == {"finmind_only": ["2016-06-03"], "derived_only": ["2016-06-02"]}
    doc = json.loads(paths.state_file(ctx.settings, "calendar_diff").read_text(encoding="utf-8"))
    assert doc["finmind_only"] == ["2016-06-03"] and doc["derived_only"] == ["2016-06-02"]
    assert (doc["start"], doc["end"]) == ("2016-06-01", "2016-06-03")
    # the file is also a valid state document: `status` can list every file in data/state
    assert any(e["dataset"] == "calendar_diff" for e in state.entries(ctx.settings))


def test_diff_agreeing_calendars_and_no_data(tmp_path):
    ctx, _, _ = make_ctx(tmp_path, daily_routes(), [D1, D2])
    assert tcd.diff(ctx, D1, D2) == {
        "finmind_only": ["2016-06-01", "2016-06-02"],
        "derived_only": [],
    }
    daily_official.run(ctx, D1, D2)
    assert tcd.diff(ctx, D1, D2) == {"finmind_only": [], "derived_only": []}
    # the range limits both sides
    assert tcd.diff(ctx, D2, D2) == {"finmind_only": [], "derived_only": []}
