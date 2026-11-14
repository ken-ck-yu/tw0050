# Run report: QA, early-lane gate (M1 tables + monthly_revenue), real data

Saved by the lead from the QA agent's hand-back (the agent has no file-write tool). Content is the agent's; nothing re-graded.

- **Task and agent:** QA reviewer. Graded the early-lane gate on `data/clean` by running and auditing `scripts/qa_gate_checks.py`, then digging into the flags.
- **Files changed:** none. Read-only, no network, no token, `.env` not read, no data modified. All commands ran; none were blocked.

## Result

**Gate: NOT PASSED**, for the same reasons as before plus one new one. After auditing the script, two of its three FAILs were script bugs (false positives). The real failures:
1. Price coverage: 44 member-months below 99% (owner: Agent A).
2. Revenue holes: stocks with no revenue or with gaps inside their membership window (owner: Agent C).

## Results table

| # | Check | Result | Evidence | Owner |
|---|---|---|---|---|
| 1 | Unique key shares_issued `(market, stock_id, event_date)` | PASS | 0 duplicates. The script's 25 duplicates are each one TWSE row plus one TPEx row | script bug (lead) |
| 2 | Unique key, other 7 tables | PASS | 0 duplicates each | none |
| 3 | `available_at` not before `event_date`, not null (5 tables) | PASS | 0 and 0; prices_raw `available_at` is 18:00 Taipei; `universe_membership.available_at > fetched_at` is 0 | none |
| 4 | market_cap = close x shares, same-market join | PASS | 0 rows differ by more than 1. The script's 9 rows come from a join without `market` | script bug (lead) |
| 5 | market_cap rows with no price row | PASS | 0 of 5,053,821 | none |
| 6 | Universe: 200 non-benchmark per month-end, 2330 present | PASS | 127 month-ends, min = max = 200 | none |
| 7 | Universe month_ends are last trading days | PASS | 0 off | none |
| 8 | Price coverage >= 99% per member-month | FAIL | 44 of 25,400 below | Agent A |
| 9 | Prices on non-trading days / trading days with no prices (to 2025-12-31) | PASS | 0 and 0 | none |
| 10 | Price sanity: high < low, close <= 0 | PASS | 0 and 0 (close null on 88,860 rows, not tested for expectedness) | none |
| 11 | Revenue unit | PASS | TSMC 2024-04 = 236,021,112,000 NT$ | none |
| 12 | Revenue completeness over the membership window | FAIL | 207 of 25,400 member-months have no revenue row available (within 3 months) at month-end; none at all for 11 stocks | Agent C |
| 13 | status_events end date | NOT FULLY PROVEN | see (e) | Agent A |
| 14 | status_events key and date sanity | PASS | 0 duplicate (stock, type, start, end, market) groups; 0 rows with end before start | none |

## Findings

**(a) shares_issued "25 duplicate keys".** The dictionary key is `market, stock_id, event_date` (`docs/data_dictionary/a_daily_official.md`); with `market` there are 0 duplicates. Each of the 25 pairs is one TWSE row and one TPEx row from different fetches. Values are identical in 15 pairs and conflicting in 10 (4912, 4739, 8462, 1795, 3092, 8476, 6472, 6446, 6589, plus one more). In all 25, prices_raw has the stock only on TPEx, so the TWSE share rows are orphans. market_cap uses the TPEx shares. Not a dictionary violation, but a consumer joining shares on `stock_id, event_date` without `market` silently picks the wrong share count. Recommend Agent A documents this and the lead fixes the script key.

**(b) market_cap vs close x shares, 9 rows.** These are 9 of the 25 dual-market pairs (the ones with conflicting counts). Cause is the script join without `market`; stored market_cap values are right.

