"""H1 strategy tests on synthetic Parquet data (offline)."""

from __future__ import annotations

import json
import math
from datetime import date

import pytest
from h1_world import World, month_add, utc, weekdays

import twdata.research.strategies.revenue_drift as h1
from twdata.research.evaluator import DataError, TargetBook
from twdata.research.strategies.revenue_drift import (
    build_books,
    decision_dates,
    diagnostics,
    run_h1,
    select_book,
)

V_START, V_END = date(2022, 1, 1), date(2024, 6, 30)
DAYS = weekdays(date(2021, 12, 1), 110)  # to early May 2022, no holidays
IDS = [f"{1001 + i}" for i in range(30)]


def flat_prices(world, sid, level=100.0):
    world.prices[sid] = {d: (level, level) for d in DAYS}


def add_history(world, sid, yoy, first=date(2020, 12, 1), last=date(2022, 3, 1)):
    """Revenue for every month from `first` to `last`: 100 a year ago, 100*(1+yoy) now."""
    m = first
    while m <= last:
        recent = m >= date(2021, 12, 1)
        world.add_revenue(sid, m, round(100 * (1 + yoy)) if recent else 100)
        m = month_add(m, 1)


def small_world(tmp_path, yoys: dict, bench=("0050",)):
    w = World(tmp_path, DAYS)
    for sid, y in yoys.items():
        flat_prices(w, sid)
        add_history(w, sid, y)
    for b in bench:
        flat_prices(w, b)
    w.set_universe(date(2021, 11, 30), list(yoys), bench=bench)
    return w


# ------------------------------------------------------------ decision dates


def test_decision_date_weekend_rolls_to_monday(tmp_path):
    w = small_world(tmp_path, {"1111": 0.5})
    data = w.load(V_START, V_END)
    ds = decision_dates(data, V_START, V_END)
    # 2022-01-10 Mon, 02-10 Thu, 03-10 Thu, 04-10 is a Sunday -> Mon 04-11. No May: the
    # calendar ends 2022-05-05 so 05-10 has no trading day.
    assert ds == [date(2022, 1, 10), date(2022, 2, 10), date(2022, 3, 10), date(2022, 4, 11)]


def test_decision_date_respects_start_and_end(tmp_path):
    w = small_world(tmp_path, {"1111": 0.5})
    data = w.load(V_START, V_END)
    assert decision_dates(data, date(2022, 2, 11), V_END) == [date(2022, 3, 10), date(2022, 4, 11)]
    assert decision_dates(data, V_START, date(2022, 2, 9)) == [date(2022, 1, 10)]
    assert decision_dates(data, V_START, date(2022, 2, 10)) == [
        date(2022, 1, 10),
        date(2022, 2, 10),
    ]


# ------------------------------------------------------------ visibility


def test_revenue_published_after_cutoff_is_not_used(tmp_path):
    w = small_world(tmp_path, {"1111": 0.2, "2222": 0.3})
    # replace the Dec 2021 row of 2222 by one that arrives at 18:01 on the decision date
    w.revenue = [r for r in w.revenue if not (r[0] == "2222" and r[1] == date(2021, 12, 1))]
    w.add_revenue("2222", date(2021, 12, 1), 10_000, available_at=utc(date(2022, 1, 10), 18, 1))
    data = w.load(V_START, V_END)
    visible = data.as_of(date(2022, 1, 10))
    assert not [r for r in visible.table("monthly_revenue") if r["revenue"] == 10_000]
    # 2222 has no visible Dec 2021 row on Jan 10, so only 1111 is eligible
    jan = [b for b in build_books(data, V_START, V_END) if b.decision_date == date(2022, 1, 10)][0]
    assert jan.weights == {"1111": 0.1}
    # the next month (cutoff after 18:01 on Jan 10) sees it; Jan 2022 data is unaffected
    feb = [b for b in build_books(data, V_START, V_END) if b.decision_date == date(2022, 2, 10)][0]
    assert set(feb.weights) == {"2222"}  # 2 stocks, k=1, best yoy of Jan (0.3)


