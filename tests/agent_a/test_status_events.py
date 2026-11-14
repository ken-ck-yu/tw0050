"""status_events: disposition mapping, chtm runs, resume, rerun (offline, no network)."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pytest

from twdata.clients.base import DriftError, Response
from twdata.common import config, views
from twdata.common.cleanstore import CleanWriter
from twdata.common.parsing import ParseError
from twdata.common.timeutil import at
from twdata.common.tradingcal import TradingCalendar
from twdata.ingest import status_events as se

FIX = Path(__file__).resolve().parents[1] / "fixtures"
FETCHED = datetime(2026, 11, 14, 3, 0, tzinfo=UTC)


def weekdays(a: date, b: date) -> list[date]:
    out, d = [], a
    while d <= b:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


CAL = TradingCalendar(weekdays(date(2015, 1, 1), date(2021, 12, 31)))


def resp(fields, rows) -> Response:
    return Response("ok", rows, b"", None, fields=fields, fetched_at=FETCHED)


def twse_punish_resp() -> Response:
    d = json.loads((FIX / "agent_a" / "twse_punish_2015_trimmed.json").read_text("utf-8"))
    return resp(d["fields"], d["data"])


def tpex_disposal_resp() -> Response:
    d = json.loads((FIX / "agent_a" / "tpex_disposal_2015_trimmed.json").read_text("utf-8"))
    t = d["tables"][0]
    return resp(t["fields"], t["data"])


def chtm_resp(day_rows) -> Response:
    d = json.loads((FIX / "lead" / "tpex" / "chtm_20200615.json").read_text("utf-8"))
    return resp(d["tables"][0]["fields"], day_rows)


def chtm_row(code, *flags, halt=False):
    chg, split, mgmt = (flags + ("", "", ""))[:3]
    return [code, "名", chg, split, mgmt, "", "Ｙ" if halt else "", "", "", ""]


def test_parse_range_both_tildes_and_errors():
    assert se.parse_roc_range("104/09/25～104/10/12") == (date(2015, 9, 25), date(2015, 10, 12))
    assert se.parse_roc_range("104/06/30~104/07/13") == (date(2015, 6, 30), date(2015, 7, 13))
    for bad in ("", "104/06/30", "104/06/30-104/07/13", "abc~def", "104/07/13~104/06/30"):
        with pytest.raises(ParseError):
            se.parse_roc_range(bad)


def test_twse_punish_fixture_mapping():
    r = twse_punish_resp()
    rows = se.disposition_rows(
        "TWSE",
        r.records,
        range_key="處置起迄時間",
        detail_key="處置措施",
        cal=CAL,
        fetched_at=FETCHED,
    )
    first = rows[0]
    assert first["stock_id"] == "0080" and first["market"] == "TWSE"
    assert first["status_type"] == "disposition"
    assert first["announce_date"] == date(2015, 9, 24) == first["event_date"]
    assert (first["start_date"], first["end_date"]) == (date(2015, 9, 25), date(2015, 10, 12))
    assert first["detail"] == "督導會報決議"
    assert first["available_at"] == at(date(2015, 9, 25), 8, 30)  # Thursday to Friday
    assert first["fetched_at"] == FETCHED
    assert "05297P" in {x["stock_id"] for x in rows}  # non-common codes are kept


def test_tpex_disposal_fixture_mapping_skips_blank_rows():
    r = tpex_disposal_resp()
    assert sum(1 for x in r.records if not x["證券代號"]) == 2
    rows = se.disposition_rows(
        "TPEx",
        r.records,
        range_key="處置起訖時間",
        detail_key="處置原因",
        cal=CAL,
        fetched_at=FETCHED,
    )
    assert len(rows) == 10
    first = rows[0]
    assert first["stock_id"] == "4703" and first["market"] == "TPEx"
    assert (first["start_date"], first["end_date"]) == (date(2015, 6, 30), date(2015, 7, 13))
    assert first["announce_date"] == date(2015, 6, 29)
    assert first["detail"] == "連續3個營業日"
    assert first["available_at"] == at(date(2015, 6, 30), 8, 30)


def test_duplicate_key_keeps_first_row():
    fields = ["公布日期", "證券代號", "處置起迄時間", "處置措施"]
    rows = [
        ["104/09/20", "1234", "104/09/25～104/10/05", "a"],
        ["104/09/24", "1234", "104/09/25～104/10/12", "b"],
    ]
    out = se.disposition_rows(
        "TWSE",
        resp(fields, rows).records,
        range_key="處置起迄時間",
        detail_key="處置措施",
        cal=CAL,
        fetched_at=FETCHED,
    )
    assert len(out) == 1 and out[0]["detail"] == "a" and out[0]["end_date"] == date(2015, 10, 5)


def test_unparseable_range_and_missing_field():
    fields = ["公布日期", "證券代號", "處置起迄時間", "處置措施"]
    with pytest.raises(ParseError):
        se.disposition_rows(
            "TWSE",
            resp(fields, [["104/09/24", "1234", "soon", "x"]]).records,
            range_key="處置起迄時間",
            detail_key="處置措施",
            cal=CAL,
            fetched_at=FETCHED,
        )
    with pytest.raises(DriftError):
        se.disposition_rows(
            "TWSE",
            resp(["公布日期"], [["104/09/24"]]).records,
            range_key="處置起迄時間",
            detail_key="處置措施",
            cal=CAL,
            fetched_at=FETCHED,
        )


def test_available_at_pending_past_calendar():
    short = TradingCalendar([date(2015, 9, 24)])
    fields = ["公布日期", "證券代號", "處置起迄時間", "處置措施"]
    out = se.disposition_rows(
        "TWSE",
        resp(fields, [["104/09/24", "1234", "104/09/25～104/10/12", "x"]]).records,
        range_key="處置起迄時間",
        detail_key="處置措施",
        cal=short,
        fetched_at=FETCHED,
    )
    assert out[0]["available_at"] is None


# ---- chtm runs ----------------------------------------------------------------------


def day_recs(spec: dict) -> dict:
    return {
        d: [dict(zip(["證券代號", *se.CHTM_FLAGS], [c, *f], strict=True)) for c, f in rs]
        for d, rs in spec.items()
    }


def test_chtm_runs_consecutive_gap_and_flags():
    days = weekdays(date(2020, 6, 15), date(2020, 6, 24))  # 8 days
    spec = {
        days[0]: [("2719", ("Ｙ", "", "")), ("3064", ("", "Ｙ", ""))],
        days[1]: [("2719", ("Ｙ", "Ｙ", ""))],
        days[2]: [],
        days[3]: [("2719", ("", "", "Ｙ"))],
        days[4]: [("2719", ("", "", "Ｙ")), ("9999", ("", "", " "))],  # blank-ish flag ignored
    }
    runs = {(r["stock_id"], r["start_date"]): r for r in se.chtm_runs(days, day_recs(spec))}
    assert set(runs) == {("2719", days[0]), ("3064", days[0]), ("2719", days[3])}
    assert runs[("2719", days[0])]["end_date"] == days[1]
    assert runs[("2719", days[0])]["detail"] is None
    assert runs[("2719", days[3])]["end_date"] == days[4]  # open at the end of the range
    assert runs[("3064", days[0])]["end_date"] == days[0]


def test_chtm_seed_extended_or_untouched():
    days = weekdays(date(2020, 6, 22), date(2020, 6, 23))
    seeds = {"2719": (date(2020, 6, 10), None), "3064": (date(2020, 6, 18), None)}
    spec = {days[0]: [("2719", ("Ｙ", "", ""))], days[1]: [("2719", ("Ｙ", "", ""))]}
    runs = se.chtm_runs(days, day_recs(spec), seeds)
    assert runs == [
        {
            "stock_id": "2719",
            "start_date": date(2020, 6, 10),
            "end_date": days[1],
            "detail": None,
            "fetched_at": None,
        }
    ]


# ---- run() against fakes and a real CleanWriter ---------------------------------------


class FakeCache:
    def __init__(self):
        self.flushes = 0

    def flush(self):
        self.flushes += 1


def make_ctx(tmp_path, *, chtm_by_day=None, calendar=CAL):
    settings = config.load_settings(data_dir_override=str(tmp_path))
    calls = []
    chtm_by_day = chtm_by_day or {}

    def chtm(d, allow_empty=False):
        assert allow_empty is True
        calls.append(d)
        r = chtm_resp(chtm_by_day.get(d, []))
        return r.records, r

    def punish(s, e):
        calls.append(("punish", s, e))
        r = twse_punish_resp()
        return r.records, r

    def disposal(s, e):
        calls.append(("disposal", s, e))
        r = tpex_disposal_resp()
        return r.records, r

    ctx = SimpleNamespace(
        settings=settings,
        calendar=calendar,
        twse=SimpleNamespace(punish=punish),
        tpex=SimpleNamespace(chtm=chtm, disposal=disposal),
        finmind=None,
        cache=FakeCache(),
        writers=lambda t: CleanWriter(settings, t),
    )
    return ctx, calls


def read_events(ctx):
    con = duckdb.connect()
    try:
        assert "status_events" in views.register_views(con, ctx.settings)
        return con.execute(
            "SELECT market, stock_id, status_type, announce_date, start_date, end_date, detail, "
            "event_date, available_at FROM default_status_events ORDER BY 1, 2, 3, 5"
        ).fetchall()
    finally:
        con.close()


def parquet_files(ctx) -> list[Path]:
    return sorted((ctx.settings.data_dir / "clean" / "status_events").rglob("*.parquet"))


def test_run_dispositions_calendar_years_and_rerun(tmp_path):
    ctx, calls = make_ctx(tmp_path)
    se.run_dispositions(ctx, date(2015, 6, 1), date(2016, 3, 31))
    assert ("punish", date(2015, 6, 1), date(2015, 12, 31)) in calls
    assert ("disposal", date(2016, 1, 1), date(2016, 3, 31)) in calls
    ev = read_events(ctx)
    assert {e[0] for e in ev} == {"TWSE", "TPEx"}
    assert all(e[2] == "disposition" for e in ev)
    n = len(parquet_files(ctx))
    se.run_dispositions(ctx, date(2015, 6, 1), date(2016, 3, 31))
    assert len(parquet_files(ctx)) == n  # identical rows are skipped


def test_run_changed_trading_runs_resume_and_rerun(tmp_path):
    d = weekdays(date(2020, 6, 15), date(2020, 6, 26))  # two weeks
    by_day = {
        d[0]: [chtm_row("2719", "Ｙ"), chtm_row("1333", halt=True)],  # halt only: ignored
        d[1]: [chtm_row("2719", "Ｙ")],
        d[2]: [chtm_row("3064", "", "Ｙ")],
        d[3]: [chtm_row("3064", "", "Ｙ")],
        d[4]: [chtm_row("3064", "", "Ｙ")],
        d[5]: [chtm_row("3064", "", "Ｙ")],  # continues into the second week
        d[6]: [chtm_row("3064", "", "Ｙ")],
    }
    ctx, calls = make_ctx(tmp_path, chtm_by_day=by_day)
    se.run_changed_trading(ctx, d[0], d[4])
    ev = {(e[1], e[4]): e for e in read_events(ctx)}
    assert set(ev) == {("2719", d[0]), ("3064", d[2])}
    e = ev[("2719", d[0])]
    assert e[2] == "changed_trading" and e[0] == "TPEx" and e[3] is None
    assert (e[5], e[7]) == (d[1], d[0])  # end_date, event_date = start_date
    assert e[8] == at(d[1], 8, 30)  # next trading day after the first day, 08:30
    assert ev[("3064", d[2])][5] == d[4]  # open at the end of the range
    assert ev[("3064", d[2])][6] is None
    # second range: the open run of 3064 is read back and extended, start_date stays
    se.run_changed_trading(ctx, d[5], d[9])
    ev = {(e[1], e[4]): e for e in read_events(ctx)}
    assert set(ev) == {("2719", d[0]), ("3064", d[2])}
    assert ev[("3064", d[2])][5] == d[6]
    # rerun of both ranges: nothing is fetched again and no new file appears
    n, before = len(parquet_files(ctx)), len(calls)
    se.run_changed_trading(ctx, d[0], d[9])
    assert len(calls) == before and len(parquet_files(ctx)) == n


def test_first_day_of_range_is_the_start_date(tmp_path):
    d = weekdays(date(2020, 6, 15), date(2020, 6, 17))
    by_day = {x: [chtm_row("2719", "Ｙ")] for x in d}
    ctx, _ = make_ctx(tmp_path, chtm_by_day=by_day)
    se.run_changed_trading(ctx, d[1], d[2])  # state already present on the first day
    ev = read_events(ctx)
    assert len(ev) == 1 and ev[0][4] == d[1]


def test_chtm_field_drift(tmp_path):
    ctx, _ = make_ctx(tmp_path)
    ctx.tpex.chtm = lambda d, allow_empty=False: ([{"證券代號": "1"}], resp(["證券代號"], [["1"]]))
    with pytest.raises(DriftError):
        se.run_changed_trading(ctx, date(2020, 6, 15), date(2020, 6, 15))


def test_datasets_registry():
    assert set(se.DATASETS) == {"status_events"}
