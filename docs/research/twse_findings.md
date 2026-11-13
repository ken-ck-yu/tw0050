# TWSE probe findings (PARTIAL: stopped early by the 3-failures-in-a-row rule)

Requests used: 14 of 80, all to www.twse.com.tw or openapi.twse.com.tw, 5 s apart. Requests 12, 13, 14 were three consecutive HTTP 200 HTML-404 pages (blind path guesses for TWT85U), so per the rules I stopped. Raw files are in the twse/ subfolder next to this file. Most of Q1(c-e), Q2, Q3 and Q4 are NOT answered live. What is below is verified live where stated, otherwise taken from the OpenAPI swagger saved in request 8 (no further request needed).

## Q1 Status-type datasets

### (a) TWT84U price limit table - VERIFIED LIVE
- URL: `https://www.twse.com.tw/rwd/zh/variation/TWT84U?date=YYYYMMDD&response=json` (folder is `variation`, NOT `afterTrading`; `afterTrading/TWT84U` returned the HTML 404).
- 20200615: stat OK, 1116 rows, title "股價升降幅度", date field 20200615. First row 0050 元大台灣50, last 9958 世紀鋼. Fields: 證券代號, 證券名稱, 漲停價, 開盤競價基準, 跌停價, 開盤競價基準 (today group, then prior-day group), 收盤價, 買進揭示價, 賣出揭示價, 最近成交日, 可否零股交易. The groups block labels the first three price columns "本日" and the next four "前日".
- 20150615: stat OK, 922 rows, same fields, first 0050 台灣50, last 9958 世紀鋼, 最近成交日 104.06.12 (the Friday before the Monday date). So history reaches at least 2015-06 and the table carries per-stock limit-up/limit-down prices and the reference price for the date asked.
- This is a per-stock per-day limit price table (the actual limit prices, which already embed the 7% to 10% rule change of 2015-06-01). Row counts (922 vs 1116) are consistent with growth in listings; it is not obviously restricted to survivors but that was not tested.
- Granularity: one request per date. Date values inside rows use ROC dotted form `109.06.12`; the title uses `109年06月15日`.
- Not tested: whether a non-trading date returns empty data; how early history goes before 2015.
- Confidence: verified live.

### (b) TWTAWU suspended securities - PARTIALLY VERIFIED
- URL: `https://www.twse.com.tw/rwd/zh/afterTrading/TWTAWU?startDate=YYYYMMDD&endDate=YYYYMMDD&response=json`.
- 20200601 to 20200630: stat OK, 5 rows. Fields: 編號, 證券代號, 證券名稱, 暫停交易日期, 暫停交易時間, 恢復交易日期, 恢復交易時間. Example row: 054467 隆達凱基97購01, halt 109/06/18 8:00, resume 109/06/19 8:00 (warrant and stock entries, e.g. 3698 隆達).
- Not tested: 2015-06 window and maximum range length. So history depth to 2015 is NOT verified.
- Openapi `/exchangeReport/TWTAWU` has no parameters (current list only), same fields in English.
- Confidence: verified live for 2020 only; 2015 not found.

### (c) TWT85U changed-trading securities and full-delivery status - NOT FOUND
- Guessed rwd paths `afterTrading/TWT85U` and `announcement/TWT85U` returned the HTML 404; `variation/TWT85U` also returned the HTML 404 (request 12, with `date=`). The correct folder is unknown.
- Openapi `/exchangeReport/TWT85U` (集中市場證券變更交易) has no parameters and fields Code, Name, PeriodicCallAuctionTrading, i.e. a current snapshot only (inferred from the swagger, not fetched).
- Openapi `/exchangeReport/BFI84U` (停資停券預告表) has fields Code, Name, StartDate, EndDate, Reason; this is margin/short suspension, not full delivery. Also unfetched.
- No TWSE source of full-delivery (全額交割) status was found; the swagger list has no endpoint with that name. It is not settled whether the rwd site has one.
- Confidence: not found.

### (d) TWT96U borrowable shares - NOT TESTED
- Openapi `/SBL/TWT96U` (上市上櫃股票當日可借券賣出股數) has no parameters and fields TWSECode, TWSEAvailableVolume, GRETAICode, GRETAIAvailableVolume (current day only, per the swagger). rwd path and history not probed.
- Confidence: not found.

### (e) Holiday schedule history - NOT TESTED
- Openapi `/holidaySchedule/holidaySchedule` has no parameters (fields Name, Date, Weekday, Description), which suggests current year only; not fetched, so unconfirmed. rwd equivalent not found.

### MFI94U total-return index - NOT TESTED beyond the swagger
- Openapi `/indicesReport/MFI94U` has fields Date and TAIEXTotalReturnIndex only (TAIEX only, no Taiwan 50 total return). The lead's note says MI_INDEX already carries both TAIEX and Taiwan 50 total return indexes, so from the swagger MFI94U has no advantage in content. Unconfirmed whether its rwd form gives a long history in one request (a possible advantage: a whole month or year per request instead of one date).