def test_revenue_exactly_at_cutoff_is_used(tmp_path):
    w = small_world(tmp_path, {"1111": 0.2})
    w.revenue = [r for r in w.revenue if not (r[1] == date(2021, 12, 1))]
    w.add_revenue("1111", date(2021, 12, 1), 150, available_at=utc(date(2022, 1, 10), 18, 0))
    data = w.load(V_START, V_END)
    jan = build_books(data, V_START, V_END)[0]
    assert jan.weights == {"1111": 0.1}


# ------------------------------------------------------------ yoy and eligibility


def test_yoy_uses_year_ago_month_and_ranks(tmp_path):
    w = World(tmp_path, DAYS)
    ids = [f"{2000 + i}" for i in range(10)]
    for i, sid in enumerate(ids):
        flat_prices(w, sid)
        add_history(w, sid, 0.01 * i)
    flat_prices(w, "0050")
    w.set_universe(date(2021, 11, 30), ids, bench=["0050"])
    # a different yoy for Dec 2021 vs Dec 2020 on stock 2003 only, so that wrong month
    # arithmetic (m-11, m-13) would change the answer
    w.revenue = [r for r in w.revenue if not (r[0] == "2003" and r[1] == date(2021, 12, 1))]
    w.add_revenue("2003", date(2021, 12, 1), 1000)
    w.add_revenue("2003", date(2021, 11, 1), 1)
    w.add_revenue("2003", date(2020, 11, 1), 1)
    w.add_revenue("2003", date(2021, 1, 1), 1)
    data = w.load(V_START, V_END)
    jan = build_books(data, V_START, V_END)[0]
    assert jan.weights == {"2003": 0.1}  # yoy 9.0 beats 0.09 of 2009; k = 1 of 10


def test_eligibility_requires_both_months_and_positive_base(tmp_path):
    ids = ["1001", "1002", "1003", "1004", "1005"]
    w = small_world(tmp_path, dict.fromkeys(ids, 0.1))
    # 1001 has no year-ago month, 1002 zero base, 1003 negative base, 1004 no current month
    drop = {
        ("1001", date(2020, 12, 1)),
        ("1002", date(2020, 12, 1)),
        ("1003", date(2020, 12, 1)),
        ("1004", date(2021, 12, 1)),
    }
    w.revenue = [r for r in w.revenue if (r[0], r[1]) not in drop]
    w.add_revenue("1002", date(2020, 12, 1), 0)
    w.add_revenue("1003", date(2020, 12, 1), -50)
    # make the ineligible ones look best if they were counted
    w.add_revenue("1001", date(2021, 12, 1), 10**6)
    data = w.load(V_START, V_END)
    visible = data.as_of(date(2022, 1, 10))
    scores = h1._yoy_scores(visible, h1._universe(visible), date(2022, 1, 10))
    assert set(scores) == {"1005"}
    assert scores["1005"] == pytest.approx(0.1)


def test_restated_revenue_row_latest_visible_wins(tmp_path):
    w = small_world(tmp_path, {"1111": 0.1})
    w.add_revenue("1111", date(2021, 12, 1), 300, available_at=utc(date(2022, 1, 5)))
    data = w.load(V_START, V_END)
    visible = data.as_of(date(2022, 1, 10))
    sc = h1._yoy_scores(visible, ["1111"], date(2022, 1, 10))
    assert sc["1111"] == pytest.approx(0.1)  # the 10th 18:00 row (110) is the later one


# ------------------------------------------------------------ selection


def test_select_book_top_decile_weights():
    scores = {f"{1000 + i}": float(i) for i in range(100)}
    book = select_book(scores)
    assert len(book) == 10
    assert set(book) == {f"{1000 + i}" for i in range(90, 100)}
    assert all(w == 0.1 for w in book.values())


def test_select_book_ceil_and_exact_float_boundary():
    # 0.10 * 30 is 3.0000000000000004 in floating point; ceil must still give 3
    assert len(select_book({f"{1000 + i}": float(i) for i in range(30)})) == 3
    assert len(select_book({f"{1000 + i}": float(i) for i in range(31)})) == 4
    assert len(select_book({f"{1000 + i}": float(i) for i in range(101)})) == 11


