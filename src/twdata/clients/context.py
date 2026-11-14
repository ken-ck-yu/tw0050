"""Run context: limiters, caches, clients and writer factory (spec section 8)."""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from twdata.common import paths
from twdata.common.config import Settings


@dataclass
class RunContext:
    settings: Settings
    calendar: Any
    twse: Any
    tpex: Any
    finmind: Any
    cache: Any
    writers: Callable[[str], Any]


def build_context(
    settings: Settings,
    transport=None,
    finmind: bool = False,
    *,
    limiter_factory=None,
    cache_factory=None,
    writers=None,
    calendar=None,
    sleep=time.sleep,
) -> RunContext:
    """Build everything for an ingest run. Limiter, rawcache and cleanstore are imported here,
    not at module import. The factories exist so tests can inject fakes."""
    from twdata.clients.finmind import FinMindClient
    from twdata.clients.tpex import TpexClient
    from twdata.clients.transport import default_transport
    from twdata.clients.twse import TwseClient

    if transport is None:
        transport = default_transport(settings)

    if limiter_factory is None:
        from twdata.clients.limiter import HostLimiter, QuotaLimiter

        def limiter_factory(host: str):
            if host == "finmind":
                return QuotaLimiter(
                    600,
                    settings.finmind.target_fraction,
                    paths.host_state_file(settings, host),
                    paths.host_lock_file(settings, host),
                )
            return HostLimiter(
                host,
                getattr(settings.spacing_s, host),
                paths.host_lock_file(settings, host),
                paths.host_state_file(settings, host),
            )

    if cache_factory is None:
        from twdata.clients.rawcache import RawCache

        def cache_factory():
            return RawCache(settings)

    if writers is None:

        def writers(table: str):
            from twdata.common.cleanstore import CleanWriter

            return CleanWriter(settings, table)

    if calendar is None:
        calendar = _load_calendar(settings)

    cache = cache_factory()
    tw = TwseClient(
        settings, limiter_factory("twse"), cache, transport, calendar=calendar, sleep=sleep
    )
    tp = TpexClient(
        settings, limiter_factory("tpex"), cache, transport, calendar=calendar, sleep=sleep
    )
    fm = None
    if finmind:
        fm = FinMindClient(
            settings, limiter_factory("finmind"), cache, transport, calendar=calendar, sleep=sleep
        )
        fm.user_info()
    return RunContext(settings, calendar, tw, tp, fm, cache, writers)


def _load_calendar(settings: Settings):
    """Load the trading calendar when its clean table exists, else None."""
    if not (settings.data_dir / "clean" / "trading_calendar").exists():
        return None
    from twdata.common import tradingcal

    loader = getattr(tradingcal, "load_calendar", None)
    return loader(settings) if loader else None
