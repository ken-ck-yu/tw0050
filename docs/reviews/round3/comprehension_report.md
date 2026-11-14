## Comprehension review of /home/ken/tw0050/docs/designs/data_platform.md, lines 1-386 (round 3)

Reviewer: `egm-comprehension` (fresh context, document read alone). Status: completed. Severity: 2 Blocker, 10 Major, 13 Nit.

Reviewer's note: the relative links were not followed. It read only the target and its persona file, and did not check that `docs/DECISIONS.md` and `DATA_COLLECTION_PLAN.md` exist.

### What this proposes
The document proposes a local data layer for a research project that tests whether a machine-learning strategy holding Taiwan stocks for 2 to 10 days beats costs. Phase 1 only collects and validates data. Sources are the official TWSE and TPEx daily files and the FinMind API (free tier). The official files build a survivorship-free universe of 200 ranked stocks per month-end from 2015-06-30. FinMind supplies 14 per-stock datasets for stocks that were ever in that universe.

Raw responses are cached unparsed. Clean data is written append-only to Parquet and queried through DuckDB views. Every joinable row carries `available_at`, a conservative guess of when the value became known. Adjusted prices are computed on demand "as of" a time from raw prices plus an event table. Splits are entered by hand, because no official feed carries them.

Six agents (A to F) build it under the Lead. A to E ingest data and F does QA. The work runs in phases 0 to 3. Eight acceptance checks decide pass or fail, and any failure stops the run.

### How the existing system works, per this document
The document describes a repository where `DATA_COLLECTION_PLAN.md` and several `docs/` files already exist. These include `DECISIONS.md`, `OFFICIAL_SOURCES.md` and `FINMIND_DATASETS.md`. There are also research and spike notes and `.claude/agents/ingest-worker.md` and `qa-goldfish.md` agent definitions. There is a hook mechanism that records agent type. No data pipeline code exists yet; "Nothing below is built until the author approves" (line 344).

The sources behave as follows:
- Undocumented TWSE and TPEx endpoints were probed in spikes S1 to S9.
- FinMind changed history in 2026.
- Several official lists keep only a latest snapshot.

The reviewer could not say what "existing system" means beyond this research and agent scaffolding. The document does not state it.

### Findings

**Blocker**

1. **Lines 13, 28, 45-47, 183-209, 227: the delivery of `event_date`/`available_at` for derived and reference tables does not connect.**
   - The Goals (line 45) say every joinable clean table has `event_date` and `available_at`, with reference tables exempt. `universe_membership` and `collection_set` are said to use "the latest `available_at` of their inputs" (line 227).
   - `collection_set` has no date column in its schema (line 207). Line 209 says tables whose key is not `event_date` store `event_date` as an equal column, and names only `revenue_month` and `month_end`.
   - `collection_set`'s key is `first_month_end`, which is not named there. `market_cap` inherits from `prices_raw` and `shares_issued`, which have different timings (18:00 versus 18:00, but that is not stated).
   - A fresh reader cannot tell what `available_at` or `event_date` is for `collection_set`, or whether it is joinable or reference.
   - Rewrite so that every table in the schema list is classified as joinable or reference, with its `event_date` source.

2. **Lines 69, 153, 162, 177, 179: "collection set" is circular and its size is unexplained.**
   - The collection set is "every stock that was ever a universe member" (line 28). The universe uses `market_cap`, which needs shares issued from the official pass.
   - Line 177 says "about 450 collection-set stocks", with no basis given. A reader cannot check the 6,300-request budget, because 14 x 450 = 6,300 rests on an unexplained 450.
   - The ordering is explained only in the critical-path sentence at line 179. State the ordering and the 450 estimate where the term is defined.
   - Separately, check 1 pulls `TaiwanStockPrice` "over the whole collection set". Whether that pull is one of the 14 datasets in the 6,300 count is unclear. Line 162 lists it among the 14, so it is probably included. Say so.

**Major**

3. **Line 4 and elsewhere: the document is unfinished in its own words.**
   - Status says "Not yet re-reviewed or approved". The Detailed Implementation Plan says "Nothing below is built until the author approves the reviewed design" (line 344).
   - Several items are explicitly open: S10, S5, S6, the 0050 reference price, `backup_dir`. Many details (`restatement_class` membership, "source columns" tables, row-count caps, config values) are deferred to Phase 0 specs that do not yet exist.
   - A reader who is asked to approve cannot see what is decided and what is deferred in one place. A short "deferred to specs" list would fix that.

4. **Lines 11, 13, 17, 21-29: heavy reliance on external documents for basic meaning.**
   - Endpoint names (`MI_INDEX`, `MI_QFIIS`, `TWT84U`, `TWT49U`, `TWTAUU`, `TWTAWU`, `exDailyQ`, `revivt`, `chtm`, `otc`, `STOCK_DAY`, `tradingStock`, `punish`, `notice`, `disposal`, `attention`, `deListed`, `warning`, `sprc`, `t187ap05_L` and the other `t187ap` names, `BWIBBU_d`, `TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`) appear without any inline gloss. Line 22 points to `docs/OFFICIAL_SOURCES.md` for them. Plan section numbers are referenced as the source of rules.
   - Add a one-line purpose for each endpoint in the Source policy table, or a short glossary. The table is the natural place, since each row is where the name is first used.

5. **Lines 28, 29: the terms are defined but only partly.** "P0, P1, P2" are the plan's priority tiers (plan section 3), and what they contain is not given. The Goals say "No paid FinMind tier is known to be needed for the P0 to P2 datasets here", so the reader needs to know which datasets those are. "Call auction" is left to general knowledge, which is acceptable.

