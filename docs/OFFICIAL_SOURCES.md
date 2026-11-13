# Official free sources (TWSE / TPEx)

Probed 2026-11-13 with tokenless GET requests, 5 seconds apart. These are **scrape-grade**: the `rwd` / `www` JSON endpoints are not in the OpenAPI swagger files and can change without notice. Cache every raw response. Dates are ROC calendar (104/06/01 = 2015-06-01) and numbers carry thousands separators.

Swagger: TWSE `https://openapi.twse.com.tw/v1/swagger.json` (143 paths), TPEx `https://www.tpex.org.tw/openapi/swagger.json` (225 paths). Most OpenAPI paths return the latest snapshot only. Full findings and evidence: `docs/research/twse_findings.md`, `docs/research/tpex_findings.md`, `docs/research/finmind_findings.md`.

## Gotchas for the clients

* TWSE answers HTTP 200 with an HTML error page for a wrong path or parameter. Judge success by the body: valid JSON, `stat` `OK`, non-empty `data`. TPEx writes `ok` in lower case.
* TPEx wrong paths return HTTP 302 to `/errors`. A holiday returns `stat` ok with 0 rows, as TWSE does.
* The rwd folder is not the web page folder or the OpenAPI prefix (`exRight/TWT49U`, `reducation/TWTAUU`, `variation/TWT84U`, `fund/MI_QFIIS`).
* To find a TPEx path: `https://www.tpex.org.tw/data/menu/zh-tw/menu.json` lists every page; each page's HTML has `action:"group/report"` and the form field names are the parameters. TWSE has no equivalent; its menus are built by JavaScript.
* Names can carry stray whitespace (a leading tab was seen in `MI_QFIIS`). Strip them.
* Stock codes are reused (2301 was Lite-On in 2002 and is today's Lite-On Technology). Join on code plus a date window, or on the ISIN.

## Added by the spikes (2026-11-13)

* `TWT84U` row for date D gives the limits for D (its `收盤價` is the previous trading day's close), 1,094 of 1,094 stocks on 2020-06-15. TPEx `otc` limit columns in file D are for the next trading day with a file (three pairs). About 98 TPEx rows carry a `9999.95`/`0.01` no-limit sentinel.
* `TWT49U` takes one call for 2015-06-01 to 2026-11-13 (11,863 rows) but takes 9 to over 60 seconds. It covers ETFs (every 0050 dividend). `TWTAUU` covers stocks only. `exDailyQ` also lists ETFs. TPEx `revivt` has 21 to 29 rows per year for 2016 to 2021, dates in 7-digit ROC format, reasons `彌補虧損` and `現金減資`.
* The common-stock rule (code `^[1-9][0-9]{3}$`, name without a trailing `*` not ending `-DR`) had no leaks or misses on 11 TWSE and 11 TPEx dates.
* TPEx `otc` era boundary: first 17-field day is 2020-04-30.

## Verified history endpoints

| Need | Endpoint | Verified |
|---|---|---|
| TWSE all-stock daily quotes, plus TAIEX and Taiwan 50 total return index table | `twse.com.tw/rwd/zh/afterTrading/MI_INDEX?date=&type=ALLBUT0999` | One date per year 2016 to 2025: identical field list every time, 951 to 1,294 rows |
| TWSE shares issued (發行股數) per stock per date | `twse.com.tw/rwd/zh/fund/MI_QFIIS?date=&selectType=ALLBUT0999` | 2015-06-01 915 rows, 2022-06-01 1,141 rows. Includes later-delisted stocks |
| TWSE limit-up and limit-down prices per stock per date | `twse.com.tw/rwd/zh/variation/TWT84U?date=` | 2015-06-15 922 rows, 2020-06-15 1,116 rows |
| TWSE ex-rights/dividends | `…/exRight/TWT49U?startDate=&endDate=` | Jun-Sep 2015 |
| TWSE capital reductions | `…/reducation/TWTAUU?startDate=&endDate=` | 2015-06 to 2022-12 in one call |
| TWSE one stock, one month | `…/afterTrading/STOCK_DAY?date=&stockNo=` | 2330 June 2015; delisted stocks up to their last trade |
| TWSE PER / yield / PBR by date | `…/afterTrading/BWIBBU_d?date=&selectType=ALL` | 2015-06-01, 858 rows |
| TWSE disposition and attention stocks | `…/announcement/punish`, `…/announcement/notice` (`startDate=&endDate=`) | 2015 and 2024 windows |
| TWSE suspended securities | `…/afterTrading/TWTAWU?startDate=&endDate=` | June 2020: 5 rows. 2015 window works but returned only 2 rows, both depositary receipts |
| TPEx all-stock daily quotes incl. shares issued and next-day limit prices | `tpex.org.tw/www/zh-tw/afterTrading/otc?date=YYYY/MM/DD&type=EW` | One date per year 2016 to 2025, 720 to 966 rows |
| TPEx ex-rights/dividends | `…/bulletin/exDailyQ?startDate=&endDate=` | 2016 full year, 510 rows. No capital reductions |
| TPEx capital reductions | `…/bulletin/revivt?startDate=&endDate=` | From 2013-01: 19 rows in 2015, 20 in 2022 |
| TPEx disposition | `…/bulletin/disposal?startDate=&endDate=&type=all` | From 2003-09: 31 rows 2015-06, 79 rows 2020-06 |
| TPEx attention (with cumulative count) | `…/bulletin/attention?startDate=&endDate=` | From 2002-02: 124 rows 2015-06, 3,277 rows for all 2020 in one reply |
| TPEx changed, split and managed trading, stop-trading flag | `…/afterTrading/chtm?date=YYYY/MM/DD` | Per day from 2008-04: 34 rows 2015-06-15 |
| TPEx delisted list | `tpex.org.tw/www/zh-tw/company/deListed?date=YYYY&code=&reason=-1` | One call per year; completeness uncertain (see below) |
| TPEx one stock, one month | `…/afterTrading/tradingStock?code=&date=` | Delisted stocks up to their last trade |

Request granularity: per date (about 2,780 trading days) for `MI_INDEX`, `MI_QFIIS`, `TWT84U`, `BWIBBU_d`, TPEx `otc` and `chtm`; per date range (a year per call works for TPEx; TWSE range limit untested, 12 calls if a year works) for the event endpoints; per stock-month for `STOCK_DAY` (about 138,000 requests, so spot checks only).

## What this settles

* **Survivorship:** the all-stock daily files from both markets contain stocks that were later delisted (66 in the 2016-06-01 TWSE file, 7 named in the 2016-06-01 TPEx file). The universe can be built from them with no dependence on any delisting list.
* **Last trading day:** it fell 1 to 13 calendar days before the official delisting date in the six stocks checked (three TWSE, three TPEx). Derive the last trading day from the daily files, not from the delisting date. Delisting lists are a cross-check only.
* **TWSE market cap:** `MI_QFIIS` gives issued shares per date. TPEx `otc` carries them daily. Market cap no longer depends on FinMind `TaiwanStockShareholding`. On four dates (2015-06-01, 2018-06-01, 2022-06-01, 2025-06-02) every common-stock code (858, 915, 964, 1,041) had a `MI_QFIIS` row. An earlier note of 915 versus 951 rows compared dates a year apart and was wrong.
* **Capital reductions:** TWSE `TWTAUU` and TPEx `revivt` carry the reference price and reason. TPEx `exDailyQ` has none.
* **Limit prices:** TWSE `TWT84U` and the TPEx `otc` next-day limit columns give actual limit prices for acceptance check 5.
* **Benchmark:** the `MI_INDEX` total return table (TAIEX and Taiwan 50) is available every sampled year. FinMind `TaiwanStockTotalReturnIndex` has `data_id` `TAIEX` and `TPEx` (documented, not live-probed). 0050 itself is an ordinary stock row.
* **Schema drift:** TWSE `MI_INDEX` had one field list over ten years. TPEx `otc` has three eras: 15 fields until 2020-04-29, 17 fields from 2020-04-30, and from 2025-01-10 the same 17 fields with two columns relabelled from `(千股)` to `(張數)`. The values did not change (median bid volume 3, ask volume 2 either side, inferred from medians). `成交股數` is in shares in all eras. Seven 2015 dates match the 2016 layout.

## Still unresolved

* TWSE full-delivery (全額交割) status: no source found. TPEx folds it into `chtm`. TWSE `TWT85U` (changed trading) has no known rwd path and the swagger form has no date parameter.
* TWSE `TWT96U` (borrowable shares) history, TWSE holiday-schedule history before the current year, and whether `MFI94U` returns a long range (it adds nothing over `MI_INDEX`).
* TPEx suspension history before 2026: `bulletin/sprc` is today only and the OpenAPI history holds the current year only. `chtm` per day is a proxy.
* TPEx delisted list completeness: transfers to TWSE may be missing.
* **No source for stock splits or par-value changes.** None of `TWT49U`, `TWTAUU`, `exDailyQ` or `revivt` carries them. 0050 closed 175.90 on 2025-06-02 and 51.45 on 2025-07-21 with no event row (inferred split). Handled through a manual corporate-actions file.
* Publication times of `TWT84U`, TPEx `otc` limit columns and `MI_QFIIS` (no timestamp in the responses).

## Snapshot-only candidates (start a daily snapshot job early)

Past `available_at` cannot be recovered for these, so snapshots should begin as soon as ingestion is approved:
TWSE `/SBL/TWT96U`, `/exchangeReport/BFI84U`, `/exchangeReport/TWTB4U`, `/exchangeReport/TWT85U`, `/opendata/t187ap04_L`, `t187ap09_L`, `t187ap12_L`, `t187ap24_L` to `t187ap27_L`; TPEx `bulletin/warning`, `bulletin/sprc`, and the OpenAPI snapshots.

## Cross-checks for FinMind

`/opendata/t187ap05_L` (monthly revenue, snapshot), `/opendata/t187ap06_L_*` and `t187ap07_L_*` (quarterly financials by industry type), `/company/suspendListingCsvAndHtml` (TWSE delistings: 265 rows from 2001 to 2026, fields DelistingDate, Company, Code only), `/company/newlisting`.

## Skip

ESG (`t187ap46_L_*`), broker statistics, warrants, bonds, funds, board-governance endpoints.
