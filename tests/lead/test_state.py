import json
from datetime import date

from twdata.common import config, paths, state
from twdata.common.tradingcal import TradingCalendar


def S(tmp_path):
    return config.load_settings(data_dir_override=str(tmp_path))


def test_merge_adjacent_ranges(tmp_path):
    s = S(tmp_path)
    state.mark_dates(s, "d", date(2025, 6, 2), date(2025, 6, 4), shards=["a"])
    state.mark_dates(s, "d", date(2025, 6, 5), date(2025, 6, 6), shards=["b"])
    state.mark_dates(s, "d", date(2025, 6, 20), date(2025, 6, 20))
    doc = state.load(s, "d")
    assert doc["completed"] == [["2025-06-02", "2025-06-06"], ["2025-06-20", "2025-06-20"]]
    assert doc["shards"] == ["a", "b"]
    assert state.is_done(s, "d", date(2025, 6, 3)) and not state.is_done(s, "d", date(2025, 6, 10))


def test_missing_against_calendar(tmp_path):
    s = S(tmp_path)
    cal = TradingCalendar([date(2025, 6, 2), date(2025, 6, 3), date(2025, 6, 4)])
    state.mark_dates(s, "d", date(2025, 6, 2), date(2025, 6, 3))
    assert state.missing(s, "d", date(2025, 6, 2), date(2025, 6, 4), cal) == [date(2025, 6, 4)]


def test_stocks_and_atomic_write(tmp_path):
    s = S(tmp_path)
    state.mark_stocks(s, "p", ["2330", "2317"])
    state.mark_stocks(s, "p", ["2330", "2454"])
    assert state.load(s, "p")["completed"] == ["2317", "2330", "2454"]
    # a leftover temp file from a crashed write must not replace the good file
    p = paths.state_file(s, "p")
    p.with_suffix(".json.tmp999").write_text("{broken", encoding="utf-8")
    assert json.loads(p.read_text(encoding="utf-8"))["completed"] == ["2317", "2330", "2454"]
    assert len(state.entries(s)) == 1
