import math
from datetime import date
from statistics import NormalDist

import pytest

from twdata.research.evaluator import costs, metrics
from twdata.research.evaluator.constants import ANNUALIZATION


def test_cost_arithmetic():
    assert costs.buy_cost(1000.0) == pytest.approx(1000 * (0.001425 + 0.001))
    assert costs.sell_cost("2330", 1000.0) == pytest.approx(1000 * (0.001425 + 0.001 + 0.003))
    assert costs.sell_cost("0050", 1000.0) == pytest.approx(1000 * (0.001425 + 0.001 + 0.001))
    assert costs.sell_cost("00878", 1000.0) == pytest.approx(1000 * 0.003425)


def test_etf_classification():
    assert not costs.is_etf("1101")
    assert not costs.is_etf("9958")
    assert costs.is_etf("0050")
    assert costs.is_etf("00632R")
    assert costs.is_etf("2330A")
    assert costs.is_etf("123")


def test_sharpe_drawdown_basic():
    xs = [0.01, -0.02, 0.03]
    m = sum(xs) / 3
    sd = math.sqrt(sum((x - m) ** 2 for x in xs) / 2)
    assert metrics.sharpe_annual(xs) == pytest.approx(m / sd * math.sqrt(ANNUALIZATION))
    assert metrics.max_drawdown(xs) == pytest.approx(0.98 / 1.0 - 1)
    assert metrics.max_drawdown([0.1, 0.1]) == 0.0
    assert metrics.total_return(xs) == pytest.approx(1.01 * 0.98 * 1.03 - 1)
    assert metrics.sharpe_annual([0.0, 0.0]) == 0.0


def test_monthly_hit_rate():
    d = [date(2023, 1, 30), date(2023, 1, 31), date(2023, 2, 1), date(2023, 2, 2)]
    s = [0.01, 0.01, -0.01, 0.0]
    b = [0.0, 0.0, 0.0, 0.0]
    assert metrics.hit_rate(d, s, b) == 0.5


def test_expected_max_sharpe_known_value():
    # Bailey and Lopez de Prado: N=10 unit-variance trials give about 1.574
    assert metrics.expected_max_sharpe(10, 1.0) == pytest.approx(1.574, abs=0.005)
    assert metrics.expected_max_sharpe(1, 1.0) == 0.0


def test_deflated_sharpe_single_trial():
    sr, t = 0.1, 250
    expected = NormalDist().cdf(sr * math.sqrt(t - 1) / math.sqrt(1 + 0.5 * sr**2))
    assert metrics.deflated_sharpe(sr, t, 0.0, 3.0, 1, [sr]) == pytest.approx(expected)


def test_deflated_sharpe_fallback_and_log_variance():
    sr, t = 0.1, 250
    # N=2 uses (0.5 * sr)^2 as the variance
    sr0 = metrics.expected_max_sharpe(2, (0.5 * sr) ** 2)
    expected = NormalDist().cdf((sr - sr0) * math.sqrt(t - 1) / math.sqrt(1 + 0.5 * sr**2))
    assert metrics.deflated_sharpe(sr, t, 0.0, 3.0, 2, [0.0, sr]) == pytest.approx(expected)
    # N=3 uses the logged trials' sample variance
    trials = [0.0, 0.05, 0.1]
    v = metrics.std(trials) ** 2
    assert v == pytest.approx(0.0025)
    sr0 = metrics.expected_max_sharpe(3, v)
    expected = NormalDist().cdf((sr - sr0) * math.sqrt(t - 1) / math.sqrt(1 + 0.5 * sr**2))
    assert metrics.deflated_sharpe(sr, t, 0.0, 3.0, 3, trials) == pytest.approx(expected)
    # more trials never raise it
    assert metrics.deflated_sharpe(sr, t, 0.0, 3.0, 30, trials) < expected


def test_skew_kurt_normal_like():
    sk, ku = metrics.skew_kurt([-1.0, 1.0] * 50)
    assert sk == pytest.approx(0.0)
    assert ku == pytest.approx(1.0)
