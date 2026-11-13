# TWSE spikes S1-S4, S8, S9 findings

Requests: 18 (log: research/spikes_twse_reqlog.txt), all to www.twse.com.tw rwd paths, 6 s apart, one in flight. One timed out (client 60 s limit), no HTML error pages, no stop condition hit. Raw responses: research/spikes_twse/. Base URL for all: https://www.twse.com.tw/rwd/zh/

## S1. MI_QFIIS coverage of common stocks
Answer: every common stock (rule `^[1-9][0-9]{3}$`, name not ending `-DR`) in MI_INDEX has a row in the same-date MI_QFIIS. Missing share is 0.00% on all four dates.

| date | common codes (MI_INDEX) | no MI_QFIIS row | share | MI_QFIIS rows |
|---|---|---|---|---|
| 20150601 | 858 | 0 | 0.00% | 915 |
| 20180601 | 915 | 0 | 0.00% | 1051 |
| 20220601 | 964 | 0 | 0.00% | (q2 saved) |
| 20250602 | 1041 | 0 | 0.00% | 1270 |

Missing codes to list: none. Evidence: live requests `fund/MI_QFIIS?date=20180601&selectType=ALLBUT0999&response=json` and `...date=20250602...` (stat OK); 20150601 and 20220601 from saved q1.json/q2.json. MI_QFIIS has more rows than the common set because it also lists ETFs and others (e.g. 0050 with 發行股數 997,500,000 on 20150601).
Confidence: verified-live for 4 dates (the 20220601 and 20150601 files were saved earlier). Unresolved: MI_QFIIS covers only listed (上市) stocks as does MI_INDEX; I did not test delisted codes (they are absent from both by construction) and did not test the other dates in between.

## S2. TWT84U date meaning
Answer: a TWT84U row dated D applies to D. 收盤價 in the row is the PRIOR trading day's close (D-1); 漲停價/跌停價 are the limits for day D, computed from that prior close. It is published before D's trading (inferred; the day-D actual close is not in the row).
Evidence (TWT84U 20200615 saved a3.json, 1116 rows; live MI_INDEX 20200612 (1117 rows) and 20200615 (1116 rows); saved 20200601):
- 1094 stocks with positive closes on both days: 收盤價 in the TWT84U row equals the 20200612 (previous trading day, Friday) close in 1094 of 1094; equals the 20200615 close in only 107 (those unchanged on the day).
- Day-D actual close (20200615) lies inside [跌停價, 漲停價] for 1094 of 1094.
- 0050: row 收盤價 88.25, 漲停 97.05, 跌停 79.45; MI_INDEX close 20200612 = 88.25, 20200615 = 87.00.
- Limit is about 1.1 x prior close for 957 of 965 non-ETF rows within 1% (rest are tick rounding / special rules).
- `最近成交日` is 109.06.12 for 1102 of 1116 rows (the rest earlier, i.e. no trade on the prior day).
- Note: the field list has `開盤競價基準` twice (columns 4 and 6), and row 收盤價 duplicates it for unchanged names; use positional parsing or rename.
Rule for the plan: available_at for a TWT84U row dated D = before the open of D (conservative: use D 08:00 Asia/Taipei if no publish time is known; unverified). Row dated D must not be joined to the D-1 session.
Confidence: verified-live for the date semantics; inferred for the publication time.

## S3. Ranges
(a) TWTAWU 2015: yes. `afterTrading/TWTAWU?startDate=20150601&endDate=20151231&response=json` returns stat OK with 2 rows (title 暫停交易證券, fields 編號, 證券代號, 證券名稱, 暫停交易日期, 暫停交易時間, 恢復交易日期, 恢復交易時間): 910708 恒大健 (104/06/18 to 104/06/22) and 911612 滬安 (104/10/27 to 104/10/30). Both are DRs, so no common stock halts in that window (listing is "全部上市證券"). Verified-live. Earliest available TWTAWU date was not probed.
(b) TWT49U maximum range: no limit found. `exRight/TWT49U?startDate=20150601&endDate=20261113&response=json` returned stat OK, 11,863 rows, first 104年06月01日, last 115年11月13日, all years 104-115 present (counts 723, 734, 781, 825, 880, 888, 973, 1027, 1086, 1184, 1358, 1404), 2.3 MB, 8.8 s on the retry. The first attempt (60 s client timeout) timed out with no response; that is a transient or slow-response failure, not a range limit (retry succeeded). Also OK: 2016-01-01 to 2020-12-31 (4,108 rows, 105年01月06日 to 109年12月30日, 28 s) and 2021-01-01 to 2026-11-13 (7,032 rows, to 115年11月13日, 38 s) and 2015 alone (747 rows) and 2025 alone (1,358 rows). Response has no `total` field and no truncation marker; consistency of counts (full 723 for Jun-Dec 2015 vs 747 for full 2015) suggests no truncation. Verified-live. Residual risk: response time varies from 9 s to over 60 s; use a client timeout of at least 150 s, or chunk by year.

