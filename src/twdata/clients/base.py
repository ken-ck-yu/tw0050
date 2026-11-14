"""Generic client: cache first, limiter slot, classification, retries (spec section 8).

Never stores, logs or raises request headers. Only `ok` responses are cached, `drift`
responses are quarantined, `transient` responses are not stored.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from datetime import date as Date

from twdata.clients.classifier import Result, ShapeError, classify, decode_json, extract
from twdata.clients.transport import HttpResult, Transport
from twdata.common.config import Settings
from twdata.common.endpoints import ENDPOINTS, EndpointSpec, build_request

log = logging.getLogger(__name__)


class BlockedError(Exception):
    """The host refuses us (FinMind non-auth 4xx, TWSE or TPEx 403). Exit 3."""


class AuthError(Exception):
    """FinMind token or permission problem. Exit 3."""


class DriftError(Exception):
    """The response is not what the contract promises. Exit 4."""


class RetryExhausted(Exception):
    """All attempts returned transient failures. Exit 3."""


def request_key(method: str, url: str, params: dict) -> str:
    """Same formula as rawcache.request_key (spec section 8); kept here so base has no
    import-time dependency on rawcache. No headers or credentials enter the key."""
    text = method + "\n" + url + "\n" + json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unique_field_names(fields) -> list[str]:
    """Strip whitespace; blank names become col<i>; repeats get #2, #3 (deterministic)."""
    seen: dict[str, int] = {}
    out: list[str] = []
    for i, f in enumerate(fields):
        name = "".join(str(f).split()) or f"col{i}"
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name}#{seen[name]}")
    return out


@dataclass
class Response:
    klass: str
    rows: list  # raw rows (lists, or dicts for OpenAPI and FinMind)
    body: bytes
    parsed: object
    from_cache: bool = False
    fields: list | None = None
    reason: str = ""
    fetched_at: datetime | None = None

    @property
    def records(self) -> list[dict]:
        """Rows as dicts keyed by field name (dict rows are returned as they are).

        Field names are stripped of whitespace. A blank name becomes ``col<i>`` and a repeated
        name gets ``#2``, ``#3`` and so on, so no column is silently dropped.
        """
        names = unique_field_names(self.fields) if self.fields is not None else None
        out = []
        for r in self.rows:
            if isinstance(r, dict):
                out.append(r)
            elif names is not None:
                out.append(dict(zip(names, r, strict=False)))
            else:
                raise DriftError("rows are lists but the response has no field list")
        return out


@dataclass
class _Ctx:
    spec: EndpointSpec
    url: str
    params: dict
    key: str
    dataset: str
    calendar: object = None
    date: Date | None = None
    allow_empty: bool = False
    extra: dict = field(default_factory=dict)


