"""Hypothesis H1: drift after monthly revenue surprises (research/cards/H1_revenue_drift.md).

Spec: docs/specs/strategy_h1.md. Development window only. Features come from
`data.as_of(decision_date)` and never from `data.tables` or adjusted prices; the diagnostics use
adjusted opens as a label only."""

from __future__ import annotations

import json
import math
import statistics
from dataclasses import asdict
from datetime import date, datetime, timedelta
from pathlib import Path

from twdata.common.config import repo_root
from twdata.research.evaluator import DevData, TargetBook, load_dev_data, run_backtest
from twdata.research.evaluator.engine import window_bounds

CARD_ID = "H1"
TOP_FRACTION_PCT = 10  # top decile, kept as an integer percentage so ceil() is exact
MAX_WEIGHT = 0.10
PARAMS = {"top_fraction": 0.10, "max_weight": 0.10}
MIN_SHARPE = 0.5
WINDOWS = ("train", "validation")


# ------------------------------------------------------------------ books


def _month_back(d: date, months: int) -> date:
    idx = d.year * 12 + (d.month - 1) - months
    return date(idx // 12, idx % 12 + 1, 1)


def decision_dates(data: DevData, start: date, end: date) -> list[date]:
    """First trading day on or after the 10th of each month whose 10th is in [start, end].

    A month is skipped when the calendar has no such day, when that day is after `end`, or when
    no later trading day exists to execute on (the evaluator would refuse the book)."""
    out = []
    y, m = start.year, start.month
    while date(y, m, 1) <= end:
        tenth = date(y, m, 10)
        if start <= tenth <= end:
            month_end = date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
            cand = data.calendar.days_between(tenth, month_end)
            if cand and cand[0] <= end and data.calendar.next_after(cand[0]) is not None:
                out.append(cand[0])
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return out


def _universe(visible) -> list[str]:
    rows = visible.table("universe_membership")
    if not rows:
        return []
    latest = max(r["month_end"] for r in rows)
    return sorted(
        {r["stock_id"] for r in rows if r["month_end"] == latest and not r["is_benchmark"]}
    )


def _yoy_scores(visible, universe: list[str], decision_date: date) -> dict[str, float]:
    m = _month_back(decision_date.replace(day=1), 1)
    m12 = _month_back(m, 12)
    want = set(universe)
    rev: dict[tuple[str, date], float | None] = {}
    # rows come sorted by available_at, so a later restatement overrides an earlier row
    for r in visible.table("monthly_revenue"):
        if r["event_date"] in (m, m12) and r["stock_id"] in want:
            rev[(r["stock_id"], r["event_date"])] = r["revenue"]
    scores = {}
    for sid in universe:
        cur, old = rev.get((sid, m)), rev.get((sid, m12))
        if cur is None or old is None or not old > 0:
            continue
        scores[sid] = cur / old - 1.0
    return scores


def select_book(scores: dict[str, float]) -> dict[str, float]:
    """Top ceil(10% of n) by score (ties: lower stock_id first), weight min(1/k, 0.10)."""
    n = len(scores)
    if n == 0:
        return {}
    k = -(-n * TOP_FRACTION_PCT // 100)
    ranked = sorted(scores, key=lambda s: (-scores[s], s))[:k]
    w = min(1.0 / k, MAX_WEIGHT)
    return {sid: w for sid in ranked}


def build_books(data: DevData, start: date, end: date) -> list[TargetBook]:
    books = []
    for d in decision_dates(data, start, end):
        visible = data.as_of(d)
        scores = _yoy_scores(visible, _universe(visible), d)
        books.append(TargetBook(decision_date=d, weights=select_book(scores)))
    return books


# ------------------------------------------------------------------ diagnostics


def _open_return(data: DevData, sid: str, e0: date, e1: date) -> float | None:
    a, b = data.adj_open(sid, e0), data.adj_open(sid, e1)
    if a is None or b is None or a <= 0:
        return None
    return b / a - 1.0


def diagnostics(data: DevData, books: list[TargetBook]) -> dict:
    """Gross open-to-open adjusted return of the selected names against the median universe
    stock, from each book's execution open to the next book's execution open."""
    books = sorted(books, key=lambda b: b.decision_date)
    diffs, tops, medians = [], [], []
    for b0, b1 in zip(books, books[1:], strict=False):
        e0 = data.next_trading_day(b0.decision_date)
        e1 = data.next_trading_day(b1.decision_date)
        if e0 is None or e1 is None or not b0.weights:
            continue
        sel = [r for s in b0.weights if (r := _open_return(data, s, e0, e1)) is not None]
        uni = [
            r
            for s in _universe(data.as_of(b0.decision_date))
            if (r := _open_return(data, s, e0, e1)) is not None
        ]
        if not sel or not uni:
            continue
        top, med = statistics.fmean(sel), statistics.median(uni)
        tops.append(top)
        medians.append(med)
        diffs.append(top - med)
    return {
        "top_vs_median_gross_monthly": statistics.fmean(diffs) if diffs else None,
        "top_mean_gross_monthly": statistics.fmean(tops) if tops else None,
        "median_gross_monthly": statistics.fmean(medians) if medians else None,
        "n_months": len(diffs),
        "avg_names": statistics.fmean(len(b.weights) for b in books) if books else 0.0,
    }


# ------------------------------------------------------------------ run


def _positive(x) -> bool:
    return isinstance(x, (int, float)) and math.isfinite(x) and x > 0


def falsification(rec, diag: dict, window: str) -> dict:
    """The card's rule. Falsified when net Sharpe < 0.5, or net mean excess return over 0050
    is not above zero, or the top decile does not beat the median stock (gross monthly).
    A missing or non-finite number fails its condition. Only the validation window decides."""
    daily = [r - b for _, r, b in rec.daily]
    mean_daily_excess = statistics.fmean(daily) if daily else None
    sharpe_ok = isinstance(rec.net_sharpe, float) and rec.net_sharpe >= MIN_SHARPE
    # conservative: both the compounded annual and the mean daily excess must be positive
    excess_ok = _positive(rec.excess_annual_return) and _positive(mean_daily_excess)
    top_ok = _positive(diag["top_vs_median_gross_monthly"])
    conditions = {
        "net_sharpe_at_least_0.5": sharpe_ok,
        "net_excess_over_0050_above_zero": excess_ok,
        "top_decile_beats_median_gross": top_ok,
    }
    if window != "validation":
        verdict = "not evaluated (train window; the rule applies to the validation window)"
    else:
        verdict = "not falsified" if all(conditions.values()) else "falsified"
    return {
        "verdict": verdict,
        "conditions": conditions,
        "mean_daily_excess": mean_daily_excess,
    }


def _clean(o):
    if isinstance(o, float) and not math.isfinite(o):
        return None
    if isinstance(o, dict):
        return {k: _clean(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_clean(v) for v in o]
    if isinstance(o, (date, datetime)):
        return o.isoformat()
    return o


def _fmt(x, pct=False, nd=3) -> str:
    if x is None or not isinstance(x, (int, float)) or not math.isfinite(x):
        return "n/a"
    return f"{x * 100:.2f}%" if pct else f"{x:.{nd}f}"


def _pf(ok: bool) -> str:
    return "pass" if ok else "FAIL"


def _markdown(window: str, record: dict, diag: dict, fals: dict) -> str:
    c = fals["conditions"]
    rows = [
        ("Window", f"{window} ({record['window_start']} to {record['window_end']})"),
        ("Net Sharpe", _fmt(record["net_sharpe"])),
        ("0050 Sharpe", _fmt(record["benchmark_net_sharpe"])),
        ("Net annual return", _fmt(record["net_annual_return"], pct=True)),
        ("Excess annual return over 0050", _fmt(record["excess_annual_return"], pct=True)),
        ("Annual turnover (one-way)", _fmt(record["annual_turnover_one_way"], pct=True)),
        ("Annual cost drag", _fmt(record["annual_cost_drag"], pct=True)),
        ("Max drawdown", _fmt(record["max_drawdown"], pct=True)),
        ("Attempts this cycle (n_trials)", str(record["n_trials"])),
        ("Deflated Sharpe", _fmt(record["deflated_sharpe"])),
        (
            "Top decile minus median, gross monthly",
            _fmt(diag["top_vs_median_gross_monthly"], pct=True),
        ),
        (
            "Months in diagnostics / average names",
            f"{diag['n_months']} / {_fmt(diag['avg_names'], nd=1)}",
        ),
        ("Falsification verdict", fals["verdict"].upper()),
        ("Condition: net Sharpe at least 0.5", _pf(c["net_sharpe_at_least_0.5"])),
        ("Condition: net excess over 0050 above zero", _pf(c["net_excess_over_0050_above_zero"])),
        ("Condition: top decile beats median (gross)", _pf(c["top_decile_beats_median_gross"])),
    ]
    lines = [
        f"# H1 revenue drift, {window} window",
        "",
        "PROVISIONAL: every early-lane result is provisional until the full Phase 1 QA passes.",
        "",
        "| Item | Value |",
        "|---|---|",
        *[f"| {k} | {v} |" for k, v in rows],
        "",
    ]
    return "\n".join(lines)


def run_h1(settings, window: str, out_dir: Path | None = None) -> dict:
    if window not in WINDOWS:
        raise ValueError(f"window must be one of {WINDOWS}, got {window!r}")
    out = Path(out_dir) if out_dir is not None else repo_root() / "research" / "runs"
    start, end = window_bounds(settings, window)
    data = load_dev_data(settings, start, end)
    books = build_books(data, start, end)
    rec = run_backtest(data, books, card_id=CARD_ID, params=dict(PARAMS), window=window)
    diag = diagnostics(data, books)
    fals = falsification(rec, diag, window)
    record = asdict(rec)
    record.pop("daily")
    record["params"] = dict(PARAMS)  # RunRecord carries only the hash; the log line has both
    record["cycle"] = settings.research.cycle
    record = _clean(record)
    result = {
        "card_id": CARD_ID,
        "window": window,
        "provisional": True,
        "record": record,
        "diagnostics": _clean(diag),
        "falsification": _clean(fals),
        "n_books": len(books),
    }
    out.mkdir(parents=True, exist_ok=True)
    json_path = out / f"H1_{window}.json"
    md_path = out / f"H1_{window}.md"
    json_path.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    md = _markdown(window, record, result["diagnostics"], result["falsification"])
    md_path.write_text(md, encoding="utf-8")
    result["files"] = [str(json_path), str(md_path)]
    return result
