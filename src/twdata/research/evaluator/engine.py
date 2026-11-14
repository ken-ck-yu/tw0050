"""Backtest engine: next-open execution, limit locks, tradeable mask, adjusted-return accounting.

NAV units: the portfolio starts at 1.0 in cash. Positions are held as values in NAV units and
marked on the fully adjusted price scale (adj_open / adjusted_close)."""

from __future__ import annotations

import math
import uuid
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta

from twdata.common.timeutil import UTC
from twdata.research.evaluator import log, metrics
from twdata.research.evaluator.constants import (
    ANNUALIZATION,
    BENCHMARK_ID,
    DEV_START,
    DROPPED_DETAIL_CAP,
    EPS,
    MAX_GROSS,
    MAX_SELL_DEFER_DAYS,
    MAX_WEIGHT,
    WEIGHT_TOL,
    WINDOWS,
    BookError,
    DataError,
)
from twdata.research.evaluator.costs import buy_rate, sell_rate
from twdata.research.evaluator.data import DevData

Weights = dict[str, float]


@dataclass
class TargetBook:
    decision_date: date
    weights: Weights


@dataclass
class RunRecord:
    run_id: str
    created_at: str
    card_id: str
    params_hash: str
    window: str
    evaluator_sha256: str
    window_start: date
    window_end: date
    first_execution: date
    last_day: date
    n_days: int
    n_books: int
    n_fills: int
    net_total_return: float
    net_annual_return: float
    net_annual_vol: float
    net_sharpe: float
    gross_sharpe: float
    max_drawdown: float
    annual_turnover: float
    annual_turnover_one_way: float
    annual_cost_drag: float
    benchmark_net_total_return: float
    benchmark_net_annual_return: float
    benchmark_net_annual_vol: float
    benchmark_net_sharpe: float
    benchmark_gross_sharpe: float
    benchmark_max_drawdown: float
    benchmark_annual_turnover: float
    benchmark_annual_cost_drag: float
    excess_annual_return: float
    hit_rate_monthly: float
    unfilled_buys: int
    blocked_sells: int
    forced_sells: int
    dropped_non_tradeable: int
    dropped_detail: list = field(default_factory=list)
    n_trials: int = 0
    deflated_sharpe: float = 0.0
    status: str = "ok"
    provisional: bool = True
    # per-day series for the caller (not written to the log)
    daily: list = field(default_factory=list, repr=False)

    def log_dict(self, params: dict, cycle: int) -> dict:
        d = asdict(self)
        d.pop("daily")
        d["params"] = params
        d["cycle"] = cycle
        d["dropped_detail"] = d["dropped_detail"][:DROPPED_DETAIL_CAP]
        return d


# ---------------------------------------------------------------- validation


def window_bounds(settings, window: str) -> tuple[date, date]:
    if window not in WINDOWS:
        raise BookError(f"unknown window {window!r}; expected one of {WINDOWS}")
    r = settings.research
    if window == "train":
        return DEV_START, r.train_end
    if window == "validation":
        return r.train_end + timedelta(days=1), r.dev_end
    return DEV_START, r.dev_end


def check_book(book: TargetBook) -> None:
    gross = 0.0
    for sid, w in book.weights.items():
        if not isinstance(w, (int, float)) or isinstance(w, bool) or not math.isfinite(w):
            raise BookError(f"{book.decision_date}: weight of {sid} is not a finite number")
        if w < 0:
            raise BookError(f"{book.decision_date}: negative weight for {sid} (long only)")
        if w > MAX_WEIGHT + WEIGHT_TOL:
            raise BookError(f"{book.decision_date}: weight {w} of {sid} exceeds {MAX_WEIGHT}")
        gross += w
    if gross > MAX_GROSS + WEIGHT_TOL:
        raise BookError(f"{book.decision_date}: gross weight {gross} exceeds {MAX_GROSS}")


