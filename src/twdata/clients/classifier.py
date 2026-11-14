"""Response classification: ok, transient or drift (spec section 8)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date as Date

from twdata.clients.transport import HttpResult
from twdata.common.endpoints import EndpointSpec
from twdata.common.schema import fields_valid

NO_DATA_PHRASES = ("很抱歉", "查詢無資料")


@dataclass(frozen=True)
class Result:
    klass: str  # ok | transient | drift
    reason: str
    rows: int = 0


class ShapeError(Exception):
    """The body does not have the shape the endpoint spec promises."""


def decode_json(body: bytes):
    """Return parsed JSON, or raise ValueError (HTML, bad UTF-8 or invalid JSON)."""
    text = body.decode("utf-8")  # UnicodeDecodeError is a ValueError
    if text.lstrip("﻿ \t\r\n").startswith("<"):
        raise ValueError("html body")
    return json.loads(text)


def extract(spec: EndpointSpec, parsed) -> tuple[list, list | None]:
    """Return (rows, fields) through the spec's rows path. Raises ShapeError."""
    if spec.kind == "snapshot" and spec.host != "finmind":
        if not isinstance(parsed, list):
            raise ShapeError("snapshot body is not a JSON list")
        return parsed, None
    if not isinstance(parsed, dict):
        raise ShapeError("body is not a JSON object")
    if spec.host == "finmind":
        data = parsed.get("data")
        if data is None and spec.key == "finmind.user_info":
            return [parsed], None
        if not isinstance(data, list):
            raise ShapeError("finmind body has no data list")
        return data, None
    if spec.tables_key:
        tables = parsed.get(spec.tables_key)
        if not isinstance(tables, list):
            raise ShapeError(f"no {spec.tables_key} list")
        if spec.table_selector:
            hits = [
                t
                for t in tables
                if isinstance(t, dict) and spec.table_selector in str(t.get("title", ""))
            ]
            if not hits:
                if not tables:
                    return [], None
                raise ShapeError(f"no table whose title contains {spec.table_selector}")
            table = hits[0]
        else:
            if not tables:
                return [], None
            table = tables[0]
        if not isinstance(table, dict):
            raise ShapeError("table is not an object")
    else:
        table = parsed
    rows = table.get("data")
    if not isinstance(rows, list):
        raise ShapeError("no data list")
    fields = table.get("fields")
    if fields is not None and not isinstance(fields, list):
        raise ShapeError("fields is not a list")
    return rows, fields


def _is_no_data_body(parsed) -> bool:
    """TWSE no-data reply: a stat message and no rows (extra keys allowed)."""
    return (
        isinstance(parsed, dict)
        and "data" not in parsed
        and "tables" not in parsed
        and isinstance(parsed.get("stat"), str)
        and any(p in parsed["stat"] for p in NO_DATA_PHRASES)
    )


def _calendar_says(calendar, d: Date | None) -> bool | None:
    """True trading day, False non-trading day, None when the calendar does not cover d."""
    if calendar is None or d is None:
        return None
    covers = getattr(calendar, "covers", None)
    if covers is not None and not covers(d):
        return None
    try:
        return bool(calendar.is_trading(d))
    except Exception:
        return None


def classify(
    spec: EndpointSpec,
    result: HttpResult,
    *,
    date: Date | None = None,
    calendar=None,
    allow_empty: bool = False,
) -> Result:
    """Classify one response. `allow_empty` accepts zero rows on a per_date call."""
    st = result.status
    if st == 0 or st == 429 or 500 <= st <= 599:
        return Result("transient", f"http {st}")
    if st == 302:
        return Result("drift", "http 302 redirect")
    if st != 200:
        return Result("drift", f"http {st}")
    if spec.host in ("twse", "tpex") and "網站維護中".encode() in result.body[:4096]:
        return Result("transient", "site maintenance page")
    try:
        parsed = decode_json(result.body)
    except ValueError as e:
        return Result("drift", f"200 with non-JSON body ({type(e).__name__})")

    verdict = _calendar_says(calendar, date)
    if spec.stat_ok is not None and isinstance(parsed, dict) and "stat" in parsed:
        if parsed["stat"] != spec.stat_ok:
            if spec.kind in ("range", "stock_month") and _is_no_data_body(parsed):
                return Result("ok", "known no-data reply", 0)
            if spec.kind == "per_date" and verdict is False:
                return Result("ok", "non-OK stat on a non-trading day", 0)
            if spec.kind == "per_date" and allow_empty and _is_no_data_body(parsed):
                return Result("ok", "known no-data reply (allow_empty)", 0)
            return Result("drift", f"stat {parsed['stat']!r} != {spec.stat_ok!r}")
    if spec.host == "finmind" and isinstance(parsed, dict) and spec.key != "finmind.user_info":
        if parsed.get("status") != 200:
            return Result("drift", f"in-body status {parsed.get('status')!r}")

    try:
        rows, fields = extract(spec, parsed)
    except ShapeError as e:
        return Result("drift", f"shape: {e}")

    if fields and not fields_valid(spec.key, date, fields):
        return Result("drift", "field list matches no era valid on the date")
    if rows and spec.tables_key is not None and fields is None:
        return Result("drift", "rows without a field list")

    n = len(rows)
    if n == 0 and spec.kind == "per_date":
        if verdict is False:
            return Result("ok", "empty on a non-trading day", 0)
        if allow_empty:
            return Result("ok", "empty (allow_empty)", 0)
        if verdict is True:
            return Result("drift", "zero rows on a trading day", 0)
        return Result("drift", "zero rows and no calendar coverage for the date", 0)
    return Result("ok", "ok", n)