## Q2 Shares issued history - NOT ANSWERED LIVE
- `t187ap03_L` (openapi `/opendata/t187ap03_L`, 上市公司基本資料): no parameters in the swagger, one 出表日期 per file, and a field 已發行普通股數或TDR原股發行股數. That makes it a snapshot with no date selector (inferred, not fetched). It also would only list currently listed companies.
- No dated endpoint tested (MI_QFIIS and listed-company reports not probed). Not found.

## Q3 Delisted names - PARTLY ANSWERED FROM SWAGGER ONLY
- Openapi `/company/suspendListingCsvAndHtml` (終止上市公司) has fields DelistingDate, Company, Code and no parameters. Depth of history and row count not fetched.
- (b) STOCK_DAY last dates for 3 delisted stocks: not done.
- (c) MI_INDEX 2016-06-01 survivorship check: not done.
- Confidence: inferred only.

## Q4 Request granularity (what was seen)
- TWT84U: one request per date (all stocks, ~900 to 1100 rows).
- TWTAWU: one request per date range (a 30-day window gave 5 rows); max range unknown.
- Others from the lead's notes were not re-verified here. Budget arithmetic for 2015-06 to 2026-11: 2015-06-01 to 2026-11-13 is about 11.45 years, about 2,780 trading days at roughly 243 days per year. One request per date for TWT84U is about 2,780 requests. At the 5 s spacing that is about 3.9 hours. Per-stock-month STOCK_DAY: 138 months times the stock count (about 1,000 plus delisted) is about 138,000 requests, which is the reason to prefer MI_INDEX one request per date.

## Decision for the author
- Whether to continue probing after the 3-failure stop. Context: the three failures were HTML 404s from guessing rwd folder names, not IP-block responses, but the rule says stop. Option 1: accept the gaps above and re-dispatch with the exact page URLs for TWT85U, TWT96U, MFI94U, MI_QFIIS and the holiday and delisted pages (the page-to-rwd-folder map cannot be found from the TWSE home, sitemap or report-index HTML, which load their menus dynamically). Option 2: explicitly permit a small number of further guesses.

