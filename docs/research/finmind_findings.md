# FinMind findings from public docs (no API calls made)

Date: 2026-11-13. Sources: finmind.github.io (official docs, Chinese and English), the FinMind GitHub README and `data_loader.py`. Page text was read through a summarising fetch tool, so exact wording may be slightly off; items marked "documented" were stated on the page, none is live-verified. Docs are maintained by FinMind itself and carry a dated changelog (WhatIsNew), so reliability is fairly good for what they state, but they are silent on many details.

Base URLs: Technical https://finmind.github.io/tutor/TaiwanMarket/Technical/ ; Chip .../Chip/ ; Fundamental .../Fundamental/ ; Others .../Others/ ; US https://finmind.github.io/en/tutor/UnitedStatesMarket/Technical/ ; Pricing https://finmind.github.io/Pricing/ ; Ban policy https://finmind.github.io/BanIPPolicy/ ; Usage https://finmind.github.io/api_usage_count/ ; Quickstart https://finmind.github.io/quickstart/ ; Changelog https://finmind.github.io/en/WhatIsNew/ ; README https://github.com/FinMind/FinMind

## Q1. TaiwanStockTotalReturnIndex
- Answer: data range 2003-01-01 to now, updated Mon-Fri 16:50. Documented `data_id` values: `TAIEX` (TAIEX total return, 發行量加權股價報酬指數) and `TPEx` (TPEx price index and total return index). `price` is the total return index value, not the ordinary index level. Columns: `date`, `stock_id` (index code), `price`. The Python wrapper renames `stock_id` to `index_id`.
- No Taiwan 50 or 0050 total return index is documented. 0050 is only available as a normal stock via `TaiwanStockPrice` (free) and `TaiwanStockPriceAdj` (Backer or higher).
- Source: Technical page; data_loader.py (`taiwan_stock_total_return_index`). Reliability: documented for TAIEX/TPEx; "not found" for any 0050 or other index. The doc is unclear whether `TPEx` returns one or two series (price index and return index) and how they are distinguished.
- Unresolved (live probe only): whether `TPEx` returns two rows per date; whether any other ids (e.g. a Taiwan 50 index) exist; whether the full 2003 history is present.

## Q2. USStockPrice
- Documented: only example is `data_id` `^DJI` (index symbols use a caret). Columns shown: date, stock_id, Adj_Close, Close, High, Low, Open, Volume. Updated daily 08:00 (Taiwan time, so it holds the prior US session). One row per date for one `data_id`; date is a string with no time. No tier restriction stated (only USStockPriceMinute is Backer/Sponsor). `USStockInfo` (no data_id needed) lists all US listed/OTC stocks with columns date, stock_id, Country, IPOYear, MarketCap, Subsector, stock_name.
- Not found: which tickers are covered (NVDA, AMD, AVGO, AAPL, MU, TSM, SOXX, QQQ, SPY, VIX/^VIX), start date, whether Adj_Close is split-only or split+dividend adjusted and whether it restates history. Inference only: plain tickers for equities/ETFs and caret for indices, so VIX is probably `^VIX`; Adj_Close column naming matches Yahoo-style data, so it likely restates after dividends. Both are inferred, not documented.
- The documentation schema block lists lowercase close/high/low/open and omits Adj_Close, which is inconsistent with the sample output.
- Source: US page. Reliability: partial; most items "not found".
- Live probe needed: ticker coverage, start dates, `^VIX` vs `VIX`, and whether Adj_Close of an old date changes between two pulls after an ex-dividend date (the restatement test needs two pulls at different times, or compare Adj_Close/Close ratio on a dividend-paying ticker such as SPY).

## Q3. Granularity and limits
Documented tier facts (Pricing page): Free 300/hour (45 datasets), Register (email-verified token, still the "Free" level) 600/hour, Backer 1,600/hour (81 datasets), Sponsor 6,000/hour (97), Sponsor Pro 20,000/hour. Quickstart page contradicts itself (600/hour in Chinese line, 300/hour in English line); README says no token 300, token 600.

| Dataset | Per-stock with date range | All stocks for one date (no data_id) | Tier for all-stocks |
|---|---|---|---|
| TaiwanStockPrice | yes | yes (start_date only) | Backer/Sponsor |
| TaiwanStockMonthRevenue | yes | yes | Backer/Sponsor |
| TaiwanStockInstitutionalInvestorsBuySell | yes | yes | Backer/Sponsor |
| TaiwanStockShareholding | yes | yes | Backer/Sponsor |
| TaiwanStockMarginPurchaseShortSale | yes | yes | Backer/Sponsor |
| TaiwanStockDayTrading | not stated, presumed yes | yes | Backer/Sponsor |
| TaiwanStockPER | yes | yes | Backer/Sponsor |
| TaiwanStockDividend | yes | yes | Backer/Sponsor |
| TaiwanStockDividendResult | yes | yes | Backer/Sponsor |

