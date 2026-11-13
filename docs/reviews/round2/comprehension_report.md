## Comprehension review: /home/ken/tw0050/docs/designs/data_platform.md, lines 1-388 (round 2)

Reviewer: `egm-comprehension` (fresh context, document read alone). Status: completed. Severity: 0 Blocker, 16 Major, 17 Nit. All five relative links (lines 19-22) were confirmed to exist. The reviewer did not read their contents.

## What this proposes
The document proposes a local data layer for a research project. The project asks whether an ML strategy that holds Taiwan stocks for 2-10 trading days earns an edge after costs. Phase 1 only collects and validates data. It pulls prices, corporate actions, fundamentals, flows and macro series from 2015-06-01. The sources are the official TWSE/TPEx daily files and FinMind's free tier. The data is stored as append-only Parquet files and queried through DuckDB views. Every row carries `event_date` and `available_at`, so later research can join on "when it could be known". The universe (200 stocks per month-end) is built from the official all-stock files. Adjusted prices are computed as of a time from raw prices plus an events table, not stored. Work is split across a Lead session, five ingest agents (A-E) and a QA agent (F), with gated phases and acceptance checks.

## How the existing system works, per this document
There is no existing code. The repo has a plan file and research notes, and nothing is built (line 324). The data sources work as follows. TWSE and TPEx publish per-date all-stock files and some latest-only snapshots, and these have undocumented endpoints and format "eras". FinMind offers per-stock datasets with a 600-requests-per-hour limit. FinMind lacks adjusted prices, market cap, financial-filing dates and some delisted-stock rows. The `.claude/` agent config today gives agent F no write tools (line 328).

## Findings

1. **Major.** Lines 62-73 (Acceptance checks), 17-27 (terms). The checks are called "agent F" checks. Phase 3 and the Modules table say F is `qa-goldfish`, and the checks are the plan's "section 7" checks. The reader cannot see how the 8 checks relate to the Goals, and the Goals repeat them in a slightly different form. For example, the goal says "2330 is always among them", while check 8 adds turnover bounds of 2% to 40%. A reader cannot tell which list is authoritative.

2. **Major.** Line 13 and "Common table columns" (172). `available_at` is called "when a value could first have been known to a trader". The Goals (42) say that no row has `available_at` earlier than `event_date`. Line 212 defines it as the next Taiwan calendar day after the US trading date. The `available_at` for `financials` is the statutory deadline, which can be after the true filing. The "first known" definition therefore does not match the rules. The rules are conservative upper bounds, not first-known times. Say so explicitly.

3. **Major.** Lines 100-109 and 289-291 (Decision 1). The document is internally confusing about why option B was chosen. Line 102 says "The original request-count reason did not hold". Lines 289-290 say that FinMind's 7.5 hours was "not derived" and that request counts are "comparable". Line 289 also quotes "about 2,000 or more requests" for the FinMind universe pass. The reader never sees that estimate derived or compared with the 8,529 + 5,760 official requests. Request cost is therefore not shown to be a non-factor.

4. **Major.** Lines 157-168 (Request budget). The arithmetic is not shown and some terms are ambiguous.
   - "Trading days ... about 2,843" is given without a derivation.
   - 8,529 is 3 x 2,843, which the reader must work out.
   - TPEx "about 5,760" is not 2 x 2,843 = 5,686.
   - At 5 s spacing, 8,529 requests take 11.9 h, which is fine. But 5,760 x 5 s = 8.0 h, so the line "hosts run concurrently ... about 12 hours" is correct only if TWSE and TPEx run at the same time.
   - "universe pass ... about 8 hours" is not derived. `MI_INDEX`, `MI_QFIIS` and `otc` would be 2 x 2,843 TWSE requests x 5 s = 7.9 h, so 8 h is plausible but not shown.
   - FinMind "14 datasets x about 450" = 6,300 is fine, but where "about 450" comes from is not stated. It is only the collection set, which is not yet built.
   - The 17,000 response count in Footprint (320) is also not derived. 2,843 x 5 is about 14,200 plus FinMind 6,300 is about 20,500, so 17,000 does not obviously match.

