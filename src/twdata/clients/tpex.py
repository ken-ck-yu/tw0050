"""TPEx client: one method per endpoint (spec section 6). Rows are returned as dicts keyed
by field name; ROC date cells stay strings."""

from __future__ import annotations

import time
from datetime import date as Date

from twdata.clients.base import Client, Response
from twdata.common.endpoints import ENDPOINTS, build_request, openapi_spec


class TpexClient(Client):
    def __init__(
        self, settings, limiter, cache, transport, *, calendar=None, sleep=time.sleep, now=None
    ):
        super().__init__(
            settings, "tpex", limiter, cache, transport, calendar=calendar, sleep=sleep, now=now
        )

    def _call(
        self, key, *, on=None, start=None, end=None, allow_empty=False, **extra
    ) -> tuple[list[dict], Response]:
        spec = ENDPOINTS[key]
        _, params = build_request(spec, on=on, start=start, end=end, **extra)
        era_date = on if on is not None else start
        resp = self.fetch(spec, params, date=era_date, allow_empty=allow_empty)
        return resp.records, resp

    def openapi(self, path: str) -> tuple[list[dict], Response]:
        spec = openapi_spec("tpex", path)
        _, params = build_request(spec)
        resp = self.fetch(spec, params)
        return resp.records, resp

    def otc(self, d: Date, *, allow_empty: bool = False):
        return self._call("tpex.otc", on=d, allow_empty=allow_empty)

    def chtm(self, d: Date, *, allow_empty: bool = False):
        return self._call("tpex.chtm", on=d, allow_empty=allow_empty)

    def ex_daily(self, start: Date, end: Date):
        return self._call("tpex.ex_daily", start=start, end=end)

    def revivt(self, start: Date, end: Date):
        return self._call("tpex.revivt", start=start, end=end)

    def disposal(self, start: Date, end: Date):
        return self._call("tpex.disposal", start=start, end=end)

    def attention(self, start: Date, end: Date):
        return self._call("tpex.attention", start=start, end=end)

    def trading_stock(self, month_day: Date, code: str):
        return self._call("tpex.trading_stock", on=month_day, code=code)

    def deListed(self, year_day: Date):  # noqa: N802 - name fixed by the spec
        """Delistings of the calendar year containing `year_day`."""
        return self._call("tpex.deListed", on=year_day)
