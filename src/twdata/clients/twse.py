"""TWSE client: one method per endpoint (spec section 6). Rows are returned as dicts keyed
by field name; ROC date cells stay strings."""

from __future__ import annotations

import time
from datetime import date as Date

from twdata.clients.base import Client, Response
from twdata.common.endpoints import ENDPOINTS, build_request, openapi_spec


class TwseClient(Client):
    def __init__(
        self, settings, limiter, cache, transport, *, calendar=None, sleep=time.sleep, now=None
    ):
        super().__init__(
            settings, "twse", limiter, cache, transport, calendar=calendar, sleep=sleep, now=now
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
        spec = openapi_spec("twse", path)
        _, params = build_request(spec)
        resp = self.fetch(spec, params)
        return resp.records, resp

    def mi_index(self, d: Date, *, allow_empty: bool = False):
        return self._call("twse.mi_index", on=d, allow_empty=allow_empty)

    def mi_index_tr(self, d: Date, *, allow_empty: bool = False):
        """The index table of the same MI_INDEX request (served from the cache)."""
        return self._call("twse.mi_index_tr", on=d, allow_empty=allow_empty)

    def mi_qfiis(self, d: Date, *, allow_empty: bool = False):
        return self._call("twse.mi_qfiis", on=d, allow_empty=allow_empty)

    def twt84u(self, d: Date, *, allow_empty: bool = False):
        return self._call("twse.twt84u", on=d, allow_empty=allow_empty)

    def bwibbu_d(self, d: Date, *, allow_empty: bool = False):
        return self._call("twse.bwibbu_d", on=d, allow_empty=allow_empty)

    def stock_day(self, month_day: Date, stock_no: str):
        return self._call("twse.stock_day", on=month_day, stockNo=stock_no)

    def twt49u(self, start: Date, end: Date):
        return self._call("twse.twt49u", start=start, end=end)

    def twtauu(self, start: Date, end: Date):
        return self._call("twse.twtauu", start=start, end=end)

    def twtawu(self, start: Date, end: Date):
        return self._call("twse.twtawu", start=start, end=end)

    def punish(self, start: Date, end: Date):
        return self._call("twse.punish", start=start, end=end)

    def notice(self, start: Date, end: Date):
        return self._call("twse.notice", start=start, end=end)
