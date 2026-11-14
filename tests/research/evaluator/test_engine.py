import json
import math
from datetime import date

import pytest
from helpers import DAYS, A, B, make_world
from world import flat, utc

from twdata.research.evaluator import BookError, TargetBook, run_backtest
from twdata.research.evaluator import metrics as M
from twdata.research.evaluator.constants import ANNUALIZATION

RB = 0.002425
RS = 0.005425  # stock sell
RS_ETF = 0.003425


def run(data, books, window="validation"):
    return run_backtest(data, books, card_id="T", params={}, window=window)


def test_next_open_execution_and_exit(tmp_path, logpath):
    w = make_world(tmp_path, 4)
    d = DAYS
    w.add(A, {d[0]: (100, 100), d[1]: (100, 110), d[2]: (110, 110), d[3]: (110, 110)})
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    assert rec.first_execution == d[1]  # next trading day, not the decision day
    assert rec.n_days == 3
    cash = 1 - 0.1 - 0.1 * RB
    expected = cash + 0.11 - 0.11 * RS
    assert rec.net_total_return == pytest.approx(expected - 1)
    assert rec.n_fills == 2 and rec.n_books == 1
    # 0050 buy and hold, flat price: initial buy and final ETF sell costs only
    n = 1 / (1 + RB)
    assert rec.benchmark_net_total_return == pytest.approx(n * (1 - RS_ETF) - 1)
    assert rec.provisional is True


def test_decision_day_prices_do_not_matter(tmp_path, logpath):
    w = make_world(tmp_path, 4)
    d = DAYS
    w.add(A, {d[0]: (50, 500), d[1]: (100, 100), d[2]: (100, 100), d[3]: (100, 100)})
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    assert rec.net_total_return == pytest.approx(-0.1 * (RB + RS))


def test_limit_up_buy_blocked(tmp_path, logpath):
    w = make_world(tmp_path, 4)
    d = DAYS
    w.add(A, flat(100.0, d))
    w.limits[A] = {d[1]: (100.0, 90.0)}  # open at limit up on the execution day
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    assert rec.unfilled_buys == 1 and rec.n_fills == 0
    assert rec.net_total_return == 0.0  # weight stayed in cash, cash earns zero


def test_limit_up_below_open_and_null_limits_fill(tmp_path, logpath):
    w = make_world(tmp_path, 4)
    d = DAYS
    w.add(A, flat(100.0, d))
    w.add(B, flat(100.0, d))
    w.limits[A] = {d[1]: (107.0, 93.0)}
    w.limits[B] = {d[1]: (None, None)}
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1, B: 0.1})])
    assert rec.unfilled_buys == 0 and rec.n_fills == 4


def _two_book_world(tmp_path, n, locked_days, drop_after=None):
    w = make_world(tmp_path, n)
    d = DAYS
    series = flat(100.0, d[:n])
    if drop_after is not None:
        for x in d[drop_after:n]:
            series[x] = (50.0, 50.0)
    w.add(A, series)
    w.limits[A] = {x: (200.0, 100.0 if x in locked_days else 90.0) for x in d[:n]}
    return w


def test_limit_down_sell_forced_on_fifth_open(tmp_path, logpath):
    d = DAYS
    # buy d1; the sell book decided d3 executes d4; locked at d4..d8; price halves from d9
    w = _two_book_world(tmp_path, 16, set(d[4:9]), drop_after=9)
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1}), TargetBook(d[3], {})])
    assert rec.blocked_sells == 4 and rec.forced_sells == 1
    # forced at the d8 open (100): the later drop is not suffered
    assert rec.net_total_return == pytest.approx(-0.1 * (RB + RS))
    assert rec.n_fills == 2


def test_limit_down_sell_retried_and_fills_when_unlocked(tmp_path, logpath):
    d = DAYS
    w = _two_book_world(tmp_path, 16, set(d[4:6]), drop_after=7)
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1}), TargetBook(d[3], {})])
    assert rec.blocked_sells == 2 and rec.forced_sells == 0
    assert rec.net_total_return == pytest.approx(-0.1 * (RB + RS))


