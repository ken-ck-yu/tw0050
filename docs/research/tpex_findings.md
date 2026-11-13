# TPEx probe findings (2026-11-13)

Requests: 54 to tpex.org.tw (log: reqlog.txt, limit 80), at least 5 s apart, one at a time. No TWSE, no FinMind, no token. Raw responses in `tpex/`.
Base pattern: `https://www.tpex.org.tw/www/zh-tw/<group>/<report>?...&response=json`. Success = JSON, `stat == "ok"`, non-empty `tables[0].data`.

## How the real paths were found (reusable)
- Menu of every page: `https://www.tpex.org.tw/data/menu/zh-tw/menu.json` (page URL list, verified live).
- Each page HTML contains `action:"<group>/<report>"` in its script (e.g. `action:"bulletin/disposal"`) = the www path. Its `#tables-form` inputs (`name=...`) = the query parameters.
- A wrong HTML page path returns HTTP 302 to `/errors` (not 200 here). A wrong www path also 302 (cmode guess).
- Holiday/no-data day returns `stat ok` with 0 rows (2025-05-30 `otc` = 0 rows, Dragon Boat holiday) - empty is not an error.
- Some endpoints with a normal-looking 200 return `stat` as a message string (sprc: `資料日期:115/11/14，本日無暫停/恢復交易股票資訊`), so test `stat == "ok"` exactly.

## Q1. Trading-restriction history

| Item | www path and params | History? | Evidence |
|---|---|---|---|
| (a) Disposition 處置有價證券 | `bulletin/disposal?startDate=YYYY/MM/DD&endDate=YYYY/MM/DD&type=all&response=json` (also `code`, `cate`, `reason`, `measure`, `order`) | YES, from 2003-09 (page note; 2002-02..2003-08 only as static HTML `/storage/disposal_history/2002.htm`) | 2015-06-01..30: ok, 31 rows. 2020-06-01..30: ok, 79 rows. Fields: 編號, 公布日期, 證券代號, 證券名稱, 累計, 處置起訖時間, 處置原因, 處置措施, 處置內容, 收盤價, 本益比. Includes convertible-bond codes (e.g. 47031). Range is by disposal period overlap: the June query returned rows announced 104/05/18. |
| (b1) Attention 注意股票 | `bulletin/attention?startDate=..&endDate=..&type=all&response=json` | YES, from 2002-02 (page note) | 2015-06: 124 rows. 2020-06: 398 rows. Full year 2020-01-01..12-31: 3277 rows (no row cap seen; June subset = 398, identical). Fields: 編號, 證券代號, 證券名稱, 累計 (cumulative count), 注意交易資訊, 公告日期, 收盤價, 本益比, link. |
| (b2) Cumulative-count warning 累計次數可能達處置標準 | `bulletin/warning?response=json` | NO, latest snapshot only | Page has no date inputs. `startDate=2020/06/01&endDate=...` returned byte-identical output to the plain call (5 rows, date 20261113). Per-day history of the count is available instead from the attention file's 累計 column. |
| (c) Changed trading / split trading / managed stock / stop trading 變更交易、分盤交易、管理股票、停止交易 | `afterTrading/chtm?date=YYYY/MM/DD&response=json` (page `/zh-tw/mainboard/trading/info/altered.html`) | YES, per day, from 2008-04-09 (page note; 2005-06..2008-04-08 via a separate link not tested) | 2015-06-15: 34 rows. 2020-06-15: 43 rows. Fields: 證券代號, 證券名稱, 變更交易, 分盤交易, 屬管理股票, 分盤或管理股票撮合循環時間(分鐘), 停止交易, 財務資訊重點專區, 公告連結. Flag value is the full-width letter `Ｙ` (U+FF39), not ASCII Y. Openapi `/tpex_cmode` is the latest snapshot only. 全額交割 has no own column; the status was folded into 變更交易 (inferred, not verified). Status is a full state list per day (not an event list). |
| (d) Suspension/resumption 暫停/恢復交易 | page `/zh-tw/announce/market/halt.html`, www `bulletin/sprc` | NO via www: today only. Date params ignored (2015-06 and 2020-06 queries returned the "no data today" message). Openapi `/openapi/v1/tpex_spendi_history` returns only the current ROC year (365 rows, all `Date` = `115`, so 2026 only). | Fields (openapi): Date, Serial, SecuritiesCompanyCode, CompanyName, DateOfSuspendedTrading, TimeOfSuspendedTrading, DateOfResumedTrading, TimeOfResumedTrading (compact ROC `1150618`). Prior-year history not found. Partial substitute: `chtm` per day has the 停止交易 flag. Warrant and ETN suspensions are separate. |