## Facts that correct or add to the notes in the instructions
- The report pages are not at `zh/trading/exchange/<REPORT>.html`: `TWT84U.html` there returned a 404 page. The suggested method (fetch the report's HTML page and read its JS) could not be followed because the page location is not discoverable from `/zh/`, `/zh/sitemap.html` or `/zh/report-index.html` (static HTML has no report links; menu is built by JavaScript).
- TWT84U lives under rwd folder `variation`, not `afterTrading`.
- TWTAWU lives under `afterTrading` and takes startDate/endDate.
- TWSE answers a missing page with HTTP 200 and an HTML 404 title "404", as warned.
- TWT84U returns real historical limit-up/limit-down prices for 2015-06-15, which is a useful dataset the plan may not have counted.

---
# UPDATE (second pass, Q2 and Q3, requests 15 to 21; total used 21 of 80 by my count)
This section supersedes the "NOT ANSWERED" notes for Q2, Q3 and Q4 above. No failures in this pass. (Note: my counter shows 21 used, so 59 left, not 66; the coordinator's figure differs from mine.)

## Q2 Shares issued history - VERIFIED LIVE via MI_QFIIS
- URL: `https://www.twse.com.tw/rwd/zh/fund/MI_QFIIS?date=YYYYMMDD&selectType=ALLBUT0999&response=json` (works with no guessing).
- 20150601: stat OK, 915 rows, first 0050 (發行股數 997,500,000), last 9958 世紀鋼 (181,919,707).
- 20220601: stat OK, 1141 rows, first 0050 (1,745,500,000), last 9958 (232,361,031).
- Fields: 證券代號, 證券名稱, 國際證券編碼 (ISIN), 發行股數, 外資及陸資尚可投資股數, 全體外資及陸資持有股數, 尚可投資比率, 持股比率, 共用法令投資上限比率, 陸資法令投資上限比率, 與前日異動原因(註), 最近一次上市公司申報外資及陸資持股異動日期. Numbers are strings with thousands commas; ratios are numbers or strings; 0 appears in the last column when no date.
- Coverage includes later-delisted stocks: the 2015-06-01 file contains 78 codes that appear in the openapi delisted list, e.g. 2384 勝華科技 (delisted 104/07/07), 2361 鴻友科技 (104/12/28), 2833 台灣人壽 (104/10/15), 2311 日月光 (107/04/30), 2325 矽品 (107/04/30). The 2022-06-01 file has 19 such codes.
- Caveats: (1) one row has a leading tab character in the name (`\t鴻友科技`), so strip names. (2) 發行股數 is the issued-share count as of the report date per TWSE; it is a report-date value, and whether `available_at` equals the date asked was not tested. (3) The rows are ISIN-keyed, which helps with code reuse. (4) Row counts (915 and 1141) are similar to the MI_INDEX stock counts, so it looks like all listed common stock; warrants are not present.
- `t187ap03_L`: the swagger shows no parameters and a single 出表日期 per record, field 已發行普通股數或TDR原股發行股數; it lists current companies only. Treat as snapshot only (inferred from the swagger; I did not fetch it). So MI_QFIIS per date is the dated source.
- Granularity: one request per date. Confidence: verified live.

## Q3 Delisted names
### (a) Delisted list - VERIFIED LIVE
- `https://openapi.twse.com.tw/v1/company/suspendListingCsvAndHtml` returned a JSON list of 265 objects with fields DelistingDate (ROC `YYY/MM/DD`), Company, Code only. Earliest 090/01/20 (2001) 國豐企業 2334; latest 115/09/01 (2026-09-01) 三商壽 2867. Per ROC year counts: 090:16, 091:31, 092:14, 093:10, 094:19, 095:14, 096:20, 097:12, 098:3, 099:12, 100:8, 101:6, 102:7, 103:7, 104:8, 105:10, 106:8, 107:10, 108:8, 109:7, 110:10, 111:13, 112:2, 113:3, 114:3, 115:4.
- Caveats: no listing date, no reason (merger, voluntary, bankruptcy, move to TPEx are not distinguished), and codes can be reused: 2301 光寶電子 (091/11/04) shares its code with today's 光寶科, so a code-only join gives false positives (this inflates the 78 and 66 counts by at least one). 2888 新光金 (114/07/24) is a merger where the code continues under a renamed entity. Depth: it is a complete-looking list from 2001, but whether it is exhaustive was not verified. Join on code plus date window or ISIN.
- Not tested: whether an rwd equivalent exists.

### (b) STOCK_DAY near delisting - VERIFIED LIVE (3 stocks)
URL `https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY?date=YYYYMMDD&stockNo=CODE&response=json` (returns the month containing the date).
- 2475 華映, delisted 108/05/13 (2019-05-13): month 201905 returned 7 rows, first 108/05/02, last 108/05/10 (the Friday before). Last trading date found: 2019-05-10.
- 3474 華亞科, delisted 105/12/06 (2016-12-06): 201612 returned stat "很抱歉，沒有符合條件的資料!" (no data); 201611 returned 21 rows, last 105/11/29. Last trading date found: 2016-11-29, one week before the delisting date.
- 2847 大眾銀行, delisted 105/03/22 (2016-03-22): 201603 returned 7 rows, first 105/03/01, last 105/03/09. Last trading date found: 2016-03-09, 13 days before the delisting date.
- Conclusion: daily prices exist up to shortly before delisting (gap between last trade and delisting date is 3 to 13 calendar days, plausibly a trading halt before the formal date; not investigated). An empty month returns stat not OK with only `stat` and `total` keys.

### (c) MI_INDEX 2016-06-01 survivorship - VERIFIED (saved file, no request)
- The saved file's "每日收盤行情(全部(不含權證、牛熊證、可展延牛熊證))" table has 951 rows. 66 codes appear in the delisted list. Genuine later-delisted examples: 2475 華映 (delisted 2019-05-13), 3474 華亞科 (2016-12-06), 2311 日月光 (2018-04-30), 2325 矽品 (2018-04-30), 2448 晶電 (2021-01-06), 6702 興航 (2017-02-02), plus DR stocks such as 9106 新焦點-DR. Confirms the all-stock daily file is survivorship-free.

## Q4 Request arithmetic (2015-06-01 to 2026-11-13)
- Trading days: about 11.45 years times about 243 = about 2,780. (Taiwan has about 240 to 247 trading days per year; exact count to come from the daily files themselves.)
- One request per date: MI_INDEX about 2,780; MI_QFIIS (issued shares and foreign holding) about 2,780; TWT84U (limit prices) about 2,780. BWIBBU_d, from the lead's notes, is also per date: about 2,780 each.
- Per date range: TWTAWU, exRight/TWT49U, reducation/TWTAUU, punish, notice take startDate/endDate; per-year chunks give about 12 requests each (about 12 for 2015-06 to 2026-11 if one request per year works; max range unverified).
- One-offs: delisted list 1; openapi snapshots 1 each.
- STOCK_DAY is per stock-month: 138 months x about 1,000 stocks = about 138,000 requests, so use MI_INDEX per date instead and use STOCK_DAY only for spot checks.
- Total if MI_INDEX, MI_QFIIS, TWT84U and BWIBBU_d are all collected per date: 4 x 2,780 = about 11,120 requests plus about 100 others. At 5 s spacing that is about 15.5 hours; at 12 requests per minute equals the same. If the hourly cap is lower than 720 requests per hour the limiter must slow it.

## Updated unresolved list
TWT85U path, full delivery (coordinator will list as unresolved), TWT96U history, holiday history, MFI94U rwd form, whether TWTAWU reaches 2015, whether MI_QFIIS values on a given date are available at close of that date.

## Updated corrections list
- Code reuse exists in the delisted list (2301), so it cannot be joined on code alone.
- MI_QFIIS is a dated TWSE source of 發行股數 back to at least 2015-06-01, including later-delisted stocks.
- Coordinator's remaining-request count (66) differs from mine (59).
