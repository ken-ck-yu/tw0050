"""Table registry (docs/specs/m0_specs.md section 7) and endpoint field-list eras."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True)
class Table:
    name: str
    columns: dict
    key: tuple
    part: str
    klass: str  # joinable | reference | derived
    restatement: str  # economic | source_error | none

    @property
    def column_names(self) -> list[str]:
        return list(self.columns)


COMMON_JOINABLE = {
    "event_date": "DATE",
    "available_at": "TIMESTAMPTZ?",
    "fetched_at": "TIMESTAMPTZ",
}
COMMON_OTHER = {"fetched_at": "TIMESTAMPTZ"}

TABLES: dict[str, Table] = {}


def register_table(table: Table) -> Table:
    for k in table.key:
        if k not in table.columns:
            raise ValueError(f"{table.name}: key column {k!r} not in columns")
    if table.part not in table.columns:
        raise ValueError(f"{table.name}: part column {table.part!r} not in columns")
    TABLES[table.name] = table
    return table


def _cols(spec: str) -> dict:
    out = {}
    for item in spec.split(","):
        name, typ = (x.strip() for x in item.split(":"))
        out[name] = typ
    return out


def _joinable(name, cols, key, restatement, extra_common=True):
    columns = dict(COMMON_JOINABLE)
    columns.update(_cols(cols))
    return register_table(
        Table(name, columns, tuple(key.split(",")), "event_date", "joinable", restatement)
    )


def _other(name, cols, key, klass, part="event_date"):
    columns = {"event_date": "DATE"} if part == "event_date" else {}
    columns.update(COMMON_OTHER)
    columns.update(_cols(cols))
    return register_table(Table(name, columns, tuple(key.split(",")), part, klass, "none"))


_joinable(
    "prices_raw",
    "market:VARCHAR, stock_id:VARCHAR, open:DOUBLE?, high:DOUBLE?, low:DOUBLE?, "
    "close:DOUBLE?, volume_shares:BIGINT, turnover_ntd:BIGINT, trades:BIGINT",
    "market,stock_id,event_date",
    "source_error",
)
_joinable(
    "price_limits",
    "market:VARCHAR, stock_id:VARCHAR, limit_up:DOUBLE?, limit_down:DOUBLE?",
    "market,stock_id,event_date",
    "source_error",
)
_joinable(
    "shares_issued",
    "market:VARCHAR, stock_id:VARCHAR, isin:VARCHAR?, shares_issued:BIGINT",
    "market,stock_id,event_date",
    "source_error",
)
_joinable(
    "corporate_actions",
    "market:VARCHAR, stock_id:VARCHAR, action_type:VARCHAR, "
    "prev_close:DOUBLE?, reference_price:DOUBLE?, halt_close:DOUBLE?, ratio:DOUBLE?, "
    "cash_dividend:DOUBLE?, stock_dividend_per_1000:DOUBLE?, reduction_reason:VARCHAR?",
    "market,stock_id,event_date,action_type",
    "source_error",
)
_joinable(
    "status_events",
    "market:VARCHAR, stock_id:VARCHAR, status_type:VARCHAR, "
    "announce_date:DATE?, start_date:DATE, end_date:DATE?, detail:VARCHAR?",
    "market,stock_id,status_type,start_date",
    "source_error",
)
_joinable(
    "benchmark_index", "index_id:VARCHAR, value:DOUBLE", "index_id,event_date", "source_error"
)
_joinable(
    "monthly_revenue",
    "stock_id:VARCHAR, country:VARCHAR, revenue_year:BIGINT, "
    "revenue_month:BIGINT, revenue:BIGINT, create_time:VARCHAR?",
    "stock_id,event_date",
    "economic",
)
_joinable(
    "financials",
    "stock_id:VARCHAR, statement:VARCHAR, item:VARCHAR, origin_name:VARCHAR, value:DOUBLE?",
    "stock_id,event_date,statement,item",
    "economic",
)
_joinable(
    "dividend_results",
    "stock_id:VARCHAR, before_price:DOUBLE, after_price:DOUBLE, "
    "stock_and_cache_dividend:DOUBLE, stock_or_cache_dividend:VARCHAR, max_price:DOUBLE, "
    "min_price:DOUBLE, open_price:DOUBLE, reference_price:DOUBLE",
    "stock_id,event_date",
    "source_error",
)
_joinable(
    "flows_institutional",
    "stock_id:VARCHAR, name:VARCHAR, buy:BIGINT, sell:BIGINT",
    "stock_id,event_date,name",
    "economic",
)
_joinable(
    "shareholding",
    "stock_id:VARCHAR, stock_name:VARCHAR, InternationalCode:VARCHAR, "
    "ForeignInvestmentRemainingShares:BIGINT, ForeignInvestmentShares:BIGINT, "
    "ForeignInvestmentRemainRatio:DOUBLE, ForeignInvestmentSharesRatio:DOUBLE, "
    "ForeignInvestmentUpperLimitRatio:DOUBLE, ChineseInvestmentUpperLimitRatio:DOUBLE, "
    "NumberOfSharesIssued:BIGINT, RecentlyDeclareDate:VARCHAR?, note:VARCHAR?",
    "stock_id,event_date",
    "source_error",
)
_joinable(
    "margin",
    "stock_id:VARCHAR, MarginPurchaseBuy:BIGINT, MarginPurchaseCashRepayment:BIGINT, "
    "MarginPurchaseLimit:BIGINT, MarginPurchaseSell:BIGINT, MarginPurchaseTodayBalance:BIGINT, "
    "MarginPurchaseYesterdayBalance:BIGINT, Note:VARCHAR?, OffsetLoanAndShort:BIGINT, "
    "ShortSaleBuy:BIGINT, ShortSaleCashRepayment:BIGINT, ShortSaleLimit:BIGINT, "
    "ShortSaleSell:BIGINT, ShortSaleTodayBalance:BIGINT, ShortSaleYesterdayBalance:BIGINT",
    "stock_id,event_date",
    "source_error",
)
_joinable(
    "securities_lending",
    "stock_id:VARCHAR, transaction_type:VARCHAR, seq:BIGINT, "
    "volume:BIGINT, fee_rate:DOUBLE, close:DOUBLE, original_return_date:VARCHAR?, "
    "original_lending_period:BIGINT?",
    "stock_id,event_date,transaction_type,seq",
    "source_error",
)
_joinable(
    "day_trading",
    "stock_id:VARCHAR, BuyAfterSale:VARCHAR, Volume:BIGINT, BuyAmount:BIGINT, SellAmount:BIGINT",
    "stock_id,event_date",
    "source_error",
)
_joinable(
    "valuation_ratios",
    "stock_id:VARCHAR, dividend_yield:DOUBLE?, PER:DOUBLE?, PBR:DOUBLE?",
    "stock_id,event_date",
    "economic",
)
_joinable(
    "us_prices",
    "ticker:VARCHAR, Open:DOUBLE, High:DOUBLE, Low:DOUBLE, Close:DOUBLE, "
    "Adj_Close:DOUBLE, Volume:BIGINT",
    "ticker,event_date",
    "source_error",
)
_joinable(
    "fx",
    "currency:VARCHAR, cash_buy:DOUBLE?, cash_sell:DOUBLE?, spot_buy:DOUBLE?, spot_sell:DOUBLE?",
    "currency,event_date",
    "source_error",
)
_joinable("rates", "series:VARCHAR, value:DOUBLE", "series,event_date", "source_error")
_joinable(
    "futures_daily",
    "futures_id:VARCHAR, contract_date:VARCHAR, trading_session:VARCHAR, "
    "open:DOUBLE?, max:DOUBLE?, min:DOUBLE?, close:DOUBLE?, spread:DOUBLE?, spread_per:DOUBLE?, "
    "volume:BIGINT, settlement_price:DOUBLE?, open_interest:BIGINT?",
    "futures_id,event_date,contract_date,trading_session",
    "source_error",
)
_joinable(
    "futures_institutional",
    "futures_id:VARCHAR, institutional_investors:VARCHAR, "
    "long_deal_volume:BIGINT, long_deal_amount:BIGINT, short_deal_volume:BIGINT, "
    "short_deal_amount:BIGINT, long_open_interest_balance_volume:BIGINT, "
    "long_open_interest_balance_amount:BIGINT, short_open_interest_balance_volume:BIGINT, "
    "short_open_interest_balance_amount:BIGINT",
    "futures_id,event_date,institutional_investors",
    "source_error",
)
_joinable(
    "dividend_announcements",
    "stock_id:VARCHAR, source_date:VARCHAR, year:VARCHAR, "
    "StockEarningsDistribution:DOUBLE?, StockStatutorySurplus:DOUBLE?, "
    "StockExDividendTradingDate:VARCHAR?, TotalEmployeeStockDividend:DOUBLE?, "
    "TotalEmployeeStockDividendAmount:DOUBLE?, RatioOfEmployeeStockDividendOfTotal:DOUBLE?, "
    "RatioOfEmployeeStockDividend:DOUBLE?, CashEarningsDistribution:DOUBLE?, "
    "CashStatutorySurplus:DOUBLE?, CashExDividendTradingDate:VARCHAR?, "
    "CashDividendPaymentDate:VARCHAR?, TotalEmployeeCashDividend:DOUBLE?, "
    "TotalNumberOfCashCapitalIncrease:DOUBLE?, CashIncreaseSubscriptionRate:DOUBLE?, "
    "CashIncreaseSubscriptionpRrice:DOUBLE?, RemunerationOfDirectorsAndSupervisors:DOUBLE?, "
    "ParticipateDistributionOfTotalShares:DOUBLE?, AnnouncementTime:VARCHAR?",
    "stock_id,event_date,year",
    "economic",
)
_joinable(
    "short_sale_balances",
    "stock_id:VARCHAR, MarginShortSalesPreviousDayBalance:BIGINT, "
    "MarginShortSalesShortSales:BIGINT, MarginShortSalesShortCovering:BIGINT, "
    "MarginShortSalesStockRedemption:BIGINT, MarginShortSalesCurrentDayBalance:BIGINT, "
    "MarginShortSalesQuota:BIGINT, SBLShortSalesPreviousDayBalance:BIGINT, "
    "SBLShortSalesShortSales:BIGINT, SBLShortSalesReturns:BIGINT, "
    "SBLShortSalesAdjustments:BIGINT, SBLShortSalesCurrentDayBalance:BIGINT, "
    "SBLShortSalesQuota:BIGINT, SBLShortSalesShortCovering:BIGINT",
    "stock_id,event_date",
    "source_error",
)
_joinable(
    "finmind_prices",
    "stock_id:VARCHAR, Trading_Volume:BIGINT, Trading_money:BIGINT, open:DOUBLE?, max:DOUBLE?, "
    "min:DOUBLE?, close:DOUBLE?, spread:DOUBLE?, Trading_turnover:BIGINT",
    "stock_id,event_date",
    "source_error",
)
_other("trading_calendar", "is_trading:BOOLEAN, source:VARCHAR", "event_date,source", "reference")
_other(
    "stock_info",
    "stock_id:VARCHAR, stock_name:VARCHAR, industry_category:VARCHAR, type:VARCHAR",
    "stock_id,event_date",
    "reference",
)
_other("delistings", "stock_id:VARCHAR, stock_name:VARCHAR", "stock_id,event_date", "reference")
_other(
    "market_cap",
    "available_at:TIMESTAMPTZ?, stock_id:VARCHAR, close:DOUBLE, shares_issued:BIGINT, "
    "market_cap_ntd:DOUBLE",
    "stock_id,event_date",
    "derived",
)
register_table(
    Table(
        "universe_membership",
        {
            "fetched_at": "TIMESTAMPTZ",
            "available_at": "TIMESTAMPTZ?",
            "month_end": "DATE",
            "stock_id": "VARCHAR",
            "isin": "VARCHAR?",
            "market": "VARCHAR",
            "rank": "BIGINT?",
            "market_cap_ntd": "DOUBLE",
            "median_turnover_60d": "DOUBLE",
            "is_watchlist": "BOOLEAN",
            "is_benchmark": "BOOLEAN",
        },
        ("month_end", "stock_id"),
        "month_end",
        "derived",
        "none",
    )
)
register_table(
    Table(
        "collection_set",
        {
            "fetched_at": "TIMESTAMPTZ",
            "stock_id": "VARCHAR",
            "first_month_end": "DATE",
            "last_month_end": "DATE",
            "ever_watchlist": "BOOLEAN",
            "is_benchmark": "BOOLEAN",
        },
        ("stock_id", "first_month_end"),
        "first_month_end",
        "reference",
        "none",
    )
)


def snapshot_table(name: str) -> Table:
    """One table per snapshot endpoint: snapshot_<name>."""
    tname = f"snapshot_{name}"
    if tname in TABLES:
        return TABLES[tname]
    cols = dict(COMMON_JOINABLE)
    cols.update(
        {
            "snapshot_date": "DATE",
            "first_seen_at": "TIMESTAMPTZ",
            "payload_sha256": "VARCHAR",
            "row_seq": "BIGINT",
            "row_json": "VARCHAR",
        }
    )
    return register_table(
        Table(
            tname,
            cols,
            ("payload_sha256", "snapshot_date", "row_seq"),
            "event_date",
            "joinable",
            "source_error",
        )
    )


@dataclass(frozen=True)
class Era:
    first_date: date | None
    last_date: date | None  # None means open-ended
    fields: tuple


ERAS: dict[str, list[Era]] = {}


def register_era(endpoint: str, era: Era) -> None:
    ERAS.setdefault(endpoint, []).append(era)


def _norm(fields) -> tuple:
    return tuple("".join(str(f).split()) for f in fields)


def fields_valid(endpoint: str, d: date | None, fields) -> bool:
    """True if the (whitespace-stripped) field list equals a registered era valid on d."""
    eras = ERAS.get(endpoint)
    if not eras:
        return True  # no era registered yet: nothing to compare against
    got = _norm(fields)
    for e in eras:
        if d is not None:
            if e.first_date is not None and d < e.first_date:
                continue
            if e.last_date is not None and d > e.last_date:
                continue
        if _norm(e.fields) == got:
            return True
    return False