- Documented: Pricing page says Backer can download all stocks for a given date without `data_id` (price, institutional, margin). Chip/Fundamental/Technical pages repeat "backer/sponsor only" per dataset. The Free tier is not explicitly stated to be barred from this for every dataset, but the pages say so for each listed one. Dividend page example for all-stocks uses the name `TaiwanStockStockDividend` (looks like a doc typo).
- Years per call: no maximum range documented. `start_date` and `end_date` are optional but at least one is needed (Quickstart). Minute/tick/news style datasets are explicitly one day per request; the daily datasets above carry no such note. No maximum rows per response documented (not found). The Python wrapper has no chunking or row limit.
- Also documented: `stock_id_list` with async option in the Python package for multi-stock pulls (Chip page); this is client-side fan-out and each stock still counts as a request (inferred, not stated).
- Arithmetic (2015-06 to 2026-11 is about 11.4 years, about 2,800 trading days at about 245 per year; 450 stocks):
  - (a) per stock, one range call each: 450 requests per dataset, 0.75 hour at 600/hour. If calls must be chunked by year (cautious, no documented limit): 450 x 12 = 5,400 requests, 9 hours. Nine datasets: 4,050 requests (6.75 hours) unchunked, 48,600 (81 hours) chunked yearly.
  - (b) per date, all stocks: about 2,800 requests per dataset (4.7 hours at 600/hour, but Backer is 1,600/hour so about 1.75 hours). Nine datasets: 25,200 requests. Not allowed on Free; needs Backer or higher (paid, human gate).
  - Allowed on Free: (a) only. Unaffected datasets (per-stock only) like month revenue are cheap: 450 requests.
  - Plan's 450-stock universe cost also includes delisted stocks, which the above counts as part of the 450.
- Reliability: documented for tier/all-stocks; "not found" for years per call and row caps.
- Live probe needed: one request with a 12-year range for one `data_id` to see whether it returns everything (cost: 1 request); check row count versus expected trading days.

## Q4. TaiwanStockMonthRevenue.create_time
- Documented (Fundamental page): `create_time` (YYYY-MM-DD) is the date the record entered the FinMind database; it is not the official MOPS announcement time but is a close approximation because FinMind collects several times a day. Populated only since 2026-04-21; older rows are an empty string. Rows written on 2026-04-21 all carry that date as an activation default, not their true announcement date. The changelog dates the column addition at 2026-05-22 (the changelog entry date differs from the 2026-04-21 population date; both documented).
- Consequence: `create_time` is useless for point-in-time history before 2026-04-21 (blank) and for the 2026-04-21 batch; it is also only date-level. Not found: FinMind's documented real publication timing. The `date` of a revenue row is shown as the first of the following month (example: March 2019 revenue dated 2019-04-01), which is not a publication date. The statutory deadline (10th of the next month) is not stated in FinMind docs; that is regulation, not FinMind documentation.
- Reliability: documented. Live probe needed only to measure blank share and distribution of create_time (fully countable from one pull per stock).

## Q5. Shareholding, Info, Delisting
- TaiwanStockShareholding: data start 2004-02-01; updated Mon-Fri 21:00. Columns include `NumberOfSharesIssued`, foreign holding shares and ratios, `RecentlyDeclareDate`, `note`. The doc example shows NumberOfSharesIssued tied to a RecentlyDeclareDate (2019-05-27 for 2330), suggesting the issued-share value carries a declaration date. Not found: whether NumberOfSharesIssued is populated across all history, whether delisted stocks are included. Changelog 2026-03-26 mentions a fix to a "shareholding distribution table" date range (unclear dataset).
- TaiwanStockInfo: documented as having date-stamped rows; `date` is the update date; "transferred stocks keep multiple rows", so take the latest `date` per `stock_id` for the current market. Lists TWSE, TPEx and Emerging. Updated daily 01:30. So it keeps some history of market changes (inferred it is not a full history of industry changes; not stated). Not found: data start. Changelog 2026-05-19: use TaiwanStockInfo to look up market type for emerging stocks. Whether it keeps delisted stocks is not documented.
- TaiwanStockDelisting: added 2024-03-19 (changelog); TPEx delisting records backfilled 2026-09-01. No dedicated section on the tutorial pages (not found: columns, range). So coverage before the TPEx backfill was TWSE-biased; probe results (726 rows) should be re-checked for TPEx coverage.
- Live probe needed: Shareholding NumberOfSharesIssued blank rate, earliest date per stock, a delisted id (any known delisted stock) in Shareholding/Price/Info, Info row multiplicity.

