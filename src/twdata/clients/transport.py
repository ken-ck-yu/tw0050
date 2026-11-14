"""HTTP transport. The only place that talks to `requests` (spec section 8)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from twdata.common.config import Settings


@dataclass(frozen=True)
class HttpResult:
    """Response status, RESPONSE headers and raw body bytes."""

    status: int
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes = b""


# (method, url, params, request headers, timeout seconds) -> HttpResult
Transport = Callable[[str, str, dict, dict, float], HttpResult]


def requests_transport(
    method: str, url: str, params: dict, headers: dict, timeout: float
) -> HttpResult:
    """Real transport: no redirects, TLS verified, connection or timeout errors give status 0."""
    import requests

    try:
        r = requests.request(
            method,
            url,
            params=params,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
            verify=True,
        )
    except requests.RequestException:
        return HttpResult(0, {}, b"")
    return HttpResult(r.status_code, dict(r.headers), r.content)


def default_transport(settings: Settings) -> Transport:
    """requests transport that adds the settings User-Agent when the caller sent none."""

    def send(method: str, url: str, params: dict, headers: dict, timeout: float) -> HttpResult:
        h = dict(headers)
        if not any(k.lower() == "user-agent" for k in h):
            h["User-Agent"] = settings.user_agent
        return requests_transport(method, url, params, h, timeout)

    return send