6. **Lines 69, 70, 152-153: undefined internal data names.** `STOCK_DAY` and `tradingStock` are named as the independent last-trade sources in check 2 and decision D6. They are not explained. Line 22 does not list them among the endpoints explained elsewhere. The reader cannot tell which host each belongs to.

7. **Lines 71, 87, 236: adjusted-price semantics are hard to follow.** The adjustment formula is given (line 236), with a worked example. But it does not say which direction factors apply for a stock split such as 0050's 4-for-1. `reference_price / prev_close` is not obviously the ratio for a split. Entries carry a "ratio" in the YAML, and how it maps to `prev_close` and `reference_price` columns is not stated. The `corporate_actions` schema has no `ratio` column. "Two actions on one date multiply" is stated. What `halt_close` is for a split, and whether a split uses `halt_close` or `prev_close`, is not. State the mapping from the YAML ratio to the table columns.

8. **Lines 213, 217, 224: the `available_at` rule table mixes timings that are said to be "four" but more appear.** Line 213 says "The table uses four timings". The table shows trading date 18:00; next trading day 08:30; the 10th of the month 18:00; statutory deadline then 08:30; announcement date and time; next Taiwan calendar day 08:30 for US prices; `first_seen_at`; and the latest of inputs. That is more than four, so the count is wrong or the grouping is undefined. Line 217 says "Design assumption, tested in S10". If S10 fails, what changes is not said.

9. **Lines 220, 74: the monthly revenue and financials rules overstate certainty.** Check 6 says monthly revenue `available_at` is "never earlier than the 10th of the following month at 18:00". Line 219 sets this as the rule itself, so the check can never fail. A check that restates its own rule tests nothing, and the reader will wonder what it detects. Say what it guards against (a regression in code). The word "statutory" is used for a Taiwanese deadline rule that has no cited source here.

10. **Lines 100, 250-251, 295: the backup story is contradictory.** Line 250 says "after each phase gate `data/raw/` is copied to a second location", and lines 51 and 351 say `backup_dir` may stay unset and is "not part of any gate". The risk table marks loss of the raw cache "Medium until `backup_dir` is set" with 18 or more hours to refetch, yet the snapshot history is stated to be unrecoverable. A reader cannot tell whether the design relies on a backup that does not exist. State plainly what happens if `backup_dir` is never set.

11. **Lines 346-351: author prerequisites mix design and instructions.** Line 348 explains a hook approach in dense prose. "The audit hook already records it" refers to a hook that is not described elsewhere. `audit/events.jsonl` first appears at line 338 and is not explained. Line 349 says `ingest-worker.md` "tells each worker to write a section of `docs/DATA_DICTIONARY.md`". The reader has to open that file to know what the change is. These are prerequisites the author must do. They need a numbered, checkable form with the exact change.

12. **Lines 285, 359-363: the dependency order has inconsistent ownership of the first live gate.** Phase 1 is "Agent A", yet the live gate is "owner Lead". "A runs S5's counterpart S6" (line 361) is a confusing phrase, since S5 and S6 are unrelated (revenue unit versus `TaiwanStockInfo.date` meaning). Rewrite as "A runs S6". Phase 1 says the snapshot collector is built first. The dependency order (line 285) says A runs "the all-stock official pass and the universe" and does not mention snapshots.

**Nit**

13. **Lines 13, 49:** "first-reported view" (line 49) is used before the views are introduced. The view is named `as_first_seen` at line 138 and later. Use one name.

14. **Line 23:** the decision numbers D1 to D9 match the Alternatives section. No action needed.

15. **Line 30:** "Lot: 1,000 shares" is in the glossary, but the `(千股)` and `(張數)` labels in lines 88 and 166 are Chinese column labels that a non-Chinese reader cannot read. Add the gloss "thousand shares" and "lots".

16. **Lines 83, 155:** the "9999.95/0.01 no-limit sentinel (bond ETFs)" is explained, but the "otc next-day limit columns" are named without saying what the file name or columns are. Minor, since `OFFICIAL_SOURCES.md` covers it.

17. **Line 179:** "about 18 to 19 hours" critical path versus 8 + 10.5 = 18.5 is fine, but 11.8 h for the three TWSE endpoints is not 8 h. The "about 8 hours" for the universe pass is derived but the arithmetic (`MI_INDEX` plus `MI_QFIIS` plus TPEx `otc`) is not shown. TPEx `otc` is about 4 h, TWSE two endpoints about 7.9 h, so 8 h holds only when the hosts run concurrently. Add one sentence.

18. **Line 174:** the budget header says "from 2015-03-02 to 2026-11" yet the Goals say data starts 2015-06-01 (line 13). Line 257 explains that earlier prices are for the 60-day window. Mention that in the Overview.

19. **Lines 5 and 7:** date and status are fine. No findings.

20. **Line 116:** D9 says "About 12 latest-only sources". The Source policy table lists TWT85U, TWT96U, BFI84U, TWTB4U, t187ap04_L, t187ap09_L, t187ap12_L, t187ap24 to 27 (4) = 11, plus `warning` and `sprc` = 13. Give the number.

21. **Lines 195-197:** `monthly_revenue`, `financials` and `dividend_announcements` key on `stock_id` with `revenue_month`, `event_date` and so on. Consistent. No action.

22. **Line 241:** "TWSE writes `OK` and TPEx writes `ok`" is unexplained in context. Add "in the `stat` field".

23. **Lines 163, 201, 224:** `USStockPrice` is listed with `^VIX`, but the `us_prices` table is keyed on `ticker`. Which tickers are collected is not stated here (deferred to the specs).

24. **Line 244:** "The lock needs a Linux filesystem (not `/mnt/c`)" assumes the reader knows the project runs under WSL2. WSL2 is mentioned only at line 332. State the runtime environment in the Overview.

25. **Line 386:** "Drafted with EGM" is not defined. It is a footer, so low priority.