**(c) 44 member-months below 99% coverage (no exemptions applied).** 33 stocks; lowest ratio 0.53 (3682, 2020-01: 8 of 15 days). In the cases examined (2317, 2327, 3682, 2603, 3481, 5371) the missing days form one contiguous block mid-month, with the first and last days of the month present. This looks like a stock-level halt, not a source outage; market-wide row counts on those days are normal (about 1,845 per day in 2018-10). Unverified without the network.
- Repeat stocks (months): 2327: 2016-08, 2017-08, 2022-10, 2025-08. 3481: 2022-10, 2023-08, 2024-08. 2492: 2016-09, 2017-09. 3105: 2015-08, 2016-09. 6271: 2020-11, 2022-12. 9945: 2018-10, 2023-09.
- One month each: 1717 2022-10; 2006 2021-12; 2201 2020-10; 2204 2019-10; 2317 2018-10; 2337 2017-08; 2352 2025-10; 2368 2022-09; 2371 2025-06; 2404 2018-12; 2409 2022-10; 2456 2018-10; 2458 2018-10; 2504 2020-10; 2603 2022-09; 2609 2017-05; 2915 2018-10; 3532 2018-09; 3576 2021-08; 3682 2020-01; 4763 2025-06; 4961 2023-09; 5371 2016-08; 6121 2017-09; 6415 2022-07; 6531 2021-10; 6548 2022-09; 6919 2025-07; 8150 2018-10.
- Clusters: 2018-10 (6 stocks: 8150, 2456, 9945, 2915, 2458, 2317); 2022-10 (4: 2409, 2327, 1717, 3481); 2022-09 (3: 2368, 2603, 6548); pairs in 2016-08, 2016-09, 2017-08, 2017-09, 2020-10, 2023-09, 2025-06; 18 further singletons. No member-month has zero price rows.

**(d) Revenue gaps.**
- 4749, 6526, 6515: missing months (4749: 2016-08 to 2021-07; 6526: 2017-07 to 2022-02; 6515: 2015-07 to 2019-07) are all before first listing and membership. No effect on the universe. Low severity.
- 8406, 6452, 5264: all three miss exactly 2019-01 to 2019-10, which falls inside their membership windows (8406 to 2019-03; 6452 to 2020-02; 5264 to 2020-12, 6 member-months from 2019-04 to 2019-11 lacking usable revenue). Probably a source hole. Owner: Agent C.

**(e) status_events ends 2025-12-30.** 2025-12-30 and 2025-12-31 are both trading days with prices. December 2025 has events on only 17 of 22 trading days, so no event on 12-31 is not anomalous. Cannot prove from Parquet that 2025-12-31 was fetched and returned empty. Ask Agent A for the done-marker. The calendar marks every weekday through 2026-12-31 as trading except some holidays; dates after 2026-11-14 are projections.

**(f) 11 collection-set stocks without revenue.** All 11 are in `delistings`: 1262, 1704, 2311, 2325, 2833, 2847, 3474, 3658, 3662, 4733, 6286. The lead's premise "delisted before 2019" is wrong for 1262 (delisted 2019-10-14) and 1704 (delisted 2019-01-30). More important: these were members in the early years (1704 for 42 months, 2311 and 2325 for 34, 1262 for 25), so revenue is absent while they were in the universe. This is survivorship in the revenue table: about 200 member-months, all delisted names. Owner: Agent C, plus a lead decision on whether to accept and document the limitation. 2475 on 2017-09-30 also lacks recent revenue. 3658 and 3662 have 0 `stock_info` rows.

## Audit of `scripts/qa_gate_checks.py`

- **Wrong:** shares_issued key omits `market`; market_cap join omits `market`; revenue gap check is not scoped to the membership window.
- **Weak:** universe check does not separate ranked rows from watchlist extras (rank null); coverage check does not distinguish suspensions from missing data; end-date checks are NOTEs only; the `available_at` check does not test the plan section 4 per-dataset rules (revenue `available_at` minus `event_date` runs 37 to 486 days; the 486-day maximum looks like late or backfilled rows, not tested against plan section 4).
- **Missing:** revenue coverage over member-months; conflicting values with differing `fetched_at` across all tables; key checks for status_events, collection_set and stock_info beyond the industry key; delisting completeness against prices; market cap absent when no share row; calendar versus status_events end of window.

## Checks I could not run

- Source verification of suspected halts (c) and whether 2025-12-31 was fetched (e): no network, state files not read.
- Plan section 4 per-dataset `available_at` rules beyond the 18:00 prices and the 37-day revenue minimum.

## What in my instructions was missing, ambiguous or wrong

- The premise in (f), "delisted before 2019", is wrong for 1262 and 1704.
- The brief called the shares_issued duplicates a possible dictionary-key violation, but the dictionary key includes `market`, which the script omitted. Both script FAILs trace to that one omission.
- `docs/DATA_DICTIONARY.md` does not exist; the dictionary is split across `docs/data_dictionary/*.md`.
- Plan section 7 and `acceptance_checks.md` were not re-read beyond what the dictionary needed; the thresholds (99% coverage, 200 members, unit check) came from the script and the brief.
- QA asks whether the 44 coverage months may be exempted for verified suspensions. None were exempted.
