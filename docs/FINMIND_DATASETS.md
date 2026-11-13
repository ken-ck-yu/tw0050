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

## Live probe results (2026-11-13, Free account, about 25 requests)

Account: `level` Free, `api_request_limit` 600 per hour. The FinMind pricing page says Free is 300 and Register is 600, so the live value wins.

| Question | Result |
|---|---|
| Maximum range per call | `TaiwanStockPrice` 2330 over 2015-06-01 to 2026-11-13 returned 2,795 rows in one call, no cap seen. One request per stock per dataset is enough |
| Delisted prices | 2475 (delisted 2019-05-13): prices 2015-06-01 to 2019-05-10, matching TWSE's last trade |
| Shares issued | `TaiwanStockShareholding` has no blank `NumberOfSharesIssued` for 2330, 2475, 6488. **3299 (TPEx, delisted 2018) returned 0 rows.** 2475 continues to 2020-12-01, 19 months after its last trade, so do not infer listing status from this table. 6488 starts on its listing date (2015-09-24) |
| US tickers | NVDA, AMD, AVGO, AAPL, MU, TSM, SOXX, QQQ, SPY all present from 2015-01-02 (2,984 rows). The VIX is `^VIX` (2,988 rows). `VIX` returns nothing |
| `create_time` | 2330 revenue: 133 of 143 rows blank. The 10 filled values run 2026-04-21 to 2026-11-13 (9 distinct), so they are load dates, not announcement dates |
| Benchmark | `TaiwanStockTotalReturnIndex` `data_id` `TAIEX` and `TPEx`, both 2,795 rows from 2015-06-01 |
| Delisting table | 690 rows from 2000-01-27 to 2026-10-01, columns `date`, `stock_id`, `stock_name` only. Includes 2475 and 3299. An earlier probe on this page counted 726 rows. The difference is unexplained |
| Stock info | 4,389 rows for 3,182 distinct `stock_id`. 1,080 ids have more than one row, so it carries dated changes. Whether `date` is the change date or a snapshot date is unknown |

Consequences: FinMind is cheap for the heavy datasets (about 450 requests per dataset for a 450-stock collection set), but it cannot supply shares issued for delisted TPEx names, so the official files stay primary for the universe pass.