5. **Major.** Lines 79-84 (spikes S1-S6). Several spikes assume knowledge of the research that this document does not give.
   - S1: "915 rows against 951 `MI_INDEX` rows" is not explained. The reader does not know whether the gap means missing shares-issued data or only different universes.
   - S2: "limit prices on a row date apply to that date or the next trading day" is unexplained.
   - S3: "maximum date range per TWSE call" is unexplained.
   - S6 refers to the delisting row counts 690 and 726 without saying what they count.
   - The Phase 0 gate (337) requires all six spikes to be done, but the Open Questions line 77 says they come "before any ingest module is built". Phase 0 is Lead-only and builds no ingest module, so the order is consistent. The spike work itself is not scheduled, though: no phase lists who runs the spikes or how.

6. **Major.** Lines 199-218 (`available_at` rules). The rules conflict or are underspecified in places.
   - "Trading date 18:00" for `prices_raw` (205) is a "design assumption". The Decisions table (104) says the rule for date-only sources is "next trading day 08:30". The reader cannot tell which datasets are date-only and which use 18:00. TWSE/TPEx daily files are date-only too, yet use a different rule.
   - `monthly_revenue` (207): "10th of the following month at 18:00". Check 6 (71) says "`available_at` is after the first day of the following month". These are two different tests and the second is much weaker. This is unexplained.
   - `financials` (208) gives the Q3 date as 14 Nov and the annual deadline as 31 Mar, but not what happens for annual statements that are due 31 Mar for the prior year or how Q4 is distinguished from annual. Also, "then next trading day 08:30" is ambiguous: does it mean the next trading day after the deadline, or after the deadline if the deadline is a trading day?
   - `us_prices` (212): "next Taiwan calendar day after the US trading date at 08:30". The "Daylight saving is not needed" claim (218) is asserted rather than shown. The rule uses calendar days, so a Friday US date gives Saturday 08:30. The reader cannot tell whether Saturday counts as a "calendar day" for joins.
   - `market_cap`, `universe_membership`, `collection_set` use "the latest `available_at` of their inputs" (214). `universe_membership` is a monthly table whose `event_date` is `month_end`. Whether its `available_at` is the month-end close at 18:00 or later is not stated. The reader cannot work it out.

7. **Major.** Lines 220-222 (Adjusted prices). The worked example is confusing. It says "close 100 on day 1 ... adjusted close on day 1 as of any time after day 2 08:30 is 95". But per the rule, `corporate_actions` has `available_at` = next trading day 08:30 after the ex-date, so day 2's ex-date gives day 3 08:30. The example says "after day 2 08:30", which contradicts line 210. The unit test (373) repeats "as of day 2 08:30", so the discrepancy is in both places. The reader cannot tell whether the example is wrong or the rule is.

8. **Major.** Lines 222 and 348. "capital reduction `resumption_reference_price / halt_close`". The `corporate_actions` schema (181) has `prev_close` and `reference_price`, but no `halt_close` or `resumption_reference_price` column. The reader cannot tell which columns hold these values.

9. **Major.** Lines 244-249 (Universe). The rule is not fully self-contained.
   - Step 3 says to exclude stocks "flagged in the TPEx changed-trading report". The TWSE equivalent is not mentioned, but `status_events` has `changed_trading` for both. Is TWSE changed trading excluded?
   - Step 4: "60-trading-day median turnover ... over observed trading days, with at least 40 observed days". The window start (2015-03-02) and "turnover window starts three months before" (159) are unclear. 2015-03-02 is exactly three months before 2015-06-01 but 60 trading days before 2015-06-30 is about April, so March is more than needed.
   - Step 5 ranks by market cap and the Goals require "exactly 200 ranked members ... unless fewer pass the floor". The table `universe_membership` has `rank` and `is_watchlist`. How watchlist names that already rank in the top 200 are flagged, and whether they get a rank, is not stated.
   - Check 8 and the Goals disagree slightly: Goals say a shortfall is "reported", check 8 says "exactly 200 ... shortfall months reported". That is consistent only if shortfall months are exempt, which should be said.

10. **Major.** Line 245. "Foreign primary listings (`F-` or `KY` names) are common stocks." `F-` and `KY` are not defined. A naive reader does not know these are naming conventions for foreign companies listed in Taiwan.

