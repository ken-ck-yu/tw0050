"""One place to import every project exception (each is defined where it is raised)."""

from twdata.clients.base import AuthError, BlockedError, DriftError, RetryExhausted
from twdata.common.cleanstore import KeyUniquenessError, PointInTimeError
from twdata.common.config import ConfigError
from twdata.common.parsing import ParseError
from twdata.common.sanity import SanityError
from twdata.common.tradingcal import CalendarRangeError

EXIT_CODES = {
    BlockedError: 3,
    AuthError: 3,
    RetryExhausted: 3,
    DriftError: 4,
    SanityError: 4,
    ParseError: 4,
    ConfigError: 5,
    CalendarRangeError: 5,
    KeyUniquenessError: 5,
    PointInTimeError: 5,
}


def exit_code_for(exc: BaseException) -> int:
    for cls, code in EXIT_CODES.items():
        if isinstance(exc, cls):
            return code
    return 5


__all__ = [
    "AuthError",
    "BlockedError",
    "CalendarRangeError",
    "ConfigError",
    "DriftError",
    "KeyUniquenessError",
    "ParseError",
    "PointInTimeError",
    "RetryExhausted",
    "SanityError",
    "EXIT_CODES",
    "exit_code_for",
]
