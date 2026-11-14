"""Cell parsing. Unparseable non-empty text raises ParseError; empty markers give None."""

from __future__ import annotations

import re


class ParseError(ValueError):
    pass


_EMPTY = {"", "--", "-", "N/A"}
_NUM = re.compile(r"^[+-]?\d+(?:\.\d+)?$")
_TAG = re.compile(r"<[^>]*>")


def _squash(text: str) -> str:
    return re.sub(r"\s+", "", text.replace(",", ""))


def strip_tags(text: str) -> str:
    return _TAG.sub("", text)


def parse_number(text: str) -> float | None:
    s = _squash(text)
    if s in _EMPTY or re.fullmatch(r"X\d*\.?\d*", s):
        return None
    if not _NUM.match(s):
        raise ParseError(f"not a number: {text!r}")
    return float(s)


def parse_int(text: str) -> int | None:
    v = parse_number(text)
    if v is None:
        return None
    if v != int(v):
        raise ParseError(f"not an integer: {text!r}")
    return int(v)


def clean_name(text: str) -> str:
    s = text.strip(" \t\r\n　")
    return s[:-1] if s.endswith("*") else s


def parse_sign(cell: str) -> int | None:
    """MI_INDEX up/down cell. '+' is +1, '-' is -1, blank is 0, 'X' is None (ex-rights/dividend)."""
    s = strip_tags(cell).strip()
    if s == "+":
        return 1
    if s == "-":
        return -1
    if s == "":
        return 0
    if s == "X":
        return None
    raise ParseError(f"unknown sign cell: {cell!r}")