11. **Major.** Lines 224-230 (Rate limiting). Some terms are not defined and some rules conflict.
    - `drift` includes "no rows on a trading day", but `valid_empty` requires "the date is not a trading day in the calendar". If the calendar itself is wrong or pending, the reader cannot tell which class applies.
    - "429" is listed as `transient`, but line 226 says "any 4xx stops the run" for FinMind. These conflict for a FinMind 429.
    - Line 274 says "no retries on `drift`" but the circuit breaker uses "3 consecutive `drift` responses". Whether the client sends three requests or counts three different dates is unclear.
    - "half-opens after 15 minutes with one probe" uses breaker vocabulary that is assumed rather than defined (this is general engineering, so a Nit-level concern).

12. **Major.** Lines 232-238 (Raw cache, state, writes).
    - "Raw: ... Parquet shards of up to 500 responses or 64 MB". How many shards fit the 2.5 GB estimate is unclear, but the main gap is that it says "each response a row" while Data flow (126) says `shard-*.parquet`. Fine.
    - "A parser fix writes a new version directory `v<N+1>` from raw, and a pointer file switches to it". The pointer file's location and format, and how DuckDB views pick up the pointer, are not described.
    - The "first-reported row per primary key (earliest `fetched_at`)" is defined, but `fetched_at` for data re-fetched in 2026 is always 2026, which the document admits (218). The reader is left unsure why "first-reported" is useful for backfilled history. The document says the dictionary notes this, but the dictionary is not written yet.
    - Snapshot job (238): "Sources with a date parameter catch up on the next run". The tables `TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap04_L` etc. are all undefined. The reader cannot tell what they contain or why they are needed. Lines 90 and 238 do not agree on the set: line 90 lists `TWT85U`, `TWT96U` and the holiday schedule as collected daily, and line 238 lists many more and does not mention the holiday schedule.

13. **Major.** Lines 174-197 (Table schemas).
    - `status_events` primary key uses `announce_date`, `start_date` but the common columns require `event_date`. Which of them is `event_date`? Line 197 only explains `monthly_revenue` and `universe_membership`.
    - `dividend_announcements`, `status_events`, `corporate_actions` etc. use various dates but the `event_date` mapping is not given.
    - `delistings, trading_calendar` row has "`stock_id`; `is_trading`" and the key "`stock_id`; `event_date`" which uses semicolons to separate two tables' columns. It is easy to misread: `delistings` has only `stock_id` (and no date column) and its primary key is shown as `stock_id` or `event_date`.
    - `fx, rates, futures` "series id ... values" is deliberately vague (197 admits it), but the key is therefore unknown.
    - `shareholding` etc. use "per source columns" while the `available_at` table treats them as defined.
    - `market_cap` has no `market` column although `prices_raw` does. Line 197 explains that a code is on one market on any date, which covers this.

14. **Major.** Lines 326-331 and 357-359. Prerequisite and command gaps.
    - The `qa-goldfish` agent file, `.claude/settings.json` and the "global `*.parquet` and `*.csv` rules" in `.gitignore` are referenced as existing facts. A reader cannot confirm the "global" rule applies.
    - Line 328 says F gets `Write` and `Edit` "limited by instruction", but line 329 relies on deny rules for the other agents. Whether F's limit is enforced or advisory is not clear.
    - The CLI: `fetch` takes `--dataset NAME`, but valid dataset names are not listed. `snapshot` is a command, yet the Modules table puts `cli.py` under the Lead while `snapshots.py` is Agent A's. How the Lead's CLI calls into modules that are not yet built, and who wires each new dataset in, is not stated.
    - Exit code 4 is "schema drift", and the exit code for a circuit-breaker stop on a probe failure is not specified (presumably 3 or 4).

15. **Major.** Lines 345-349 (Phase 2 gate). "A one-month, five-stock run (month 2020-06, stocks 2330, 2317, 2454, 6488 and 2475)". 2475 is described on line 67 as a delisted stock. Check 2's delisting is not stated to fall in or near 2020-06, so a run for 2020-06 may not exercise delisting handling. The reader cannot tell what 2475 tests there.