def test_select_book_weight_cap_and_cash_below_ten_names():
    book = select_book({"1001": 0.5, "1002": 0.1, "1003": 0.2})
    assert book == {"1001": 0.1}  # k=1, 1/k capped at 0.10, the rest is cash
    book = select_book({f"{1000 + i}": float(i) for i in range(50)})
    assert len(book) == 5 and sum(book.values()) == pytest.approx(0.5)
    big = select_book({f"{1000 + i}": float(i) for i in range(200)})
    assert len(big) == 20
    assert all(w == pytest.approx(0.05) for w in big.values())  # 1/k below the cap


def test_select_book_ties_prefer_lower_stock_id():
    scores = {"1005": 1.0, "1003": 1.0, "1004": 1.0, "1001": 0.0}
    scores.update({f"{2000 + i}": -1.0 for i in range(16)})  # n = 20 so k = 2
    assert set(select_book(scores)) == {"1003", "1004"}


def test_select_book_empty_is_cash():
    assert select_book({}) == {}


def test_empty_universe_gives_empty_books(tmp_path):
    w = World(tmp_path, DAYS)
    flat_prices(w, "0050")
    w.set_universe(date(2021, 11, 30), [], bench=["0050"])
    data = w.load(V_START, V_END)
    books = build_books(data, V_START, V_END)
    assert len(books) == 4 and all(b.weights == {} for b in books)


def test_no_visible_universe_gives_empty_books(tmp_path):
    w = small_world(tmp_path, {"1111": 0.5})
    w.members = {}
    w.set_universe(date(2021, 11, 30), ["1111"], available_at=utc(date(2022, 6, 1)))
    data = w.load(V_START, V_END)
    assert all(b.weights == {} for b in build_books(data, V_START, V_END))


def test_benchmark_rows_excluded_watchlist_allowed(tmp_path):
    w = small_world(tmp_path, {"1111": 0.1})
    flat_prices(w, "1112")
    add_history(w, "1112", 0.2)
    flat_prices(w, "0050")
    add_history(w, "0050", 5.0)
    w.members = {}
    w.set_universe(date(2021, 11, 30), ["1111", "1112"], bench=["0050"], watch=["1112"])
    data = w.load(V_START, V_END)
    visible = data.as_of(date(2022, 1, 10))
    assert h1._universe(visible) == ["1111", "1112"]
    jan = build_books(data, V_START, V_END)[0]
    assert jan.weights == {"1112": 0.1}  # watchlist stock allowed, benchmark 0050 never


def test_latest_visible_month_end_is_the_universe(tmp_path):
    w = small_world(tmp_path, {"1111": 0.1, "1112": 0.9})
    # from 2021-12-31 the universe only holds 1111 (1112 dropped out)
    w.set_universe(date(2021, 12, 31), ["1111"], bench=["0050"])
    data = w.load(V_START, V_END)
    jan = build_books(data, V_START, V_END)[0]
    assert jan.weights == {"1111": 0.1}


# ------------------------------------------------------------ diagnostics


def test_diagnostics_hand_computed(tmp_path):
    days = weekdays(date(2022, 1, 3), 8)  # Jan 3..12
    w = World(tmp_path, days)
    d = {x: i for i, x in enumerate(days)}
    # opens at E1 = Jan 4, E2 = Jan 6, E3 = Jan 10
    e1, e2, e3 = date(2022, 1, 4), date(2022, 1, 6), date(2022, 1, 10)
    opens = {
        "1001": (100, 110, 110),
        "1002": (100, 120, 108),
        "1003": (100, 90, 99),
        "1004": (100, 100, 105),
        "0050": (100, 500, 500),  # benchmark: excluded from the universe median
    }
    for sid, (o1, o2, o3) in opens.items():
        w.prices[sid] = {}
        for x in days:
            o = {e1: o1, e2: o2, e3: o3}.get(x, 100.0 if d[x] < d[e1] else o1)
            w.prices[sid][x] = (float(o), float(o))
    w.set_universe(date(2021, 12, 31), ["1001", "1002", "1003", "1004"], bench=["0050"])
    data = w.load(date(2022, 1, 1), date(2022, 1, 31))
    books = [
        TargetBook(date(2022, 1, 3), {"1001": 0.1, "1002": 0.1}),
        TargetBook(date(2022, 1, 5), {"1003": 0.1}),
        TargetBook(date(2022, 1, 7), {"1004": 0.1, "1001": 0.1, "1002": 0.1}),
    ]
    diag = diagnostics(data, books)
    # pair 1: top mean (0.10 + 0.20) / 2 = 0.15, median of (.1, .2, -.1, 0) = 0.05 -> 0.10
    # pair 2: top 0.10 (1003: 90 -> 99), returns (0, -.10, .10, .05) median 0.025 -> 0.075
    assert diag["n_months"] == 2
    assert diag["top_vs_median_gross_monthly"] == pytest.approx(0.0875)
    assert diag["top_mean_gross_monthly"] == pytest.approx((0.15 + 0.10) / 2)
    assert diag["median_gross_monthly"] == pytest.approx((0.05 + 0.025) / 2)
    assert diag["avg_names"] == pytest.approx((2 + 1 + 3) / 3)