Confidence: verified live for all rows above; the 全額交割 mapping is inferred; pre-2026 suspension history = not found.
Unresolved: whether `spendi_history` accepts a year parameter (swagger lists none; not tested); whether a suspension-history HTML page exists outside the menu.

## Q2. Capital reductions
- `bulletin/exDailyQ` does NOT include capital reductions. Checked all of 2016 (510 rows, one request): 權/息 values are only 除息 403, 除權息 76, 除權 31; no row contains 減資. Fields have no reduction columns. Verified live for 2016 only (and 2015-06..09 by the notes).
- Separate report exists: page `/zh-tw/announce/market/reduction/reference.html`, www `bulletin/revivt?startDate=YYYY/MM/DD&endDate=YYYY/MM/DD&response=json`. Page note: data from 2013-01 (民國102年1月).
  - 2015-01-01..12-31: ok, 19 rows (first resume date 104/01/30, last 104/12/31).
  - 2022-01-01..12-31: ok, 20 rows (first 111/01/10).
  - Whole-year ranges work. 2016 to 2021 not individually tested.
- Fields: 恢復買賣日期 (compact ROC, e.g. `1040130`), 股票代號, 名稱, 最後交易日之收盤價格 (last close before halt), 減資恢復買賣開始日參考價格 (reference price), 漲停價格, 跌停價格, 開始交易基準價, 除權參考價, 減資原因 (reason, e.g. 彌補虧損), 詳細資料 (HTML table inside the string: 停止買賣日期, 恢復買賣日期, 每壹仟股換發新股票 ...). The detail HTML carries the halt start date and exchange ratio; it needs HTML parsing.
- Related but not tested: reduction notice `/zh-tw/announce/market/reduction.html` (減資預告表), par-value change reference `/zh-tw/announce/market/change/reference.html`.
Confidence: verified live (2015, 2022); other years inferred.

## Q3. Delisting and survivorship
(a) List: page `/zh-tw/mainboard/listed/delisted.html`, www `company/deListed?date=YYYY&code=&reason=-1&response=json`. Fields: 股票代號, 公司名稱 (full legal name), 終止上櫃日期 (`107-11-29`, ROC with hyphens), 終止上櫃原因 (rule article), 公司資料網址. `date` = ROC-or-Gregorian year accepted as Gregorian (`2018`, `2016`, `2022` worked). With no params it returns the current year only (7 rows for 2026).
 Rows per year: 2016: 10, 2018: 9, 2022: 7, 2026: 7. Earliest year not found: the page input has `data-start=20210101` but 2016 and 2018 returned data, so depth is at least 2016; earlier years not tested.
 WARNING completeness: these counts look low for a market of ~800 stocks. 2018 with reason=2 (轉上市, moved to TWSE) returned 0 rows and reason=0 (merger) returned 7 of the 9. Whether transfers to TWSE are in this list is NOT established; do not assume it is a complete survivorship list. Code field can carry trailing space (`'1752 '`).
(b) Last trading date, using per-stock monthly endpoint `afterTrading/tradingStock?code=<c>&date=YYYY/MM/01&response=json` (1 request per stock-month; fields 日期, 成交仟股, 成交仟元, 開盤.. 筆數):
| Stock | Delist date (list) | Last trade found | Gap |
|---|---|---|---|
| 3658 (list says 漢民微測科技; daily file says 漢微科) | 105-11-22 | 105/11/15 | 7 calendar days, no rows 11/16-11/21 |
| 3299 帛漢 | 107-11-29 | 107/11/21 | 8 days; cross-check: `otc` 2018-11-22 (798 rows) has no 3299 |
| 5306 桂盟 | 111-03-08 | 111/03/07 | 1 day |
So last trade can precede the delisting date by a week or more (cause of the gap not checked; probably a halt before termination). Do not use the delisting date as the last-trade date. Name changes between list and daily files exist.
(c) `otc` 2016-06-01: ok, 720 rows. It contains later-delisted 3658 漢微科, 3299 帛漢, 8266 中日新, 3291 遠翔科, 8082 漢承泰, 8079 誠遠, 5306 桂盟 (delisted 2016-2022), and 3428 光燿科. Not present (listed before/after or not yet listed): 8925, 6250, 3528, 8053 (delisted 2016-05, before the date), 6554. Answer: yes.
Confidence: verified live (a, b, c); completeness of (a) unresolved.

