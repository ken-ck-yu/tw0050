import json
from datetime import date, timedelta

import pytest
from helpers import DAYS, A, make_world
from world import flat, utc

from twdata.common.config import load_settings
from twdata.research.evaluator import (
    BookError,
    BudgetError,
    DataError,
    HoldoutError,
    TargetBook,
    load_dev_data,
    log,
    run_backtest,
)


def test_holdout_refused(tmp_path):
    s = load_settings(data_dir_override=str(tmp_path / "data"))
    with pytest.raises(HoldoutError):
        load_dev_data(s, date(2024, 1, 2), s.research.dev_end + timedelta(days=1))
    with pytest.raises(HoldoutError):
        load_dev_data(s, date(2025, 1, 2), date(2025, 2, 3))


def test_missing_table_is_data_error(tmp_path):
    s = load_settings(data_dir_override=str(tmp_path / "data"))
    with pytest.raises(DataError):
        load_dev_data(s, date(2023, 1, 2), date(2023, 1, 10))


def test_dev_end_itself_is_allowed(tmp_path):
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, DAYS[:4]))
    w.write()
    s = w.settings()
    data = load_dev_data(s, date(2023, 1, 2), s.research.dev_end)
    assert data.end == s.research.dev_end


def test_loader_drops_rows_after_end(tmp_path):
    w = make_world(tmp_path, 6)
    w.add(A, flat(100.0, DAYS[:6]))
    data = w.load(end=DAYS[3])
    assert max(r["event_date"] for r in data.tables["prices_raw"]) == DAYS[3]
    assert data.calendar.last_day() == DAYS[3]


def test_as_of_cutoff_is_1800_taipei(tmp_path):
    d = DAYS
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, d))
    w.revenue = [
        (A, date(2022, 12, 1), 100, utc(d[1], 17, 59)),
        (A, date(2022, 11, 1), 90, utc(d[1], 18, 0)),
        (A, date(2022, 10, 1), 80, utc(d[1], 18, 1)),
        (A, date(2022, 9, 1), 70, None),
    ]
    data = w.load(end=d[3])
    got = {r["revenue"] for r in data.as_of(d[1]).table("monthly_revenue")}
    assert got == {100, 90}  # 18:00 sharp counts, 18:01 and pending rows do not
    assert {r["revenue"] for r in data.as_of(d[0]).table("monthly_revenue")} == set()
    # prices are visible once their available_at (18:00 of the day) is reached
    assert {r["event_date"] for r in data.as_of(d[1]).table("prices_raw")} >= {d[0], d[1]}
    assert d[2] not in {r["event_date"] for r in data.as_of(d[1]).table("prices_raw")}
    with pytest.raises(DataError):
        data.as_of(d[1]).table("adjusted_prices")


def _data(tmp_path):
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, DAYS[:4]))
    return w.load()


def run(data):
    return run_backtest(
        data, [TargetBook(DAYS[0], {A: 0.1})], card_id="H", params={"k": 1}, window="validation"
    )


def test_log_line_fields(tmp_path, logpath):
    rec = run(_data(tmp_path))
    lines = [json.loads(x) for x in logpath.read_text().splitlines()]
    assert len(lines) == 1
    ln = lines[0]
    assert ln["status"] == "ok" and ln["card_id"] == "H" and ln["params"] == {"k": 1}
    assert ln["run_id"] == rec.run_id and ln["cycle"] == 1 and ln["window"] == "validation"
    assert ln["n_trials"] == 1 and ln["evaluator_sha256"] == log.evaluator_sha256()
    assert ln["params_hash"] == log.params_hash({"k": 1})
    assert "daily" not in ln
    for key in (
        "net_sharpe",
        "benchmark_net_sharpe",
        "deflated_sharpe",
        "annual_turnover",
        "annual_cost_drag",
        "max_drawdown",
        "hit_rate_monthly",
        "unfilled_buys",
        "blocked_sells",
        "dropped_non_tradeable",
        "created_at",
    ):
        assert key in ln


def test_error_line_then_reraise(tmp_path, logpath):
    data = _data(tmp_path)
    with pytest.raises(BookError):
        run_backtest(data, [], card_id="H", params={}, window="validation")
    ln = json.loads(logpath.read_text().splitlines()[0])
    assert ln["status"] == "error" and ln["message"] == "no books"
    assert ln["card_id"] == "H" and ln["cycle"] == 1


def test_budget_error_on_eleventh_run(tmp_path, logpath):
    data = _data(tmp_path)
    for i in range(10):
        assert run(data).n_trials == i + 1
    with pytest.raises(BudgetError):
        run(data)
    assert len(logpath.read_text().splitlines()) == 10  # a refused call writes nothing
    with pytest.raises(BudgetError):
        run(data)


def test_budget_counts_only_current_cycle(tmp_path, logpath):
    logpath.parent.mkdir(parents=True)
    old = [json.dumps({"status": "ok", "cycle": 0, "net_sharpe": 0.1}) for _ in range(10)]
    logpath.write_text("\n".join(old) + "\n")
    rec = run(_data(tmp_path))
    assert rec.n_trials == 11  # all rows count as trials, only the cycle counts for the budget