def test_unfilled_sell_keeps_earning_stock_return(tmp_path, logpath):
    d = DAYS
    w = _two_book_world(tmp_path, 8, {d[4]})
    w.prices[A][d[4]] = (100.0, 102.0)  # locked at the open, then closes higher
    for x in d[5:8]:
        w.prices[A][x] = (102.0, 102.0)
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1}), TargetBook(d[3], {})])
    assert rec.blocked_sells == 1
    expected = (1 - 0.1 - 0.1 * RB) + 0.102 - 0.102 * RS
    assert rec.net_total_return == pytest.approx(expected - 1)


def test_tradeable_mask(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    ids = ["1001", "1002", "1003", "1004", "1005", "1006", "1007"]
    for sid in ids:
        w.add(sid, flat(100.0, d))
    del w.prices["1004"][d[1]]  # no row on the execution day
    w.members = {date(2022, 12, 31): (utc(date(2022, 12, 31)), [s for s in ids if s != "1002"])}
    old = utc(date(2022, 12, 1))
    w.status = [
        ("1003", "disposition", d[1], d[2], old),  # covers E
        ("1005", "disposition", date(2022, 12, 5), d[0], old),  # ended before E
        ("1006", "changed_trading", d[0], None, old),  # open ended window
        ("1007", "attention", d[0], d[3], old),  # attention does not block
    ]
    rec = run(w.load(), [TargetBook(d[0], {s: 0.1 for s in ids})])
    reasons = {x[1]: x[2] for x in rec.dropped_detail}
    assert reasons == {
        "1002": "not_in_universe",
        "1003": "status_window",
        "1004": "no_open",
        "1006": "status_window",
    }
    assert rec.dropped_non_tradeable == 4
    assert rec.n_fills == 6  # 1001, 1005, 1007 bought, and sold at the final open


def test_dropped_name_stays_in_cash(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, d))
    w.add(B, flat(100.0, d))
    w.members = {date(2022, 12, 31): (utc(date(2022, 12, 31)), [A])}
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1, B: 0.1})])
    assert rec.n_fills == 2
    assert rec.dropped_detail == [[d[0].isoformat(), B, "not_in_universe"]]
    assert rec.net_total_return == pytest.approx(-0.1 * (RB + RS))


def test_membership_uses_only_months_available_at_decision(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, d))
    w.add(B, flat(100.0, d))
    w.members = {
        date(2022, 12, 31): (utc(date(2022, 12, 31)), [A]),
        date(2023, 1, 31): (utc(date(2023, 2, 1)), [B]),  # not yet known on 2023-01-02
    }
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1, B: 0.1})])
    assert [x[1] for x in rec.dropped_detail] == [B]


def test_book_rejections_and_error_line(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, d))
    data = w.load()
    with pytest.raises(BookError, match="exceeds"):
        run(data, [TargetBook(d[0], {A: 0.11})])
    ids = [f"{1000 + i}" for i in range(11)]
    with pytest.raises(BookError, match="gross"):
        run(data, [TargetBook(d[0], {s: 0.1 for s in ids})])
    with pytest.raises(BookError, match="negative"):
        run(data, [TargetBook(d[0], {A: -0.01})])
    with pytest.raises(BookError, match="window"):
        run(data, [TargetBook(date(2020, 1, 2), {A: 0.1})])
    with pytest.raises(BookError, match="unknown window"):
        run(data, [TargetBook(d[0], {A: 0.1})], window="holdout")
    lines = [json.loads(x) for x in logpath.read_text().splitlines()]
    assert len(lines) == 5 and all(x["status"] == "error" for x in lines)
    assert lines[0]["error_type"] == "BookError" and "exceeds" in lines[0]["message"]
    # exactly 10% per name is allowed; error lines count as trials
    rec = run(data, [TargetBook(d[0], {A: 0.1})])
    assert rec.n_trials == 6


def test_adjusted_return_through_four_for_one_split(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 5)
    s = {d[0]: (400, 400), d[1]: (400, 400), d[2]: (100, 100), d[3]: (100, 100), d[4]: (100, 100)}
    w.add(A, s, adj={x: 100.0 for x in d[:5]})  # fully adjusted close is continuous
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    assert rec.net_total_return == pytest.approx(-0.1 * (RB + RS))
    assert rec.max_drawdown > -0.001


