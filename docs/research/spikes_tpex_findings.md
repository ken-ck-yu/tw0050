# TPEx spikes findings (S2, S3, S4, S8, S9)

18 live requests, all to https://www.tpex.org.tw/www/zh-tw/, 5 s apart, no failures. Raw responses are in `research/spikes_tpex/`. Request log: `research/spikes_tpex_reqlog.txt`. Helper scripts: `s2.py`, `s4.py`, `sp_fetch.sh`, `bis.sh` in `research/`.

## S2 Next-day limit columns (verified-live on saved files, no request needed)

**Answer.** The `次日漲停價` and `次日跌停價` columns in file D are the limit prices for the next trading day.
- Stocks: up is about 1.10 x close, down is about 0.90 x close, rounded to the tick. 
- Check on the pair 20250109 to 20250110 (both saved): 
  - Of 932 rows with a close, 833 had up within one tick of 1.10 x close. 98 of the other rows are `9999.95` / `0.01`, which means no price limit (bond ETFs such as 00679B and 00687B). One mismatch was a stock: 6488 close 369.00, up 400.00, down 328.00. These are not 1.10 x close, so a reference price adjusted for an ex-dividend or similar event is likely. This is inferred from the pattern, not looked up.
  - D+1 close lay inside D's [down, up] for 923 of 923 rows with a D+1 close, 0 outside.
- Pair 20250108 to 20250109: 923 of 923 inside, one non-ETF mismatch (6488 again).
- Pair 20250529 to 20250602: 917 of 917 inside. The mismatch is 6788: close 225, up 236.5, down 193.5. 
- 20250530 is NOT a trading day. It was a Dragon Boat holiday, the file has `ok` and 0 rows. The prompt's example pair 20250529/20250530 is therefore invalid. 20250529 to 20250602 is the consecutive trading pair, with 20250531 a Saturday.

**Shift rule.** Store D's `次日漲停價` / `次日跌停價` as `limit_up` / `limit_down` on the next trading day D+1, where D+1 is the next date with a non-empty file. The `available_at` can be D's close time. This is a trading-calendar shift, not a +1 calendar day shift. For the last day of a file range, the limit belongs to a day with no file yet.
Treat `9999.95` and `0.01` as the "no limit" sentinel and store them as null.
The columns exist in the 15-field layout too (2015, 2016 files), so the rule holds for the whole history. Not checked with value tests before 2025; inferred from the field presence only.

**Confidence.** High for the 2025 shift rule. Medium for the sentinel and the mismatch explanation.

## S3 revivt 2016 to 2021 and exDailyQ 2025 (verified-live)

| year | rows | first `恢復買賣日期` | last |
|---|---|---|---|
| 2016 | 27 | 1050108 | 1051229 |
| 2017 | 25 | 1060330 | 1061215 |
| 2018 | 29 | 1070102 | 1071224 |
| 2019 | 26 | 1080102 | 1081230 |
| 2020 | 25 | 1090113 | 1091231 |
| 2021 | 21 | 1100111 | 1101230 |

- The date is a 7-digit ROC compact string `YYYMMDD` (1050108 = 2016-01-08). Rows are sorted ascending. Already saved: 2015 has 19 rows and 2022 has 20 rows.
- The fields are identical in all years, `stat` is `ok`, and every year had data. 
- `減資原因` values: 彌補虧損 (loss offset) and 現金減資 (cash reduction). Counts for 2016 to 2021: 15/12, 9/16, 17/12, 15/11, 20/5, 16/5.
- exDailyQ for 2025 (`startDate=2025/01/01&endDate=2025/12/31`): 1250 rows, first 114/01/02, last 114/12/31. `權/息` values are 除息 1123, 除權 70, 除權息 57. The 85 rows have a nonzero stock dividend per 1,000 shares, up to 350.
- No row in exDailyQ 2025 mentions a capital reduction, par-value change or share-exchange keyword (searched 減資, 面額, 分割, 換發, 彌補 across all fields: 0 hits). The `title`, `summary` and `notes` keys are empty. Capital reductions appear only in revivt, not in exDailyQ.
- `exDailyQ` includes ETFs (for example 00950B, with `9999.95` / `0.01` limits), so filter by the common-stock rule.

