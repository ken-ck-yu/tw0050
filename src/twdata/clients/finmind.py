"""FinMind client (spec section 8). The token is read from the environment at call time and
goes only into the request headers handed to the transport."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, replace
from datetime import date as Date

from twdata.clients.base import AuthError, BlockedError, Client
from twdata.clients.classifier import decode_json
from twdata.clients.transport import HttpResult
from twdata.common.endpoints import EndpointSpec

DATA_URL = "https://api.finmindtrade.com/api/v4/data"
USER_INFO_URL = "https://api.web.finmindtrade.com/v2/user_info"

DATA_SPEC = EndpointSpec("finmind.data", "finmind", "range", DATA_URL, "", {}, dataset="data")
USER_INFO_SPEC = EndpointSpec(
    "finmind.user_info", "finmind", "snapshot", USER_INFO_URL, "", {}, dataset="user_info"
)


@dataclass(frozen=True)
class QuotaInfo:
    level: str
    limit: int
    user_count: int


def _token_headers() -> dict:
    token = os.environ.get("FINMIND_TOKEN")
    if not token:
        raise AuthError("FINMIND_TOKEN is not set")
    return {"Authorization": f"Bearer {token}"}


class FinMindClient(Client):
    def __init__(
        self,
        settings,
        limiter,
        cache,
        transport,
        *,
        calendar=None,
        sleep=time.sleep,
        now=None,
    ):
        super().__init__(
            settings,
            "finmind",
            limiter,
            cache,
            transport,
            headers_for=_token_headers,
            calendar=calendar,
            sleep=sleep,
            now=now,
        )
        self._calls = 0

    # ---- error mapping -----------------------------------------------------------

    def _precheck(self, spec: EndpointSpec, result: HttpResult) -> HttpResult:
        st = result.status
        if st == 0 or 500 <= st <= 599:
            return result  # transient, handled by the classifier
        body_status = None
        if st == 200:
            try:
                parsed = decode_json(result.body)
            except ValueError:
                return result  # the classifier calls it drift
            if isinstance(parsed, dict) and isinstance(parsed.get("status"), int):
                body_status = parsed["status"]
            if body_status is None or body_status == 200:
                return result
            if 500 <= body_status <= 599:
                return HttpResult(body_status, result.headers, result.body)
            effective = body_status
        else:
            effective = st
        if effective == 302 or effective < 400:
            return result  # classifier: drift
        if effective in (400, 401):
            raise AuthError(f"FinMind refused the token or request (status {effective})")
        raise BlockedError(f"FinMind answered status {effective}")

    # ---- API ---------------------------------------------------------------------

    def user_info(self) -> QuotaInfo:
        resp = self.fetch(USER_INFO_SPEC, {}, use_cache=False, store=False)
        info = resp.parsed
        out = QuotaInfo(
            str(info.get("level_title", "")),
            int(info["api_request_limit"]),
            int(info["user_count"]),
        )
        update = getattr(self.limiter, "update", None)
        if update is not None:
            update(out.limit, out.user_count)
        return out

    def dataset(
        self,
        name: str,
        start: Date,
        end: Date | None = None,
        data_id: str | None = None,
    ) -> list[dict]:
        params = {"dataset": name, "start_date": start.isoformat()}
        if end is not None:
            params["end_date"] = end.isoformat()
        if data_id is not None:
            params["data_id"] = data_id
        spec = replace(DATA_SPEC, key=f"finmind.{name}", dataset=name)
        resp = self.fetch(spec, params, dataset=name)
        self._calls += 1
        every = self.settings.finmind.user_info_refresh_requests
        if every and self._calls % every == 0:
            self.user_info()
        return resp.records