## S4. Common-stock rule leaks (11 saved MI_INDEX per-stock tables, 20150601 to 20250602)
Answer: the rule `^[1-9][0-9]{3}$` plus not ending `-DR` has no leaks and no misses for ordinary common stocks in the 11 sampled dates; the `-DR` name condition is REQUIRED.
(a) Passing the code regex but not common stock: only TDRs with `-DR` names (4 to 7 per date, e.g. 9103 美德醫療-DR, 9105 泰金寶-DR, 9106 新焦點-DR, 9110 越南控-DR); 7 on 2015-2017, 6 on 2018-2019, 5 on 2020-2021, 4 on 2022-2025. They are removed by the name condition. After the name condition no passing row looked like a preferred share, ETF, ETN, beneficiary certificate or special share. A keyword scan of passing names (特, 甲, 乙, 丙, ETF, ETN, 受益, 傳, 購, DR ...) found only false positives that are ordinary companies (遠傳, 特力, 力特, 懷特, 邁達特, 富爾特, 凱基金, 傳奇, 三商家購, 全球傳動, 格威傳媒, 惠特, 乙盛-KY, 寶綠特-KY). Pass counts: 858, 877, 896, 915, 930, 942, 952, 964, 975, 1011, 1041 for the 11 dates in date order (2015...2025); no `F-` names exist in any table (foreign companies are `-KY` and pass; KY names in pass: 43 in 2015 up to 88 in 2025, all legitimate common stocks).
(b) Failing the rule, ordinary-looking: none that are common stock. The failing rows are: 0-prefixed ETFs/REIT/ETN codes (34 in 2015 up to 216 in 2025), `-DR` TDRs, letter-suffixed preferred shares (4-digit + letter, `...特`, `...甲特`, `...乙特`: 3 in 2015, 26 in 2025, e.g. 1101B 台泥乙特, 2002A 中鋼特, 1312A 國喬特, 5871A 中租-KY甲特, 2887Z1 台新新光己特), and 6-digit TDR codes (e.g. 910322 康師傅-DR, 911609 揚子江 whose name lacks `-DR`). All correctly excluded.
Surprise: names carry a trailing `*` for some common stocks (2327 國巨*, 4763 材料*-KY, 6415 矽力*-KY, 8070 長華*; 4 on 2015-06-01, 10 on 2025-06-02). Keep names verbatim and strip `*` before name matching; it appears to mark non-NT$10 par value (inferred, not verified). Rule remains safe because the check is only on a trailing `-DR`.
Extra condition needed: no; keep the `-DR` clause. Optionally also exclude 6-digit and letter-suffix codes (already excluded by the regex).
Confidence: verified locally on 11 dates only; a new listing category (for example 創新板 `-創`, seen as `7631 聚賢研發-創` in TWT49U 2025) would pass the regex and is a common stock; whether `-創` names exist in MI_INDEX was not checked beyond the 11 dates (none found in them).