def _membership(data: DevData, decision_date: date) -> set[str]:
    rows = data.as_of(decision_date).table("universe_membership")
    if not rows:
        return set()
    latest = max(r["month_end"] for r in rows)
    return {r["stock_id"] for r in rows if r["month_end"] == latest}


def _status_blocked(data: DevData, decision_date: date, e: date) -> set[str]:
    """Names inside a disposition or changed_trading window on e. Rows known at the decision
    cutoff count, and so do rows whose available_at is still null (conservative)."""
    cutoff = data.as_of(decision_date).cutoff
    out = set()
    for r in data.tables["status_events"]:
        if r["status_type"] not in ("disposition", "changed_trading"):
            continue
        av = r.get("available_at")
        if av is not None and av > cutoff:
            continue
        end = r.get("end_date")
        if r["start_date"] <= e and (end is None or e <= end):
            out.add(r["stock_id"])
    return out


def tradeable_targets(data: DevData, book: TargetBook, e: date) -> tuple[Weights, list]:
    """Apply the tradeable mask. Returns (kept weights, dropped [(date, stock, reason)])."""
    members = _membership(data, book.decision_date)
    blocked = _status_blocked(data, book.decision_date, e)
    kept: Weights = {}
    dropped = []
    for sid, w in sorted(book.weights.items()):
        if w <= 0:
            continue
        if sid not in members:
            reason = "not_in_universe"
        elif data.raw_open(sid, e) is None:
            reason = "no_open"
        elif data.adj_open(sid, e) is None:
            reason = "no_adjusted_price"
        elif sid in blocked:
            reason = "status_window"
        else:
            kept[sid] = w
            continue
        dropped.append((book.decision_date.isoformat(), sid, reason))
    return kept, dropped


# ---------------------------------------------------------------- simulation


@dataclass
class SimResult:
    dates: list
    net: list
    gross: list
    n_fills: int = 0
    unfilled_buys: int = 0
    blocked_sells: int = 0
    forced_sells: int = 0
    turnover: float = 0.0  # sum of buy and sell notional, each over NAV at the open of its day
    cost_frac: float = 0.0  # sum of costs, each over NAV at the open of its day