def test_overnight_gap_uses_adjusted_open(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    # raw price falls 10% at d2 open (a 10% cash dividend): the adjusted series is flat
    s = {d[0]: (100, 100), d[1]: (100, 100), d[2]: (90, 90), d[3]: (90, 90)}
    w.add(A, s, adj={x: 90.0 for x in d[:4]})
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    assert rec.net_total_return == pytest.approx(-0.1 * (RB + RS))


def test_two_asset_hand_computed_metrics(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    w.add(A, {d[0]: (100, 100), d[1]: (100, 110), d[2]: (110, 121), d[3]: (121, 121)})
    w.add(B, {d[0]: (100, 100), d[1]: (100, 90), d[2]: (90, 99), d[3]: (99, 99)})
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1, B: 0.1})])
    cash = 1 - 0.2 - 0.2 * RB
    nav1 = cash + 0.11 + 0.09
    nav2 = cash + 0.121 + 0.099
    sell = 0.22 * RS
    nav3 = cash + 0.22 - sell
    rets = [nav1 - 1, nav2 / nav1 - 1, nav3 / nav2 - 1]
    gross = [(nav1 + 0.2 * RB) - 1, nav2 / nav1 - 1, (nav3 + sell) / nav2 - 1]
    assert rec.net_total_return == pytest.approx(nav3 - 1)
    m = sum(rets) / 3
    sd = math.sqrt(sum((x - m) ** 2 for x in rets) / 2)
    assert rec.net_sharpe == pytest.approx(m / sd * math.sqrt(ANNUALIZATION))
    assert rec.gross_sharpe == pytest.approx(M.sharpe_annual(gross))
    assert rec.net_annual_vol == pytest.approx(sd * math.sqrt(ANNUALIZATION))
    assert rec.net_annual_return == pytest.approx(nav3 ** (ANNUALIZATION / 3) - 1)
    assert rec.max_drawdown == pytest.approx(nav3 / nav2 - 1)
    nav2_open = cash + 0.22  # NAV at the final open, before the sell cost
    assert rec.annual_turnover == pytest.approx((0.2 + 0.22 / nav2_open) * ANNUALIZATION / 3)
    assert rec.annual_turnover_one_way == pytest.approx(rec.annual_turnover / 2)
    drag = (0.2 * RB + sell / nav2_open) * ANNUALIZATION / 3
    assert rec.annual_cost_drag == pytest.approx(drag)
    assert rec.excess_annual_return == pytest.approx(
        rec.net_annual_return - rec.benchmark_net_annual_return
    )
    assert [x[0] for x in rec.daily] == [d[1], d[2], d[3]]
    assert [x[1] for x in rec.daily] == pytest.approx(rets)


def test_drawdown_from_initial_nav(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4)
    w.add(A, flat(100.0, d))
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    # peak is the starting NAV 1.0; the lowest NAV is after the final sell
    assert rec.max_drawdown == pytest.approx(rec.net_total_return)


def test_benchmark_buy_and_hold(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 4, with_bench=False)
    w.add("0050", {d[0]: (100, 100), d[1]: (100, 100), d[2]: (101, 101), d[3]: (102.01, 102.01)})
    w.add(A, flat(100.0, d))
    rec = run(w.load(), [TargetBook(d[0], {A: 0.1})])
    n = 1 / (1 + RB)
    assert rec.benchmark_net_total_return == pytest.approx(n * 1.0201 * (1 - RS_ETF) - 1)
    assert rec.benchmark_annual_turnover == pytest.approx((n + 1.0) * ANNUALIZATION / 3)
    assert rec.excess_annual_return < 0


def test_deflated_sharpe_and_trials_recorded(tmp_path, logpath):
    d = DAYS
    w = make_world(tmp_path, 6)
    w.add(A, {x: (100 + i, 100 + i) for i, x in enumerate(d[:6])})
    data = w.load()
    recs = [run(data, [TargetBook(d[0], {A: 0.1})]) for _ in range(3)]
    assert [r.n_trials for r in recs] == [1, 2, 3]
    assert all(0.0 <= r.deflated_sharpe <= 1.0 for r in recs)
    assert recs[2].deflated_sharpe <= recs[0].deflated_sharpe