## S8. Corporate-action fields (2025 window, startDate=20250101 endDate=20251231)
TWT49U (`exRight/TWT49U`, 1,358 rows): fields: 資料日期, 股票代號, 股票名稱, 除權息前收盤價, 除權息參考價, 權值+息值, 權/息, 漲停價格, 跌停價格, 開盤競價基準, 減除股利參考價, 詳細資料, 最近一次申報資料 季別/日期, 最近一次申報每股 (單位)淨值, 最近一次申報每股 (單位)盈餘. Example: ['114年01月02日','00940','元大台灣價值高息','9.41','9.38','0.030000','息','10.31','8.45','9.38','9.38','00940,20250102','115年11月13日(https://mops...)','12.39','N/A']. Dates are ROC with 年月日 characters. `權/息` values over the full 2015-2026 pull: 息 10,298, 權息 914, 權 651. Notes state the table excludes 除息併案辦理退還股款減資 and 分割減資 data; ETFs, TDRs, beneficiary certificates are explicitly in scope.
TWTAUU (`reducation/TWTAUU`, 17 rows, 2025): fields: 恢復買賣日期, 股票代號, 名稱, 停止買賣前收盤價格, 恢復買賣參考價, 漲停價格, 跌停價格, 開盤競價基準, 除權參考價, 減資原因, 詳細資料. Example: ['114/02/12','2025','千興','10.50','17.09','18.75','15.40','17.10','--','彌補虧損','2025  ,20250204']. 減資原因: 退還股款 11, 彌補虧損 6. Date format is `YYY/MM/DD` (slashes), differing from TWT49U. Stocks only; no 0-prefixed code.
0050: appears in TWT49U, not in TWTAUU. TWT49U 2025 rows: 114年01月17日 (close 198.05, ref 195.35, 息 2.70) and 114年07月21日 (51.45, 51.09, 息 0.36). Other years, all from live pulls: 104年10月26日; 105年07月28日; 106年02月08日 and 07月31日; 107年01月29日 and 07月23日; 108年01月22日 and 07月19日; 109年01月31日 and 07月21日; 110年01月22日 and 07月21日; 111年01月21日 and 07月18日; 112年01月30日 and 07月18日; 113年01月17日 and 07月16日; 115年01月22日 and 07月21日. So every 0050 cash dividend is covered back to 2015-06-01 (one per year until 2015, two per year from 2016 on). ETFs are covered by TWT49U (e.g. 00940, 00946, 00953B, 0056, 006203 in 2025).
Split wording: no row in TWT49U (2015-06 to 2026-11) or TWTAUU (2025) contains 分割, 面額 or 拆. A stock split is NOT captured: 0050 closed 175.90 on 20250602 (MI_INDEX) and 51.45 before the 2025-07-21 ex-dividend (about a 4-for-1 split between those dates, inferred from prices), yet TWT49U has no 0050 row between 2025-01-17 and 2025-07-21 and the notes exclude 分割減資. Adjusted-price construction must find splits elsewhere (not found in these endpoints).
Confidence: verified-live for fields, 0050 rows and absence of split wording; the split inference is from prices only.

## S9. 2015 sampling (MI_INDEX, type=ALLBUT0999)
All six requested dates were trading days (no holiday responses), plus 20150601 saved.

| date | per-stock rows | tables | total return index table | field list equals 2016 |
|---|---|---|---|---|
| 20150302 | 913 | 10 | yes, 報酬指數(臺灣證券交易所) 42 rows | yes |
| 20150401 | 915 | 10 | yes, 42 | yes |
| 20150504 | 917 | 10 | yes, 42 | yes |
| 20150601 (saved) | 919 | 10 | yes, 42 | yes |
| 20150701 | 922 | 10 | yes, 42 | yes |
| 20150901 | 925 | 10 | yes, 42 | yes |
| 20151201 | 936 | 10 | yes, 42 | yes |

Per-stock fields (identical on all dates and to 20160601): 證券代號, 證券名稱, 成交股數, 成交筆數, 成交金額, 開盤價, 最高價, 最低價, 收盤價, 漲跌(+/-), 漲跌價差, 最後揭示買價, 最後揭示買量, 最後揭示賣價, 最後揭示賣量, 本益比. Total return table has fields 報酬指數, 收盤指數, 漲跌(+/-), 漲跌點數, 漲跌百分比(%), 特殊處理註記 and its first rows are 寶島股價報酬指數, 發行量加權股價報酬指數, 臺灣50報酬指數, 臺灣中型100報酬指數. Differences from later years: 2015 has only 10 tables (the 跨市場 and 臺灣指數公司 index tables are present but empty, as is the 2016 return table count of 43 vs 42 in 2015); price index table grows 47 to 51 rows during 2015; 2016 has 報酬指數 43 rows and 價格指數(臺灣指數公司) 1 row. The rule for locating the per-stock table by title containing 每日收盤行情 works on every date. Verified-live.

## Facts that contradict or refine the notes in the prompt
1. The first TWT49U full-range attempt failed (client timeout), but a retry of the identical URL worked in 8.8 s; no range limit exists up to 11.4 years. The prompt's fallback of "one year" was not needed.
2. TWT84U 收盤價 is not "the day's close" and not the post-close value: it is the previous trading day's close, and the field list has a duplicated column name 開盤競價基準.
3. 0050 does appear in TWT49U (ETFs are covered); the prompt hinted it might not. It does not appear in TWTAUU (stocks only).
4. The prompt expected stock-split/par-value wording might be present: it is absent; splits are not covered by TWT49U or TWTAUU.
5. MI_INDEX per-stock names contain a trailing `*` on some common stocks, which the prompt's rule does not mention.
6. The prompt said the `-DR` exclusion is part of the rule; it is essential (4 to 7 four-digit DR codes pass the regex on every date).
7. TWTAWU 2015 returns only 2 rows, both TDRs, so a 2015 window works but is nearly empty.
8. The prompt's "20150601 saved MI_INDEX" path was under probe/ (twse_mi_index_2015.json), not probe3/; both exist as stated.
