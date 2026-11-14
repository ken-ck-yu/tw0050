"""Endpoint table (docs/specs/m0_specs.md section 6) and request construction."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

TWSE_BASE = "https://www.twse.com.tw/rwd/zh/"
TWSE_OPENAPI = "https://openapi.twse.com.tw/v1"
TPEX_BASE = "https://www.tpex.org.tw/www/zh-tw/"
TPEX_OPENAPI = "https://www.tpex.org.tw/openapi/v1"


@dataclass(frozen=True)
class EndpointSpec:
    key: str
    host: str  # twse | tpex
    kind: str  # per_date | range | snapshot | stock_month
    base: str
    path: str
    fixed_params: dict = field(default_factory=dict)
    date_format: str = "%Y%m%d"
    date_param: str = "date"  # for per_date
    range_params: tuple = ("startDate", "endDate")
    stat_ok: str | None = None  # "OK" (TWSE), "ok" (TPEx), None
    table_selector: str | None = None  # substring of a table title (MI_INDEX)
    tables_key: str | None = None  # key holding a list of tables (TPEx: "tables")
    extra_params: tuple = ()  # names of further call-time params (stockNo, code)
    dataset: str = ""

    @property
    def url(self) -> str:
        return self.base + self.path


def _twse(key, path, kind, fixed=None, **kw):
    return EndpointSpec(
        key,
        "twse",
        kind,
        TWSE_BASE,
        path,
        {"response": "json", **(fixed or {})},
        "%Y%m%d",
        stat_ok="OK",
        dataset=key.split(".", 1)[1],
        **kw,
    )


def _tpex(key, path, kind, fixed=None, **kw):
    return EndpointSpec(
        key,
        "tpex",
        kind,
        TPEX_BASE,
        path,
        {"response": "json", **(fixed or {})},
        "%Y/%m/%d",
        stat_ok="ok",
        tables_key="tables",
        dataset=key.split(".", 1)[1],
        **kw,
    )


ENDPOINTS: dict[str, EndpointSpec] = {
    e.key: e
    for e in [
        _twse(
            "twse.mi_index",
            "afterTrading/MI_INDEX",
            "per_date",
            {"type": "ALLBUT0999"},
            table_selector="每日收盤行情",
            tables_key="tables",
        ),
        _twse("twse.mi_qfiis", "fund/MI_QFIIS", "per_date", {"selectType": "ALLBUT0999"}),
        _twse("twse.twt84u", "variation/TWT84U", "per_date"),
        _twse("twse.bwibbu_d", "afterTrading/BWIBBU_d", "per_date", {"selectType": "ALL"}),
        _twse("twse.stock_day", "afterTrading/STOCK_DAY", "stock_month", extra_params=("stockNo",)),
        _twse("twse.twt49u", "exRight/TWT49U", "range"),
        _twse("twse.twtauu", "reducation/TWTAUU", "range"),
        _twse("twse.twtawu", "afterTrading/TWTAWU", "range"),
        _twse("twse.punish", "announcement/punish", "range"),
        _twse("twse.notice", "announcement/notice", "range"),
        _tpex("tpex.otc", "afterTrading/otc", "per_date", {"type": "EW"}),
        _tpex("tpex.chtm", "afterTrading/chtm", "per_date"),
        _tpex("tpex.ex_daily", "bulletin/exDailyQ", "range"),
        _tpex("tpex.revivt", "bulletin/revivt", "range"),
        _tpex("tpex.disposal", "bulletin/disposal", "range", {"type": "all"}),
        _tpex("tpex.attention", "bulletin/attention", "range"),
        _tpex(
            "tpex.trading_stock", "afterTrading/tradingStock", "stock_month", extra_params=("code",)
        ),
        _tpex("tpex.deListed", "company/deListed", "range", {"code": "", "reason": "-1"}),
    ]
}


def openapi_spec(host: str, path: str) -> EndpointSpec:
    base = TWSE_OPENAPI if host == "twse" else TPEX_OPENAPI
    return EndpointSpec(
        f"{host}.openapi.{path.strip('/')}",
        host,
        "snapshot",
        base,
        path,
        {},
        dataset="openapi_" + path.strip("/").replace("/", "_"),
    )


def build_request(
    spec: EndpointSpec,
    *,
    on: date | None = None,
    start: date | None = None,
    end: date | None = None,
    **extra,
) -> tuple[str, dict]:
    """Return (url, params) for a call. Dates are formatted per host."""
    params = dict(spec.fixed_params)
    if spec.kind == "per_date":
        if on is None:
            raise ValueError(f"{spec.key} needs `on`")
        params[spec.date_param] = on.strftime(spec.date_format)
    elif spec.kind == "stock_month":
        if on is None:
            raise ValueError(f"{spec.key} needs `on`")
        params[spec.date_param] = on.strftime(spec.date_format)
    elif spec.kind == "range":
        if spec.key == "tpex.deListed":
            if on is None:
                raise ValueError("tpex.deListed needs `on` (a date in the year)")
            params["date"] = str(on.year)
        else:
            if start is None or end is None:
                raise ValueError(f"{spec.key} needs `start` and `end`")
            params[spec.range_params[0]] = start.strftime(spec.date_format)
            params[spec.range_params[1]] = end.strftime(spec.date_format)
    for name in spec.extra_params:
        if name not in extra:
            raise ValueError(f"{spec.key} needs {name}")
        params[name] = extra[name]
    return spec.url, params
