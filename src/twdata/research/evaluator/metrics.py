"""Return statistics. Pure functions over lists of daily returns."""

from __future__ import annotations

import math
from datetime import date
from statistics import NormalDist

from twdata.research.evaluator.constants import ANNUALIZATION

EULER_GAMMA = 0.5772156649015329
_N = NormalDist()


def mean(xs: list[float]) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def std(xs: list[float]) -> float:
    """Sample standard deviation (ddof 1)."""
    n = len(xs)
    if n < 2:
        return 0.0
    m = mean(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))


def sharpe_daily(xs: list[float]) -> float:
    s = std(xs)
    return mean(xs) / s if s > 0 else 0.0


def sharpe_annual(xs: list[float]) -> float:
    return sharpe_daily(xs) * math.sqrt(ANNUALIZATION)


def total_return(xs: list[float]) -> float:
    nav = 1.0
    for x in xs:
        nav *= 1.0 + x
    return nav - 1.0


def annual_return(xs: list[float]) -> float:
    years = len(xs) / ANNUALIZATION
    if years <= 0:
        return 0.0
    nav = 1.0 + total_return(xs)
    if nav <= 0:
        return -1.0
    return nav ** (1.0 / years) - 1.0


def annual_vol(xs: list[float]) -> float:
    return std(xs) * math.sqrt(ANNUALIZATION)


def max_drawdown(xs: list[float]) -> float:
    """Most negative NAV / running peak - 1 (zero or negative); the peak starts at 1.0."""
    nav, peak, worst = 1.0, 1.0, 0.0
    for x in xs:
        nav *= 1.0 + x
        peak = max(peak, nav)
        worst = min(worst, nav / peak - 1.0)
    return worst


def skew_kurt(xs: list[float]) -> tuple[float, float]:
    """Population skewness and raw (non-excess) kurtosis; (0, 3) when degenerate."""
    n = len(xs)
    if n < 2:
        return 0.0, 3.0
    m = mean(xs)
    m2 = sum((x - m) ** 2 for x in xs) / n
    if m2 <= 0:
        return 0.0, 3.0
    m3 = sum((x - m) ** 3 for x in xs) / n
    m4 = sum((x - m) ** 4 for x in xs) / n
    return m3 / m2**1.5, m4 / m2**2


def monthly_returns(dates: list[date], xs: list[float]) -> dict[tuple[int, int], float]:
    out: dict[tuple[int, int], float] = {}
    for d, x in zip(dates, xs, strict=True):
        k = (d.year, d.month)
        out[k] = (1.0 + out.get(k, 0.0)) * (1.0 + x) - 1.0 if k in out else x
    return out


def hit_rate(dates: list[date], strat: list[float], bench: list[float]) -> float:
    s = monthly_returns(dates, strat)
    b = monthly_returns(dates, bench)
    if not s:
        return 0.0
    return sum(1 for k in s if s[k] > b[k]) / len(s)


def expected_max_sharpe(n_trials: int, trial_var: float) -> float:
    """SR0 of Bailey and Lopez de Prado: the expected maximum Sharpe of n_trials trials with
    zero true Sharpe and variance trial_var (daily units). Zero for one trial."""
    if n_trials < 2 or trial_var <= 0:
        return 0.0
    g = EULER_GAMMA
    z1 = _N.inv_cdf(1.0 - 1.0 / n_trials)
    z2 = _N.inv_cdf(1.0 - 1.0 / (n_trials * math.e))
    return math.sqrt(trial_var) * ((1.0 - g) * z1 + g * z2)


def deflated_sharpe(
    sr_daily: float,
    n_obs: int,
    skew: float,
    kurt: float,
    n_trials: int,
    trial_sharpes_daily: list[float],
) -> float:
    """Probability that the true Sharpe is positive after n_trials trials.

    Trial variance: the sample variance of the logged trial Sharpes when n_trials >= 3 and at
    least two are available, otherwise (0.5 * observed Sharpe) squared. Returns 0.0 when the
    estimator's variance term is not positive (conservative)."""
    if n_trials >= 3 and len(trial_sharpes_daily) >= 2:
        v = std(trial_sharpes_daily) ** 2
    else:
        v = (0.5 * sr_daily) ** 2
    sr0 = expected_max_sharpe(n_trials, v)
    den = 1.0 - skew * sr_daily + (kurt - 1.0) / 4.0 * sr_daily**2
    if den <= 0 or n_obs < 2:
        return 0.0
    return _N.cdf((sr_daily - sr0) * math.sqrt(n_obs - 1) / math.sqrt(den))
