# Official free sources (TWSE / TPEx)

Probed 2026-11-13 with tokenless GET requests (about 16 in total, 4 to 5 seconds apart). These are **scrape-grade**: the `rwd` / `www` JSON endpoints are not in the OpenAPI swagger files and can change without notice. Cache every raw response. Dates are ROC calendar (104/06/01 = 2015-06-01) and numbers carry thousands separators.

Swagger: TWSE `https://openapi.twse.com.tw/v1/swagger.json` (143 paths), TPEx `https://www.tpex.org.tw/openapi/swagger.json` (225 paths). Most OpenAPI paths return the latest snapshot only.

## Closes the three Free-tier gaps in `FINMIND_DATASETS.md`

| Need | Endpoint | Verified |
|---|---|---|
| TWSE ex-rights/dividends (pre-ex close, reference price) | `twse.com.tw/rwd/zh/exRight/TWT49U?startDate=&endDate=` | Jun-Sep 2015 returned |
| TWSE capital reductions (reference price, reason) | `twse.com.tw/rwd/zh/reducation/TWTAUU?startDate=&endDate=` | 2015-06 to 2022-12 in one call |
| TPEx ex-rights/dividends | `tpex.org.tw/www/zh-tw/bulletin/exDailyQ?startDate=&endDate=` | Jun-Sep 2015 returned, 473 rows |
| TPEx daily quotes incl. shares issued (`發行股數`), so market cap | `tpex.org.tw/www/zh-tw/afterTrading/otc?date=&type=EW` | 2015-06-01 returned, 696 rows |
| TWSE all-stock daily quotes | `twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=&type=ALLBUT0999` | 2015-06-01 returned |
| TWSE one stock, one month | `twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=&stockNo=` | 2330, June 2015 |

Open: TWSE shares-issued history (`/opendata/t187ap03_L` is a current snapshot only); TPEx capital-reduction coverage (`exDailyQ` is ex-rights/dividends).

## Fills gaps in the plan (universe exclusions and fill blockers)

| Need | Endpoint | Verified |
|---|---|---|
| Disposition stocks | `twse.com.tw/rwd/zh/announcement/punish?startDate=&endDate=` | Works for 2015 and 2024 windows. Fields: announce date, code, condition, period, measure |
| Attention stocks | `twse.com.tw/rwd/zh/announcement/notice?startDate=&endDate=` | Works for 2015 and 2024 windows. Fields: cumulative count, reason text, date, close, PER |
| Official PER / yield / PBR by date | `twse.com.tw/rwd/zh/afterTrading/BWIBBU_d?date=&selectType=ALL` | 2015-06-01 returned, 858 rows. Cross-check for FinMind `TaiwanStockPER` |

Not found at the URL patterns I guessed (returned an HTML error page, so paths unknown, not proof of no history): `TWT84U` (price-limit steps), `MFI94U` (total return index), `TWTAWU` (suspended securities), `TWT85U` (altered trading). TPEx equivalents exist in the swagger (`/tpex_disposal_information`, `/tpex_trading_warning_information`, `/tpex_cmode`) and have not been probed for history. Find the real paths from the TWSE site's network calls before relying on any of these.

## Snapshot-only candidates (start a daily snapshot job early)

Past `available_at` cannot be recovered for these, so snapshots should begin as soon as ingestion is approved:
`/SBL/TWT96U` (borrowable shares), `/exchangeReport/BFI84U` (margin/short suspensions), `/exchangeReport/TWTB4U` (day-trading list), `/opendata/t187ap04_L` (material announcements), `/opendata/t187ap12_L` (insider transfer filings), `/opendata/t187ap09_L` (director pledges), `/opendata/t187ap24_L` to `t187ap27_L` (control and business changes).

## Cross-checks for FinMind

`/opendata/t187ap05_L` (monthly revenue), `/opendata/t187ap06_L_*` and `t187ap07_L_*` (quarterly income statement and balance sheet by industry type), `/company/suspendListingCsvAndHtml` (delistings), `/company/newlisting`.

## Not probed

History depth before 2015 and for delisted names' last trading days; throttling behaviour (too few requests to trigger it); value-level agreement with FinMind.

## Skip

ESG (`t187ap46_L_*`), broker statistics, warrants, bonds, funds, board-governance endpoints.