## Q4. Unit hazard
- The label change is NOT on 2025-06-02. Label `(千股)` is on 2025-01-02, 01-08, 01-09. Label `(張數)` is on 2025-01-10, 01-13, 01-17, 02-17, 04-01, 05-29, 06-02. First `(張數)` day = 2025-01-10 (2025-01-09 is the last `(千股)` day; both days fetched). The 2025-06-02 file has the same 17 fields as 2025-01-10. So the notes' "3 variants" is really 2 label variants for the new field set, with the switch on 2025-01-10; 2025-06-02 is not special.
- Units: `成交股數` = shares in all dates (values are multiples of 1,000; e.g. 6488 on 2025-05-29: 2,324,000). Last bid/ask volume: 6488 values 2025-01-02 `6`/`5`, 2025-01-08 `13`/`4`, 2025-01-10 `20`/`1`, 2025-05-29 `115`/`4`. All small integers, scale consistent with lots. Across all stocks the median bid volume = 3 and median ask volume = 2 on every one of 2025-01-02, 01-08 (labelled 千股) and 01-10, 01-13, 01-17, 04-01 (labelled 張數). Thousand shares = lots (1 lot = 1000 shares), so the numbers did not change; only the label was corrected. In both eras: unit = lots = thousand shares. No effect on `成交股數`.
- Caveat: the numeric-equality conclusion is from distribution (median) comparison and magnitude, not from an independent order-book source.
- Odd-lot: from 2025-01-10 a few rows have 成交股數 not a multiple of 1000 (e.g. 00687C 37,200); 2025-01-08 all multiples of 1000 (ratio 1.0 vs 0.9989). Possibly bond-ETF type rows; not investigated. `成交仟股` in the per-stock monthly endpoint is thousand shares (unit differs from `otc`).
Confidence: verified live (label dates); unit equivalence inferred from medians.

## Q5. Request granularity and arithmetic (2015-06-01 to 2026-11-13)
Weekdays in range: 2990; trading days about 2,820 (subtract roughly 12 to 15 holidays per year; exact calendar not computed).
| Endpoint | Granularity | Requests |
|---|---|---|
| `afterTrading/otc` | per day (holiday returns 0 rows) | about 2,820 (or 2,990 if all weekdays are requested) |
| `afterTrading/chtm` | per day, state snapshot | about 2,820 |
| `bulletin/attention`, `bulletin/disposal` | date range; full-year ranges work (3277 rows in one reply, 895 KB) | 12 yearly (or 138 monthly) each |
| `bulletin/exDailyQ` | date range; full year 2016 worked (510 rows) | 12 yearly |
| `bulletin/revivt` | date range; full year worked | 12 yearly |
| `company/deListed` | per year | 12 |
| `afterTrading/tradingStock` | per stock per month | stocks x 138 months; not needed if `otc` is collected |
| `bulletin/warning`, `bulletin/sprc`, `/openapi/v1/tpex_*` snapshots | latest only; must be collected going forward daily | 1 per day from now |
Unverified: whether a very large range is silently truncated for any report (attention returned 3277 rows without a cap; exDailyQ 510 rows not cross-checked against a count).

## Decision for the author
1. Delisted list completeness. Context: `company/deListed` returned 7 to 10 rows per year and 0 transfers to TWSE for 2018. Options: (a) accept as the survivorship source and add a check that every code seen in daily `otc` files but missing later has a delisting row; (b) also derive disappearance dates from the daily `otc` files (first and last date each code appears), which is complete by construction but has no reason; (c) add TWSE-side data for transfers (outside this probe's scope).
2. Suspension history before 2026 is not available on TPEx in this probe. Options: (a) use `chtm` per day 停止交易 flag as the historical proxy; (b) collect `sprc` and openapi snapshots daily from now on and accept no history; (c) investigate FinMind or MOPS announcements (not probed).

## Facts that contradict or correct the notes in the task
1. The `(千股)` to `(張數)` relabel happened on 2025-01-10 (last 千股 day 2025-01-09), not 2025-06-02. The 2025-06-02 file is the same variant as 2025-01-10.
2. The numbers did not change unit with the label; both mean lots (= thousand shares).
3. `exDailyQ` has no capital-reduction rows; reductions are in `bulletin/revivt`.
4. `/tpex_exright_daily` and the other swagger endpoints are snapshots; `/tpex_spendi_history` is current year only despite its name.
5. A wrong page URL returns HTTP 302 to /errors here, not 200 with an error body.
6. Names differ between the delisted list and daily files (3658). Last trade can be a week or more before the delisting date.
7. Server clock showed `115/11/14` in an empty sprc reply while the local date is 2026-11-13 (a timezone or one-day offset on the server; not investigated).