def simulate(
    data: DevData, days: list[date], targets_by_day: dict[date, Weights], *, strict: bool
) -> SimResult:
    """Run the portfolio over `days` (trading days, first = first execution, last = liquidation).

    strict=False (benchmark) skips limit locks, and the caller supplies already-masked targets."""
    res = SimResult([], [], [])
    cash = 1.0
    pos: dict[str, float] = {}
    mark: dict[str, float] = {}
    attempts: dict[str, int] = {}
    pending: set[str] = set()
    targets: Weights = {}
    last_day = days[-1]
    nav_prev = 1.0
    rb = buy_rate()

    for d in days:
        # 1. overnight, previous close to this open
        for sid in pos:
            ao = data.adj_open(sid, d)
            if ao is not None:
                pos[sid] *= ao / mark[sid]
                mark[sid] = ao
        nav_open = cash + sum(pos.values())
        day_cost = 0.0

        final = d == last_day
        new_book = d in targets_by_day
        if new_book:
            targets = dict(targets_by_day[d])
            pending = set()
        if final:
            targets = {}
        if new_book or final or pending:
            # drift is only rebalanced on a book day; other days only retry blocked sells
            consider = (set(pos) | set(targets)) if (new_book or final) else set(pending)
            sells, buys = [], []
            for sid in sorted(consider):
                cur = pos.get(sid, 0.0)
                tgt = targets.get(sid, 0.0) * nav_open
                if final or sid not in targets:
                    tgt = 0.0
                delta = tgt - cur
                if delta < -EPS:
                    sells.append((sid, -delta if tgt > 0 else cur))
                else:
                    attempts.pop(sid, None)
                    if delta > EPS and new_book and not final:
                        buys.append((sid, delta))
            # sells first
            for sid, amt in sells:
                op = data.raw_open(sid, d)
                if op is None and not final:
                    pending.add(sid)  # no print today, retry tomorrow (no attempt consumed)
                    continue
                if op is not None and not final:
                    attempts[sid] = attempts.get(sid, 0) + 1
                    lim = data.limits.get((sid, d))
                    ld = None if lim is None else lim.get("limit_down")
                    if strict and ld is not None and op <= ld:
                        if attempts[sid] < MAX_SELL_DEFER_DAYS:
                            res.blocked_sells += 1
                            pending.add(sid)
                            continue
                        res.forced_sells += 1
                amt = min(amt, pos[sid])
                cost = amt * sell_rate(sid)
                pos[sid] -= amt
                cash += amt - cost
                day_cost += cost
                res.turnover += amt / nav_open
                res.cost_frac += cost / nav_open
                res.n_fills += 1
                attempts.pop(sid, None)
                pending.discard(sid)
                if pos[sid] <= EPS:
                    cash += pos.pop(sid)
                    mark.pop(sid, None)
            # buys
            fill_buys = []
            for sid, amt in buys:
                lim = data.limits.get((sid, d))
                lu = None if lim is None else lim.get("limit_up")
                op = data.raw_open(sid, d)
                if strict and lu is not None and op is not None and op >= lu:
                    res.unfilled_buys += 1
                    continue
                if data.adj_open(sid, d) is None:
                    if strict:
                        res.unfilled_buys += 1
                        continue
                    raise DataError(f"no adjusted open for {sid} on {d}")
                fill_buys.append((sid, amt))
            total = sum(a for _, a in fill_buys)
            if total > 0:
                scale = min(1.0, max(cash, 0.0) / (total * (1.0 + rb)))
                for sid, amt in fill_buys:
                    n = amt * scale
                    cost = n * rb
                    if sid not in pos:
                        mark[sid] = data.adj_open(sid, d)
                        pos[sid] = 0.0
                    pos[sid] += n
                    cash -= n + cost
                    day_cost += cost
                    res.turnover += n / nav_open
                    res.cost_frac += cost / nav_open
                    res.n_fills += 1
            for sid in list(pos):
                if pos[sid] <= EPS:
                    cash += pos.pop(sid)
                    mark.pop(sid, None)

        # 2. intraday, open to adjusted close
        for sid in pos:
            ac = data.adj_close(sid, d)
            if ac is not None and not final:
                pos[sid] *= ac / mark[sid]
                mark[sid] = ac
        nav = cash + sum(pos.values())
        res.dates.append(d)
        res.net.append(nav / nav_prev - 1.0)
        res.gross.append((nav + day_cost) / nav_prev - 1.0)
        nav_prev = nav
    return res


# ---------------------------------------------------------------- run


def _stats(sim: SimResult) -> dict:
    n = len(sim.net)
    years = n / ANNUALIZATION
    return {
        "total": metrics.total_return(sim.net),
        "annual": metrics.annual_return(sim.net),
        "vol": metrics.annual_vol(sim.net),
        "sharpe": metrics.sharpe_annual(sim.net),
        "gross_sharpe": metrics.sharpe_annual(sim.gross),
        "mdd": metrics.max_drawdown(sim.net),
        "turnover": sim.turnover / years,
        "cost_drag": sim.cost_frac / years,
    }