def test_diagnostics_no_books_or_single_book(tmp_path):
    w = small_world(tmp_path, {"1111": 0.5})
    data = w.load(V_START, V_END)
    one = diagnostics(data, [TargetBook(date(2022, 1, 10), {"1111": 0.1})])
    assert one["n_months"] == 0 and one["top_vs_median_gross_monthly"] is None
    none = diagnostics(data, [])
    assert none["n_months"] == 0 and none["avg_names"] == 0.0


# ------------------------------------------------------------ run_h1 end to end


def scenario(tmp_path, top_drift: float):
    """30 stocks, the top three by revenue growth (yoy rises with the id) drift by top_drift a
    day, the rest are flat. The same names win the ranking every month."""
    w = World(tmp_path, DAYS)
    for i, sid in enumerate(IDS):
        add_history(w, sid, 0.1 * (i + 1))
        drift = top_drift if i >= 27 else 0.0
        w.prices[sid] = {}
        for t, d in enumerate(DAYS):
            lvl = 100.0 * (1 + drift) ** t
            sgn = (-1) ** t
            w.prices[sid][d] = (lvl * (1 + 0.002 * sgn), lvl * (1 - 0.002 * sgn))
    w.prices["0050"] = {
        d: (100.0 * (1 + 0.001 * (-1) ** t), 100.0 * (1 - 0.001 * (-1) ** t))
        for t, d in enumerate(DAYS)
    }
    w.set_universe(date(2021, 11, 30), IDS, bench=["0050"])
    return w


