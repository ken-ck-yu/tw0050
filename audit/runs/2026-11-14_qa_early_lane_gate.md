# Run report: qa / early-lane gate (M1 + monthly_revenue, offline)

- **Task and agent name:** qa-goldfish, early-lane gate check (M1 datasets and monthly_revenue). Report saved by the lead because the QA agent's shell was blocked before it could write it (see problems).
- **Files created or changed:** this report only. No data modified, no ingestion code, no network, no token, `.env` not read.
- **Result: NOT PASSED.** Data was still being written during the run (state files updated 16:18 to 20:41 UTC on 2026-11-14), so counts may shift. Checks 15b and 16 are unverified.
- **Method:** read-only DuckDB queries over `data/clean/*/v1/*/*.parquet` using `.venv/bin/python -I`.
- **Data seen:** prices_raw 5,163,522 rows (2015-03-02 to 2025-12-22); universe_membership 109 month-ends (2015-06-30 to 2024-06-28); market_cap ends 2024-06-28; monthly_revenue 48,132 rows (2013-12 to 2024-05, 400 stocks); collection_set 412 names.

## Results

| # | Check | Result | Evidence and owner |
|---|---|---|---|
| 1 | Keys unique: trading_calendar, prices_raw, shares_issued, market_cap, universe_membership, delistings, monthly_revenue, collection_set | PASS | 0 duplicate keys in each |
| 2 | Keys unique: stock_info | FAIL | 616 (stock_id, event_date) keys have two rows with different `industry_category` in the same fetch (e.g. 1471). Dictionary says a duplicate key stops the run. Owner: agent A |
| 3 | Keys unique: status_events | NOTE | 151 changed_trading keys repeat; each is a revision with a longer `end_date`. Looks intentional. Owner A to confirm |
| 4 | `available_at` not before `event_date` (Asia/Taipei) | PASS | 0 violations, 0 nulls in prices_raw, shares_issued, market_cap, status_events, monthly_revenue. universe_membership never before month_end |
| 5 | monthly_revenue `available_at` = 10th of next month, rolled to next trading day, 18:00 Taipei | PASS | 0 mismatches in 48,132 rows |
| 6 | monthly_revenue fallback share | REPORTED | 100%: all rows have null `create_time`, so every row uses the statutory fallback |
| 7 | universe_membership: 200 ranked per month-end, 2330 present | PASS within its range | 200 ranked non-benchmark members in all 109 months; 2330 rank 1 every month; 0050 benchmark row each month; no non-common codes; no member covered by a status event |
| 8 | universe_membership covers dev window to 2025-12-31 | FAIL | Ends 2024-06-28; 18 month-ends (2024-07 to 2025-12) missing. market_cap also ends 2024-06-28. Reflects the superseded dev window. Owner: agent A |
| 9 | prices_raw covers dev window | FAIL (partial) | Ends 2025-12-22; calendar has 6 more trading days to 2025-12-31. Owner: agent A |
| 10 | Price coverage >= 99% of trading days per member-month | FAIL | 38 of 21,909 member-months below 99% (min 53%). e.g. 3682 Jan 2020 (8/15), 6121 Sep 2017 (12/22), 5371 Aug 2016 (13/23). Clusters: Oct 2018, Oct 2022, Sep 2022. Gaps are consecutive runs inside the month. Source gap or halt cannot be told offline. Owner: agent A |
| 11 | Trading calendar | PASS | Covers 2015-06-01 to 2026-12-31 plus 65 stub days from 2015-03-02; every price day is a trading day; every trading day to 2025-12-22 has prices; 8 Saturday make-up days present. Forward-dated part not verifiable offline |
| 12 | Delisted names present | PASS | 690 delistings; 27 in the collection set, all with prices through last trade |
| 13 | Delisted names with no prices | NOTE | 2384 (delisted 2015-07-07) and 3126 (delisted 2016-04-06) have no price rows. Not members, gate unaffected. Owner A to explain |
| 14 | Collection set completeness | PASS | 412 names, all in prices_raw, shares_issued, market_cap; equals distinct universe stocks |
| 15 | monthly_revenue completeness vs collection_set | PARTIAL FAIL | 400 of 411 non-benchmark names have rows; the 11 without were delisted before 2019. Revenue stops at 2024-05 for 388 stocks. 4 stocks have 86 interior missing months in total (not itemised). Owner: agent C |
| 16 | monthly_revenue unit | NOT VERIFIED | Dictionary says NT$ (inferred, spike S5 not run); plan says NT$ thousands. 415 rows <= 0. Owner: C or lead |
| 17 | market_cap = close x shares_issued | PASS | 0 rows differ by more than 1 NTD; one non-common code row (020021, 2020-12-02) has 0 |

## Checks that could not be run
- Plan section 7 check 3 (adjusted prices): needs adjusted prices and corporate actions, outside M1.
- Plan section 7 check 4 (cross-source against TWSE/TPEx): needs network.
- Plan section 7 check 5 (price limits): no previous-close or ex-date table in M1.
- status_events completeness against official sources: needs network.
- Whether the price gaps in check 10 are real halts: needs network.
- The live gates in the design.
- Volume units were checked only by column name (`volume_shares`).

## Failures by owner
- agent A: checks 2, 8, 9, 10.
- agent C: check 15 (and 16 with the lead).
- agent A to confirm: checks 3, 13.

## Problems hit
- The QA agent's Bash tool began refusing every command partway through. The message said the session was isolated in the worktree `.claude/worktrees/drafts-and-gitignore`, but its cwd resolved to `/home/ken/tw0050`. It made no attempt to work around the block and has no file-write tool, so the report was not written by the agent.

## What in the instructions was missing, ambiguous or wrong
1. No expected end date per table was given. QA used the amended dev window to 2025-12-31. If the gate means the earlier 2024-06-30 range, checks 8, 9 and 15 pass on end date.
2. The 99% coverage rule is silent on halts, new listings and partial first months. QA used all calendar trading days in the member's month up to month-end.
3. Not stated whether revision rows are allowed in status_events and stock_info.
4. The plan says revenue is in NT$ thousands; the data dictionary says NT$.
5. The plan's `revenue_month_num` differs from the schema's `revenue_month`.
6. No `CURRENT` pointer files were found, so QA read all `v1` partitions.
7. No delisted names to check were named; QA used 2475 and the delistings table.
8. Worktree isolation resolved to the shared checkout and blocked every command.

## What I would do differently next time
Ask up front for the expected end date per table and the halt handling, and get a list of documented gaps.
