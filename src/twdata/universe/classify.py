"""Common-stock classification for the universe (design, section "Universe", rule 2)."""

from __future__ import annotations

import re

from twdata.common.parsing import clean_name

_COMMON_CODE = re.compile(r"^[1-9][0-9]{3}$")


def normalise_name(name: str) -> str:
    """Names are compared after `clean_name` (strip, one trailing `*`)."""
    return clean_name(name)


def is_common_stock(stock_id: str, stock_name: str) -> bool:
    """Four digits not starting with 0 (no ETFs, letter suffixes or six-digit codes) and a name
    that does not end with `-DR` (depositary receipts). `F-` and `KY` names are common stocks."""
    if not _COMMON_CODE.match(stock_id):
        return False
    return not normalise_name(stock_name).endswith("-DR")