def read_log(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def test_run_h1_winning_signal_not_falsified(tmp_path, logpath):
    w = scenario(tmp_path, 0.01)
    w.write()
    out = tmp_path / "out"
    res = run_h1(w.settings(), "validation", out_dir=out)
    assert res["falsification"]["verdict"] == "not falsified"
    assert all(res["falsification"]["conditions"].values())
    assert res["record"]["net_sharpe"] > 0.5
    assert res["diagnostics"]["top_vs_median_gross_monthly"] > 0
    assert res["n_books"] == 4
    # files
    js = json.loads((out / "H1_validation.json").read_text())
    assert js["record"]["card_id"] == "H1" and "daily" not in js["record"]
    assert js["record"]["params"] == {"top_fraction": 0.1, "max_weight": 0.1}
    assert js["falsification"]["verdict"] == "not falsified"
    md = (out / "H1_validation.md").read_text()
    assert "NOT FALSIFIED" in md and "Net Sharpe" in md and "Deflated Sharpe" in md
    assert "Annual turnover (one-way)" in md and "Max drawdown" in md
    # exactly one logged run
    rows = read_log(logpath)
    assert len(rows) == 1 and rows[0]["status"] == "ok" and rows[0]["card_id"] == "H1"
    assert rows[0]["window"] == "validation"


def test_run_h1_losing_signal_falsified(tmp_path, logpath):
    w = scenario(tmp_path, -0.01)
    w.write()
    out = tmp_path / "out"
    res = run_h1(w.settings(), "validation", out_dir=out)
    assert res["falsification"]["verdict"] == "falsified"
    c = res["falsification"]["conditions"]
    assert not c["net_sharpe_at_least_0.5"]
    assert not c["net_excess_over_0050_above_zero"]
    assert not c["top_decile_beats_median_gross"]
    md = (out / "H1_validation.md").read_text()
    assert "FALSIFIED" in md and "NOT FALSIFIED" not in md
    assert "FAIL" in md


def test_run_h1_default_out_dir_is_repo_research_runs(tmp_path, logpath, monkeypatch):
    # the default is never written by tests: stub the writer root to a temp directory
    monkeypatch.setattr(h1, "repo_root", lambda: tmp_path / "fake_root")
    w = scenario(tmp_path, 0.01)
    w.write()
    res = run_h1(w.settings(), "validation")
    assert res["files"][0] == str(
        tmp_path / "fake_root" / "research" / "runs" / "H1_validation.json"
    )


def test_run_h1_refuses_missing_data(tmp_path, logpath):
    w = scenario(tmp_path, 0.01)
    w.write(skip=("monthly_revenue",))
    with pytest.raises(DataError):
        run_h1(w.settings(), "validation", out_dir=tmp_path / "out")
    assert not (tmp_path / "out").exists()
    assert not logpath.exists() or logpath.read_text() == ""


def test_run_h1_refuses_empty_data_directory(tmp_path, logpath):
    w = scenario(tmp_path, 0.01)  # nothing written
    with pytest.raises(DataError):
        run_h1(w.settings(), "validation", out_dir=tmp_path / "out")


def test_run_h1_rejects_other_windows(tmp_path, logpath):
    w = scenario(tmp_path, 0.01)
    w.write()
    for bad in ("dev", "holdout", "test"):
        with pytest.raises(ValueError):
            run_h1(w.settings(), bad, out_dir=tmp_path / "out")
    assert not logpath.exists()


def test_run_h1_train_window_verdict_not_evaluated(tmp_path, logpath):
    # train data: a window in 2015 with its own calendar
    days = weekdays(date(2015, 5, 1), 110)
    w = World(tmp_path, days)
    ids = IDS
    for i, sid in enumerate(ids):
        w.prices[sid] = {d: (100.0 * (1 + 0.002 * (-1) ** t), 100.0) for t, d in enumerate(days)}
        m = date(2014, 5, 1)
        while m <= date(2015, 9, 1):
            recent = m >= date(2015, 5, 1)
            w.add_revenue(sid, m, round(100 * (1 + 0.1 * (i + 1))) if recent else 100)
            m = month_add(m, 1)
    w.prices["0050"] = {d: (100.0, 100.0 + (t % 2)) for t, d in enumerate(days)}
    w.set_universe(date(2015, 4, 30), ids, bench=["0050"])
    w.write()
    res = run_h1(w.settings(), "train", out_dir=tmp_path / "out")
    assert res["falsification"]["verdict"].startswith("not evaluated")
    assert (tmp_path / "out" / "H1_train.json").exists()
    assert res["record"]["window"] == "train"


# ------------------------------------------------------------ falsification rule


class _Rec:
    def __init__(self, sharpe, excess_annual, daily_excess):
        self.net_sharpe = sharpe
        self.excess_annual_return = excess_annual
        self.daily = [(date(2022, 1, 4), e, 0.0) for e in daily_excess]


GOOD = {"top_vs_median_gross_monthly": 0.01}


@pytest.mark.parametrize(
    ("rec", "diag", "expected"),
    [
        (_Rec(1.0, 0.1, [0.001]), GOOD, "not falsified"),
        (_Rec(0.49, 0.1, [0.001]), GOOD, "falsified"),
        (_Rec(0.5, 0.1, [0.001]), GOOD, "not falsified"),
        (_Rec(1.0, 0.0, [0.001]), GOOD, "falsified"),
        (_Rec(1.0, 0.1, [-0.001]), GOOD, "falsified"),
        (_Rec(1.0, 0.1, [0.001]), {"top_vs_median_gross_monthly": 0.0}, "falsified"),
        (_Rec(1.0, 0.1, [0.001]), {"top_vs_median_gross_monthly": None}, "falsified"),
        (_Rec(math.nan, 0.1, [0.001]), GOOD, "falsified"),
    ],
)
def test_falsification_rule(rec, diag, expected):
    assert h1.falsification(rec, diag, "validation")["verdict"] == expected