**Confidence.** High.

## S4 Common-stock rule (`^[1-9][0-9]{3}$` and name not ending in `-DR`), on 11 saved files (verified locally)

| date | rows | pass | fail |
|---|---|---|---|
| 20160601 | 720 | 718 | 2 |
| 20170601 | 741 | 738 | 3 |
| 20180601 | 772 | 754 | 18 |
| 20190603 | 845 | 771 | 74 |
| 20200601 | 881 | 773 | 108 |
| 20210601 | 900 | 785 | 115 |
| 20220601 | 905 | 797 | 108 |
| 20230601 | 907 | 808 | 99 |
| 20240603 | 919 | 819 | 100 |
| 20250602 | 966 | 852 | 114 |
| 20250529 | 966 | 852 | 114 |

(a) Non-common-stock codes that pass the rule: none found in these 11 dates. I searched names for ETF, ETN, 受益, 存託, 債, 基金, REIT, 特別, -DR, and for codes starting with 9. The only hits were false positives (新零售 and 9949/9950/9951/9960/9962, which are ordinary stocks such as 琉園, 萬國通). No 4-digit ETF or ETN code exists in the OTC file. TPEx stocks with `F-` or `-KY` names are 4-digit codes and pass (for example 6514 `F-芮特`, later `芮特-KY`). This is only an observation on 11 dates; a 4-digit special code on other dates is not excluded.
(b) Failing codes: 
  - Bond ETFs `NNNNNB` / `NNNNNC` (for example 00679B, 00687C) are most of the fail list from 2019 onward. 
  - Equity ETFs with 5 digits (00858, 00877, 00886, 00928, 00955) and 6-digit codes (006201, 009806, 009807).
  - 020xxx codes ending in `N` names are ETNs (020001, 020023, 020040).
  - Special/preferred shares of ordinary companies have a letter suffix: 4129A 聯合甲特, 8349A 恒耀甲特, 8916A 光隆甲特. All are `甲特` (Class A special shares), so they correctly fail.
  - 911613 `特藝` (2016-06-01 only) is a 6-digit code starting with 91, a Taiwan depositary receipt. It correctly fails. `-DR` suffix: no name in the 11 files ends in `-DR` and has a 4-digit code.
  - No ordinary common stock failed the rule in these files. Counter by pattern across all dates: 148 codes with letters, 23 with 6 digits, 8 with 5 digits (unique code/name pairs).
  
**Decision.** The rule needs no extra condition for TPEx on these 11 dates. A cheap safety is to also require that the code not start with `91`, or just rely on the 4-digit rule (which already excludes it). Add the letter-suffix special shares as a known exclusion class. Confidence medium: 11 dates, not every date.

## S8 Field lists

**exDailyQ** (21 fields, same in 2016 and 2025). Example row (2016): `105/01/07, 4157, F*太景, 31.60, 31.49, 0.11, 0.00000000, 0.11, 除權, 34.75, 28.35, 31.60, 31.60, 0.00000000, 0.00000000, 20000000, 27.50, 2000000, 2000000, 16000000, 22.96341673`.
Fields: 除權息日期 (ROC YYY/MM/DD), 代號, 名稱 (space padded), 除權息前收盤價, 除權息參考價, 權值, 息值, 權值+息值, 權/息, 漲停價, 跌停價, 開始交易基準價, 減除股利參考價, 現金股利, 每仟股無償配股, 現金增資股數, 現金增資認購價, 公開承銷股數, 員工認購股數, 原股東認購股數, 按持股比例仟股認購.
- Pre-event close = `除權息前收盤價`. Reference price = `除權息參考價`. Cash dividend = `現金股利`. Stock dividend per 1,000 shares = `每仟股無償配股`. Example 2025 row: 6712 長聖, stock 99.99999623 per 1,000, reference 158.64.
- Also `息值` and `權值` are the value of the dividend and the stock dividend, `開始交易基準價` is the rounded base price used for limits.
- All values are strings. Names have trailing spaces. The 2025 rows have prices as strings too.