## Q6. Dividends
- TaiwanStockDividend: documented range from 2005-05-01 to now. `AnnouncementDate` = 公告日期 (announcement date); `AnnouncementTime` = 公告時間, e.g. 15:47:30. No further definition (the doc does not say whose announcement: board resolution, shareholders' meeting, or exchange notice; inferred: date of the exchange announcement). Changelog 2026-10-22: duplicate ETF distribution records were reduced to one per ex-dividend date (so ETF rows like 0050 were restated recently; refetch if collected before).
- TaiwanStockDividendResult: documented range from 2003-05-01 to now; columns date, stock_id, before_price, after_price, stock_and_cache_dividend, stock_or_cache_dividend, max_price, min_price, open_price, reference_price. Changelog 2026-09-06: completed for 2026-09-02.
- Both cover 2015 per docs. Reliability: documented; actual completeness per stock not verifiable here.

## Q7. Sources, errors, restatements, rate limits
- README: states data is "processed and provided by" FinMind and that all information is subject to data announced by the Taiwan Stock Exchange (TWSE); TPEx is not mentioned there. No page found that explicitly says prices come from TWSE and TPEx daily files (inferred, not documented). Taiwan PriceAdj is back-calculated from the latest trading day; recomputed 2026-09-01.
- Restatements documented in the changelog (all 2026): TaiwanStockPrice gained zero/low-volume rows for 2022-11-28 to 2023-03-27 (2026-11-04), refetch advised; TaiwanStockPriceLimit rebuilt (2026-10-19, 10-31); TPEx margin short-sale buy and sell columns swapped and corrected (2026-09-01); TaiwanStockDividend ETF duplicates fixed (2026-10-22); EPS in FinancialStatements corrected (2026-10-11). Institutional buy/sell can rise slightly after first publication; docs advise waiting 1-2 trading days. So history is restated in place and there is no versioning: collect with fetch timestamps. Disclaimer in README: no guarantee against data errors or delays. Maintenance every Sunday 00:00-07:00 (no service).
- Emerging-stock caveat: open is previous-day average, 0 on first trading day; days with no price show 0 in all price fields. Dealer/foreign-dealer categories were split in 2014-12 and 2017-2018, with 0 before.
- Rate limits: 402 means quota exceeded ("Requests reach the upper limit"). `user_info` endpoint `GET https://api.web.finmindtrade.com/v2/user_info` with Bearer token returns `user_count` and `api_request_limit`. IP ban policy: a large volume of 4xx errors in a short period (invalid token, bad params, over quota) bans the IP; every request then returns 403 `{"msg": "ip banned", "status": 403}`; ban lifts automatically after 30 minutes and recurs if bad requests continue. No numeric threshold given. `TokenIllegal` (400) / `TokenLevelTooLow`: stop. 5xx: exponential backoff with capped retries.

## Decision for the author
Context: collecting nine datasets for about 450 stocks over 11.4 years. On Free, only per-stock range calls are documented as allowed, and that is cheap (450 requests per dataset if long ranges work) so no paid tier is needed. Options:
1. Stay on Free, per-stock range calls (recommended; about 4,050 requests for nine datasets, about 7 hours at 600/hour). Run one 1-request probe of a 12-year range first.
2. Buy Backer for all-stocks-per-date (about 25,200 requests, faster per hour but total requests are higher than option 1), no real benefit except for survivorship coverage of stocks outside the list. Not worth it for this universe.
Also decide whether to run a live probe for the items below (all small).

## Items settled only by a live probe (with token)
1. Max years per call and row cap (one long-range call).
2. USStockPrice tickers, start dates, `^VIX`, Adj_Close restatement.
3. TaiwanStockTotalReturnIndex `TPEx` shape and any 0050-like id.
4. Blank share of MonthRevenue create_time.
5. Shareholding NumberOfSharesIssued blanks, earliest date, delisted stock coverage; Info/Delisting coverage for delisted and TPEx ids.
6. Whether free tier really rejects all-stocks-per-date (costs an error response; rejected requests count towards 4xx ban risk, so do it once at most, or skip: the docs say it is paid).

## Contradictions or corrections to existing docs
- FINMIND_DATASETS.md: "600 requests/hour" for `level: Free` matches the registered-member limit; the official Pricing page lists Free at 300 and Register at 600, and the Quickstart contradicts itself. Use the user-info value (as rule 7 says).
- FINMIND_DATASETS.md lists TaiwanStockTotalReturnIndex data_id only as `TAIEX`; docs also give `TPEx`. There is no 0050 or Taiwan 50 total return index documented.
- FINMIND_DATASETS.md says `create_time` "exists, measure blanks": docs say it is blank before 2026-04-21 and the 2026-04-21 batch carries a default date, so it cannot give historical available_at; use a statutory-deadline rule for history.
- Fallback "compute adjusted prices from DividendResult" is fine, but note the 2026-10-22 ETF duplicate fix and 2026-11-04 price backfill: earlier pulls may be stale.
- DividendResult docs span from 2003, Dividend from 2005; both cover 2015. AnnouncementDate has no documented semantics beyond "announcement date".
- TaiwanStockDelisting: the 726-row probe was before or after the 2026-09-01 TPEx backfill is unknown; the docs say TPEx records were backfilled on 2026-09-01.
- I did not read the plan file; the "Consequences" claim that Shareholding gives NumberOfSharesIssued for market value is only documented as tied to a declaration date, not a daily series.