class Client:
    def __init__(
        self,
        settings: Settings,
        host: str,
        limiter,
        cache,
        transport: Transport,
        headers_for: Callable[[], dict] | None = None,
        *,
        calendar=None,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] | None = None,
    ):
        self.settings = settings
        self.host = host
        self.limiter = limiter
        self.cache = cache
        self.transport = transport
        self.headers_for = headers_for
        self.calendar = calendar
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(UTC))

    # ---- helpers -----------------------------------------------------------------

    def _timeout(self) -> float:
        return float(getattr(self.settings.timeout_s, self.host))

    def _row_cap(self, dataset: str) -> int:
        caps = self.settings.row_caps
        if dataset in caps.datasets:
            return int(caps.datasets[dataset])
        if self.host == "finmind":
            return int(caps.finmind_default)
        return int(getattr(caps, self.host))

    def _resolve(self, endpoint) -> EndpointSpec:
        return endpoint if isinstance(endpoint, EndpointSpec) else ENDPOINTS[endpoint]

    def _headers(self, extra_headers: dict | None) -> dict:
        h = {"User-Agent": self.settings.user_agent}
        if self.headers_for is not None:
            h.update(self.headers_for())
        if extra_headers:
            h.update(extra_headers)
        return h

    def _precheck(self, spec: EndpointSpec, result: HttpResult) -> HttpResult:
        """TWSE and TPEx: a 403 raises BlockedError before classification. FinMind overrides."""
        if self.host in ("twse", "tpex") and result.status == 403:
            raise BlockedError(f"{self.host} answered HTTP 403")
        return result

    def _build_response(
        self, spec, parsed, res: Result, body: bytes, from_cache: bool, fetched_at=None
    ) -> Response:
        try:
            rows, fields = extract(spec, parsed)
        except ShapeError:
            if res.rows:
                raise
            rows, fields = [], None  # an ok-empty no-data reply has no rows path
        return Response(res.klass, rows, body, parsed, from_cache, fields, res.reason, fetched_at)

    # ---- main entry --------------------------------------------------------------

    def fetch(
        self,
        endpoint,
        params: dict,
        *,
        date: Date | None = None,
        use_cache: bool = True,
        extra_headers: dict | None = None,
        allow_empty: bool = False,
        store: bool = True,
        dataset: str | None = None,
        calendar=None,
    ) -> Response:
        spec = self._resolve(endpoint)
        cal = calendar if calendar is not None else self.calendar
        ds = dataset or spec.dataset
        url = spec.url
        key = request_key("GET", url, params)

        def cls(result: HttpResult) -> Result:
            return classify(spec, result, date=date, calendar=cal, allow_empty=allow_empty)

        if use_cache:
            hit = self.cache.get(spec.host, ds, key)
            if hit is not None:
                res = cls(HttpResult(200, {}, hit.body))
                if res.klass == "ok":
                    self._check_cap(ds, res.rows, key)
                    return self._build_response(
                        spec, decode_json(hit.body), res, hit.body, True, hit.fetched_at
                    )

        waits = tuple(self.settings.retry_waits_s)
        attempts = len(waits) + 1
        last = ""
        for attempt in range(attempts):
            with self.limiter.slot():
                result = self.transport(
                    "GET", url, params, self._headers(extra_headers), self._timeout()
                )
            result = self._precheck(spec, result)
            res = cls(result)
            fetched_at = self._now()
            if res.klass == "ok":
                self._check_cap(
                    ds, res.rows, key, quarantine=(spec, url, params, result, fetched_at)
                )
                if store:
                    self.cache.put(
                        spec.host, ds, key, url, params, result.status, result.body, fetched_at
                    )
                return self._build_response(
                    spec, decode_json(result.body), res, result.body, False, fetched_at
                )
            if res.klass == "drift":
                self._quarantine(spec, ds, key, url, params, result, fetched_at, res.reason)
                raise DriftError(f"{spec.key}: {res.reason}")
            last = res.reason
            log.warning(
                "%s transient (%s), attempt %d of %d", spec.key, last, attempt + 1, attempts
            )
            if attempt < len(waits):
                self._sleep(waits[attempt])
        raise RetryExhausted(f"{spec.key}: {attempts} attempts failed, last: {last}")

    def _quarantine(self, spec, ds, key, url, params, result, fetched_at, reason) -> None:
        self.cache.put_quarantine(
            spec.host,
            ds,
            key,
            url,
            params,
            result.status,
            result.body,
            fetched_at,
        )
        log.warning("%s quarantined: %s", spec.key, reason)

    def _check_cap(self, ds: str, n: int, key: str, quarantine=None) -> None:
        cap = self._row_cap(ds)
        if n > cap:
            if quarantine is not None:
                spec, url, params, result, fetched_at = quarantine
                reason = f"{n} rows exceed the cap {cap}"
                self._quarantine(spec, ds, key, url, params, result, fetched_at, reason)
            raise DriftError(f"{ds}: {n} rows exceed the row cap {cap}")

    def per_date(self, endpoint, on: Date, **kw) -> Response:
        """Fetch a per_date endpoint for one date (builds the request from ENDPOINTS)."""
        spec = self._resolve(endpoint)
        _, params = build_request(spec, on=on)
        return self.fetch(spec, params, date=on, **kw)