**revivt** (11 fields, same 2015 to 2022). Fields: 恢復買賣日期 (7-digit ROC compact), 股票代號, 名稱, 最後交易日之收盤價格, 減資恢復買賣開始日參考價格, 漲停價格, 跌停價格, 開始交易基準價, 除權參考價, 減資原因, 詳細資料 (HTML table).
Example (2020): `1090113, 3073, 凱柏實業, 5.20, 9.76, 10.70, 8.79, 9.76, 0.00, 彌補虧損, <html>`.
- Capital-reduction halt close = `最後交易日之收盤價格`. Resumption reference price = `減資恢復買賣開始日參考價格`. 
- The HTML `詳細資料` holds 停止買賣日期 (halt date), 恢復買賣日期, 每壹仟股換發新股票 (new shares per 1,000 old, for example 792 for 4131), 每股退還股款 (cash refund per share), and cash-capital-increase details.
- 現金減資 rows have `除權參考價` 0.00 in the sample I looked at (3169 亞信, 2020). Not checked for all.

**Splits and par-value changes.** Neither exDailyQ nor revivt has a split or par-value field or text. Splits and par-value changes were not found in either feed in the years checked. Use the `halt` and the `詳細資料` data if needed. Unresolved: whether TPEx publishes par-value change events elsewhere (not probed).

## S9 Field-list eras of `afterTrading/otc`

(a) Verified-live, all `ok`, 15 fields, identical to the 20160601 list (`代號, 名稱, 收盤, 漲跌, 開盤, 最高, 最低, 成交股數, 成交金額(元), 成交筆數, 最後買價, 最後賣價, 發行股數, 次日漲停價, 次日跌停價`):
- 20150302: 685 rows; 20150901: 694 rows; 20151201: 700 rows.
- Both 20150302/0901/1201 were trading days. 20160601 has 720 rows (saved).

(b) Bisect between 20190603 (15 fields) and 20200601 (17): 
- 20191202: 15; 20200302: 15; 20200415: 15; 20200511: 17; 20200428: 15; 20200504: 17; 20200430: 17; 20200429: 15.
- **The first date with the 17-field layout is 20200430** (the day after 20200429, 15 fields). Boundary is exact; 8 requests. The new fields are `最後買量<br>(千股)` and `最後賣量<br>(千股)`.
- The layout depends on the trade date requested, so history is not re-served in the new layout. This is inferred from the old files still having 15 fields.

(c) Saved files: 20250109 has labels `(千股)`; 20250110 has `(張數)`. The first date with `(張數)` is 20250110, confirmed. Row counts 942 and 943. Note: the unit name changes from 千股 to 張數 on the same column position; the numeric values in the two eras still need a unit check (not done).

## Facts that contradict the notes in the prompt
1. 20250530 was a holiday (0 rows), so the example pair 20250529/20250530 does not work. Use 20250529/20250602.
2. The prompt says `revivt` for 2016 to 2021 would be checked by "first and last dates": dates are 7-digit ROC strings (`1050108`), not Gregorian.
3. The prompt says the otc newer layout has 17 fields "labelled `(千股)`" for the last bid and ask volume: correct, but the boundary in 2025 relabels the same fields to `(張數)`, so there are three eras (15, 17 with 千股, 17 with 張數).
4. The `次日漲停價` for bond ETFs is `9999.95` (and down `0.01`) rather than 1.10 x close, so the "about 1.10 x close" statement is false for those rows and for events with an adjusted reference price.
5. exDailyQ also lists ETFs (for example 00950B), so it is not a stocks-only feed.
6. The prompt's wrong-path rule (HTTP 302 to /errors) was not triggered; no request failed.
