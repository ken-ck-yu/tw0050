# FinMind dataset verification

Verified 2026-11-13 against the live API (v4) with a Free-tier account (`level: Free`, 600 requests/hour).
Each dataset was probed with one small request (2330 or a short date range). 27 of 27 names exist.

## Needs a paid tier (Free account returns 400 "Your level is register")

| Dataset | Fallback |
|---|---|
| `TaiwanStockPriceAdj` | Compute adjusted prices from raw `TaiwanStockPrice` plus `TaiwanStockDividendResult` (has `before_price`, `after_price`, `reference_price`) |
| `TaiwanStockCapitalReductionReferencePrice` | TWSE/TPEx open data for capital reductions |
| `TaiwanStockMarketValue` | `close` x `NumberOfSharesIssued` (from `TaiwanStockShareholding`) |

## Available on Free tier

| Dataset | Notable columns |
|---|---|
| `TaiwanStockInfo` | industry_category, stock_id, stock_name, type (market flag), date |
| `TaiwanStockDelisting` | date, stock_id, stock_name (726 rows) |
| `TaiwanStockTradingDate` | date |
| `TaiwanStockPrice` | OHLC, Trading_Volume, Trading_money, spread |
| `TaiwanStockDividend` | ex-dates, cash/stock amounts, **AnnouncementDate**, AnnouncementTime |
| `TaiwanStockDividendResult` | before_price, after_price, reference_price |
| `TaiwanStockTotalReturnIndex` | price (data_id `TAIEX`) |
| `TaiwanStockMonthRevenue` | revenue, revenue_month, revenue_year, **create_time** |
| `TaiwanStockInstitutionalInvestorsBuySell` | buy, sell, name (investor type) |
| `TaiwanStockShareholding` | foreign holding ratios, **NumberOfSharesIssued** |
| `TaiwanStockMarginPurchaseShortSale` | margin and short balances |
| `TaiwanStockSecuritiesLending` | transaction_type, volume, fee_rate |
| `TaiwanDailyShortSaleBalances` | margin and SBL short balances |
| `TaiwanStockDayTrading` | Volume, BuyAmount, SellAmount |
| `TaiwanStockPER` | PER, PBR, dividend_yield |
| `USStockPrice` | Open/High/Low/Close, Adj_Close, Volume |
| `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`, `TaiwanStockCashFlowsStatement` | type, value, origin_name; **no filing-date column** |
| `TaiwanExchangeRate` | cash/spot buy/sell (data_id `USD`) |
| `InterestRate` | country, interest_rate (data_id `FED`) |
| `GovernmentBondsYield` | name, value (data_id `United States 10-Year`) |
| `TaiwanFuturesDaily` | futures_id, contract_date, OHLC, open_interest (data_id `TX`) |
| `TaiwanFuturesInstitutionalInvestors` | long/short volume and open interest by investor |

## Consequences for the plan

- **Adjusted prices** must be built in-house. This also serves as the validation the plan calls for.
- **Quarterly financials:** FinMind gives no filing date, so use the statutory-deadline fallback and look for real filing dates in MOPS.
- **Monthly revenue:** `create_time` exists. Measure how many rows are blank before relying on it.
- **Dividends:** `AnnouncementDate` gives a usable `available_at`.
- **Not yet probed:** `USStockPrice` for the full ticker list (AMD, AVGO, AAPL, MU, TSM, SOXX, QQQ, SPY, VIX), the exact `data_id` for TAIEX versus 0050 total return, and disposition/attention stocks (TWSE/TPEx).