def _execute(data: DevData, books: list[TargetBook], window: str):
    ws, we = window_bounds(data.settings, window)
    if not books:
        raise BookError("no books")
    books = sorted(books, key=lambda b: b.decision_date)
    targets_by_day: dict[date, Weights] = {}
    dropped: list = []
    for b in books:
        check_book(b)
    seen = set()
    for b in books:
        if b.decision_date in seen:
            raise BookError(f"two books for decision date {b.decision_date}")
        seen.add(b.decision_date)
        if not (ws <= b.decision_date <= we):
            raise BookError(f"decision date {b.decision_date} outside window {window}")
        e = data.next_trading_day(b.decision_date)
        if e is None or e > we or e > data.end:
            raise BookError(f"book {b.decision_date}: execution day {e} outside window or data")
        if e in targets_by_day:
            raise BookError(f"two books execute on {e}")
        kept, drops = tradeable_targets(data, b, e)
        targets_by_day[e] = kept
        dropped.extend(drops)
    first = min(targets_by_day)
    limit = min(data.end, we)
    days = data.calendar.days_between(first, limit)
    if len(days) < 2 or days[0] != first:
        raise BookError("window holds fewer than two trading days after the first execution")
    strat = simulate(data, days, targets_by_day, strict=True)
    bench = simulate(data, days, {first: {BENCHMARK_ID: 1.0}}, strict=False)
    return books, days, strat, bench, dropped, (ws, we)


def run_backtest(
    data: DevData, books: list[TargetBook], *, card_id: str, params: dict, window: str
) -> RunRecord:
    cfg = data.settings.research
    log.check_budget(cfg)  # refused before any work; writes nothing
    run_id = str(uuid.uuid4())
    created = datetime.now(UTC).isoformat()
    sha = log.evaluator_sha256()
    ph = log.params_hash(params)
    try:
        books_s, days, strat, bench, dropped, (ws, we) = _execute(data, books, window)
        s, b = _stats(strat), _stats(bench)
        skew, kurt = metrics.skew_kurt(strat.net)
        rec = RunRecord(
            run_id=run_id,
            created_at=created,
            card_id=card_id,
            params_hash=ph,
            window=window,
            evaluator_sha256=sha,
            window_start=ws,
            window_end=we,
            first_execution=days[0],
            last_day=days[-1],
            n_days=len(days),
            n_books=len(books_s),
            n_fills=strat.n_fills,
            net_total_return=s["total"],
            net_annual_return=s["annual"],
            net_annual_vol=s["vol"],
            net_sharpe=s["sharpe"],
            gross_sharpe=s["gross_sharpe"],
            max_drawdown=s["mdd"],
            annual_turnover=s["turnover"],
            annual_turnover_one_way=s["turnover"] / 2.0,
            annual_cost_drag=s["cost_drag"],
            benchmark_net_total_return=b["total"],
            benchmark_net_annual_return=b["annual"],
            benchmark_net_annual_vol=b["vol"],
            benchmark_net_sharpe=b["sharpe"],
            benchmark_gross_sharpe=b["gross_sharpe"],
            benchmark_max_drawdown=b["mdd"],
            benchmark_annual_turnover=b["turnover"],
            benchmark_annual_cost_drag=b["cost_drag"],
            excess_annual_return=s["annual"] - b["annual"],
            hit_rate_monthly=metrics.hit_rate(strat.dates, strat.net, bench.net),
            unfilled_buys=strat.unfilled_buys,
            blocked_sells=strat.blocked_sells,
            forced_sells=strat.forced_sells,
            dropped_non_tradeable=len(dropped),
            dropped_detail=[list(x) for x in dropped],
            daily=list(zip(strat.dates, strat.net, bench.net, strict=True)),
        )
        line = rec.log_dict(params, cfg.cycle)
        done = log.append_ok(line, s["sharpe"], len(strat.net), skew, kurt)
        rec.n_trials = done["n_trials"]
        rec.deflated_sharpe = done["deflated_sharpe"]
        return rec
    except Exception as exc:
        log.append_error(
            {
                "status": "error",
                "run_id": run_id,
                "created_at": created,
                "card_id": card_id,
                "params": params,
                "params_hash": ph,
                "window": window,
                "cycle": cfg.cycle,
                "evaluator_sha256": sha,
                "error_type": type(exc).__name__,
                "message": str(exc),
            }
        )
        raise