16. **Major.** Lines 351-355 (Phase 3). "the improve loop" and "At most three rounds, logged in `docs/ITERATION_LOG.md`" are not defined anywhere in the document. The reader does not know what a round involves, who fixes failures ("tagged by owner" is mentioned) or how it relates to the plan. Also, F "fetches cross-check data ... through the Lead's clients and a `qa` cache namespace", but the Dependency order (268) says F "runs last" and that F is "read-only on data" (137). Fetching writes to the cache, so this is contradictory, or at least the `qa` namespace should be called out as the exception.

17. **Nit.** Lines 25, 24. "`ingest-worker` agents" and "`qa-goldfish` agent" are Claude Code subagent types defined in files not linked from here. A link to the agent definitions would help.

18. **Nit.** Line 26. "ROC dates" is defined as "the Republic of China calendar", with one example, but the conversion rule (year + 1911) is not stated. The example is enough to derive it.

19. **Nit.** Line 38. "TWSE disposition and attention lists do have history back to 2015, and TPEx's go back to 2002 and 2003". It is unclear which list goes with which year. "Disposition" and "attention" are not defined (see also line 246, line 70). A short gloss would help.

20. **Nit.** Lines 59, 88. "full-delivery" (TWSE full-delivery stock list) is not defined. Neither is "changed trading" (`chtm`). Both are Taiwan-specific trading restrictions.

21. **Nit.** Line 70. "up/down sign" and "HTML sign snippet" (367) imply TWSE rows encode direction in HTML. This is explained only by the test case on line 367. A sentence in the source-policy section would help.

22. **Nit.** Line 111. "Decisions marked Lead are open to the author's override." The Basis column's reasons are terse, such as "The original request-count reason did not hold", which is explained only in Decision 1.

23. **Nit.** Lines 146, 152-153. Several source datasets are named with no description (`BWIBBU_d`, `t187ap05_L`, `t187ap06_L_*`, `t187ap07_L_*`, `TWT49U`, `TWTAUU`, `exDailyQ`, `revivt`, `punish`, `notice`, `disposal`, `attention`, `sprc`, `warning`). A one-line pointer to `OFFICIAL_SOURCES.md` would fix this. The same applies to FinMind dataset names.

24. **Nit.** Lines 153, 146, 183. Benchmark index appears twice in the Source policy table. The first row's cross-check (FinMind price) does not apply to an index. `benchmark_index` has `TPEX_TR`, but the last row's primary source covers only TAIEX and Taiwan 50.

25. **Nit.** Line 155. "(千股)" and "(張數)" are Chinese labels that are not translated (thousand shares versus lots). One lot is 1,000 shares, which is not stated. Line 172 says "volume in shares (not lots)", so "lot" is also undefined.

26. **Nit.** Lines 172, 184. `create_time (as given)` is mentioned only here. Line 207 explains it is a load date and not used. Minor cross-reference.

27. **Nit.** Lines 94, 278. "about 12 hours of refetching" (94) versus "12 or more hours to refetch, snapshot history lost" (278). Slightly different. Minor.

28. **Nit.** Line 280. The Risks table says "Medium" likelihood for single-source shares issued but the mitigation names "carry-forward limit" with no value. The limit (10 trading days) is only in S1, line 79.

29. **Nit.** Lines 308-310 (Decision 5). "Rejected by Lead" appears at the end of a list that mixes chosen and rejected items, and the sentence does not say which of `requests`, `Retry`, FinMind package, `requests-cache` and `pandas` was chosen or rejected.

30. **Nit.** Line 318. `audit/events.jsonl` is mentioned with no definition, and no other part of the document says what writes it.

31. **Nit.** Line 335. `pip freeze` and `requirements.lock` are fine, but the list of dependencies that go into `pyproject.toml` is not given in one place.

32. **Nit.** Line 363. "tests/fixtures/** (saved responses ... each at most 300 KB)" versus the 150 KB daily file on line 20 is fine, but the 2.5 GB line (320) is not tied to this.

33. **Nit.** Line 388. "Drafted with EGM" is not defined in the document. It is only context for the author.

The reviewer's most serious items for a fresh reader are 7 (the worked example and its test contradict the `available_at` rule), 6 (conflicting `available_at` rules), 8 (missing columns for the capital-reduction factor), 13 (no `event_date` mapping for several tables) and 16 (the improve loop is undefined and F is both read-only and fetching). It found no section it could not paraphrase, so there are no Blockers.
