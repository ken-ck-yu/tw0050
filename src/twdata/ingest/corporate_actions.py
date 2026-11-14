"""Corporate actions: official ex-rights, ex-dividend and capital-reduction feeds plus the
manual file (Agent B, docs/specs/m2_agent_b.md).

Sources: TWSE TWT49U (ex-rights/dividend, one call for the span), TWSE TWTAUU (capital
reduction), TPEx exDailyQ (ex-rights/dividend) and TPEx revivt (capital reduction), the last
three in windows of one calendar year, and ``config/manual_corporate_actions.yaml``.
``available_at`` is the next trading day 08:30 after the event date.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import yaml

from twdata.clients.base import DriftError
from twdata.common import state
from twdata.common.config import repo_root
from twdata.common.parsing import ParseError, parse_number
from twdata.common.timeutil import avail_next_day_0830, roc_to_date

log = logging.getLogger(__name__)

TABLE = "corporate_actions"
MANUAL_ACTION_TYPES = ("split", "par_value_change", "ex_dividend", "ex_rights", "capital_reduction")
# Tests point this at a temporary file; None means config/manual_corporate_actions.yaml.
MANUAL_PATH: Path | None = None


@dataclass
class Stats:
    """Counts of one collection pass, reported in the run report."""

    per_source: dict[str, int] = field(default_factory=dict)
    collisions: int = 0


def manual_path() -> Path:
    return MANUAL_PATH or repo_root() / "config" / "manual_corporate_actions.yaml"


# ---- cell helpers -----------------------------------------------------------------


def _get(rec: dict, name: str, source: str):
    if name not in rec:
        raise DriftError(f"{source}: field {name!r} missing from the response")
    return rec[name]


def _num(rec: dict, name: str, source: str) -> float | None:
    v = _get(rec, name, source)
    return None if v is None else parse_number(str(v))


def _text(rec: dict, name: str, source: str) -> str:
    return str(_get(rec, name, source)).strip()


def _stock(rec: dict, name: str, source: str) -> str:
    sid = _text(rec, name, source)
    if not sid:
        raise ParseError(f"{source}: empty stock id")
    return sid


def action_from_mark(text: str) -> str:
    """The 權/息 cell. TWSE: 權 or 息. TPEx: 除權, 除息 or 除權息. Both marks mean ex_rights."""
    s = text.strip()
    if s in ("權", "除權", "權息", "除權息"):
        return "ex_rights"
    if s in ("息", "除息"):
        return "ex_dividend"
    raise ParseError(f"unknown 權/息 cell {text!r}")


def parse_event_date(text: str) -> date:
    """7-digit or slashed ROC date, the TWT49U `104年06月01日` form, or YYYYMMDD."""
    s = str(text).strip()
    if re.fullmatch(r"\d{8}", s):
        return date(int(s[:4]), int(s[4:6]), int(s[6:]))
    return roc_to_date(s)


def year_windows(start: date, end: date):
    for y in range(start.year, end.year + 1):
        yield max(start, date(y, 1, 1)), min(end, date(y, 12, 31))


def _fetched(resp) -> datetime:
    return resp.fetched_at or datetime.now(UTC)


def _row(**kw) -> dict:
    base = {
        "prev_close": None,
        "reference_price": None,
        "halt_close": None,
        "ratio": None,
        "cash_dividend": None,
        "stock_dividend_per_1000": None,
        "reduction_reason": None,
    }
    base.update(kw)
    return base


# ---- the four feeds ---------------------------------------------------------------


def parse_twt49u(records: list[dict]) -> list[dict]:
    """TWT49U gives `權值+息值` (the sum), not the cash dividend or the stock dividend, so
    cash_dividend and stock_dividend_per_1000 stay null."""
    src = "twse.twt49u"
    out = []
    for r in records:
        out.append(
            _row(
                market="TWSE",
                stock_id=_stock(r, "股票代號", src),
                event_date=parse_event_date(_text(r, "資料日期", src)),
                action_type=action_from_mark(_text(r, "權/息", src)),
                prev_close=_num(r, "除權息前收盤價", src),
                reference_price=_num(r, "除權息參考價", src),
            )
        )
    return out


def parse_twtauu(records: list[dict]) -> list[dict]:
    src = "twse.twtauu"
    out = []
    for r in records:
        halt = _num(r, "停止買賣前收盤價格", src)
        out.append(
            _row(
                market="TWSE",
                stock_id=_stock(r, "股票代號", src),
                event_date=parse_event_date(_text(r, "恢復買賣日期", src)),
                action_type="capital_reduction",
                prev_close=halt,
                halt_close=halt,
                reference_price=_num(r, "恢復買賣參考價", src),
                reduction_reason=_text(r, "減資原因", src) or None,
            )
        )
    return out


def parse_ex_daily(records: list[dict]) -> list[dict]:
    src = "tpex.ex_daily"
    out = []
    for r in records:
        out.append(
            _row(
                market="TPEx",
                stock_id=_stock(r, "代號", src),
                event_date=parse_event_date(_text(r, "除權息日期", src)),
                action_type=action_from_mark(_text(r, "權/息", src)),
                prev_close=_num(r, "除權息前收盤價", src),
                reference_price=_num(r, "除權息參考價", src),
                cash_dividend=_num(r, "現金股利", src),
                stock_dividend_per_1000=_num(r, "每仟股無償配股", src),
            )
        )
    return out


def parse_revivt(records: list[dict]) -> list[dict]:
    src = "tpex.revivt"
    out = []
    for r in records:
        halt = _num(r, "最後交易日之收盤價格", src)
        out.append(
            _row(
                market="TPEx",
                stock_id=_stock(r, "股票代號", src),
                event_date=parse_event_date(_text(r, "恢復買賣日期", src)),
                action_type="capital_reduction",
                prev_close=halt,
                halt_close=halt,
                reference_price=_num(r, "減資恢復買賣開始日參考價格", src),
                reduction_reason=_text(r, "減資原因", src) or None,
            )
        )
    return out


# ---- the manual file --------------------------------------------------------------


def _opt_float(v, name: str) -> float | None:
    if v is None:
        return None
    if isinstance(v, bool) or not isinstance(v, int | float):
        raise ParseError(f"manual corporate action: {name} is not a number: {v!r}")
    return float(v)


def load_manual(path: Path) -> tuple[list[dict], datetime | None]:
    """Rows of the manual file and its modification time (UTC); ([], None) if absent."""
    if not path.exists():
        return [], None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    if doc is None:
        return [], mtime
    if not isinstance(doc, list):
        raise ParseError("manual corporate actions file must be a list of entries")
    out = []
    for e in doc:
        for k in ("market", "stock_id", "action_type", "event_date"):
            if e.get(k) is None:
                raise ParseError(f"manual corporate action without {k}: {e!r}")
        if e["market"] not in ("TWSE", "TPEx"):
            raise ParseError(f"manual corporate action: bad market {e['market']!r}")
        if e["action_type"] not in MANUAL_ACTION_TYPES:
            raise ParseError(f"manual corporate action: bad action_type {e['action_type']!r}")
        if not isinstance(e["event_date"], date):
            raise ParseError(f"manual corporate action: event_date is not a date: {e!r}")
        halt = _opt_float(e.get("halt_close"), "halt_close")
        prev = _opt_float(e.get("prev_close"), "prev_close")
        out.append(
            _row(
                market=e["market"],
                stock_id=str(e["stock_id"]).strip(),
                event_date=e["event_date"],
                action_type=e["action_type"],
                prev_close=prev if prev is not None else halt,
                halt_close=halt,
                reference_price=_opt_float(e.get("reference_price"), "reference_price"),
                ratio=_opt_float(e.get("ratio"), "ratio"),
            )
        )
    return out, mtime


# ---- collection -------------------------------------------------------------------


def _key(r: dict) -> tuple:
    return (r["market"], r["stock_id"], r["event_date"], r["action_type"])


def dedupe(rows: list[dict]) -> tuple[list[dict], int]:
    """One row per key; the first row in response order wins. Returns the rows and the number
    of dropped rows."""
    best: dict[tuple, dict] = {}
    dropped = 0
    for r in rows:
        k = _key(r)
        if k in best:
            dropped += 1
        else:
            best[k] = r
    return list(best.values()), dropped


def _avail(ctx, d: date) -> datetime | None:
    """Next trading day 08:30; null (pending, filled by a later run) without a calendar."""
    return None if ctx.calendar is None else avail_next_day_0830(d, ctx.calendar)


def collect(ctx, start: date, end: date) -> tuple[list[dict], Stats]:
    """Fetch every source and return the rows to write. Nothing is written here."""
    stats = Stats()
    rows: list[dict] = []

    def add(source: str, parsed: list[dict], resp) -> None:
        fetched = _fetched(resp)
        for r in parsed:
            r["fetched_at"] = fetched
            r["available_at"] = _avail(ctx, r["event_date"])
        stats.per_source[source] = stats.per_source.get(source, 0) + len(parsed)
        rows.extend(parsed)

    recs, resp = ctx.twse.twt49u(start, end)
    add("twt49u", parse_twt49u(recs), resp)
    for ws, we in year_windows(start, end):
        recs, resp = ctx.twse.twtauu(ws, we)
        add("twtauu", parse_twtauu(recs), resp)
        recs, resp = ctx.tpex.ex_daily(ws, we)
        add("ex_daily", parse_ex_daily(recs), resp)
        recs, resp = ctx.tpex.revivt(ws, we)
        add("revivt", parse_revivt(recs), resp)

    manual, mtime = load_manual(manual_path())
    manual = [r for r in manual if start <= r["event_date"] <= end]
    for r in manual:
        r["fetched_at"] = mtime
        r["available_at"] = _avail(ctx, r["event_date"])
    stats.per_source["manual"] = len(manual)
    rows.extend(manual)

    rows, stats.collisions = dedupe(rows)
    if stats.collisions:
        log.warning("corporate_actions: %d rows shared a key and were collapsed", stats.collisions)
    return rows, stats


def run(ctx, start: date, end: date) -> None:
    rows, stats = collect(ctx, start, end)
    ctx.writers(TABLE).append(rows)
    ctx.cache.flush()
    state.mark_dates(ctx.settings, TABLE, start, end)
    log.info(
        "corporate_actions %s..%s: %s, collisions %d",
        start,
        end,
        stats.per_source,
        stats.collisions,
    )


DATASETS = {"corporate_actions": run}
