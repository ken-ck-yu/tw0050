# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-321`, everything above `## Detailed Implementation Plan`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed (did not open the reading list; structural audit only, no fact-checking) |
| `egm-style` | completed |

**Severity totals after deduplication:** 0 Blocker, 28 Major, 25 Nit. Every reviewer reported no Blockers.

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

## Major

### Check 3 and the "independent source" goal are circular - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 45, 68, 149, 181, 222, 314
* **Discrepancy Description**: Goal line 45 says adjusted prices match "an independent source". Check 3 compares adjusted returns to returns implied by raw prices and the official reference price. That is the same `reference_price` stored in `corporate_actions` and used to build the factor, so the check tests only the arithmetic. An event missing from both sides passes. Yahoo `Adj Close` is excluded with an unsupported "not trusted" and has no source-policy row. FinMind `TaiwanStockDividendResult` is listed as a cross-check (line 149) but no check uses it. Line 314 repeats "doubles as the validation the plan asks for". Reference prices are rounded to tick size, which at prices of 50 to 100 is about 0.05 to 0.1% and close to the 0.1% tolerance.
* **Rationale & Recommendation**: Reword the goal and line 314 to say what check 3 detects. Add a completeness check: list every raw close-to-prior-close move beyond a threshold (for example 8%) with no limit-lock explanation and no event, and reconcile yearly event counts against `DividendResult`, `TWT49U`/`TWTAUU` and `exDailyQ`/`revivt`. Define a tick-aware tolerance. Cite a reason for distrusting Yahoo or drop it.

### Wall-clock and request-budget statements are inconsistent - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 94, 157-168, 246, 275, 278, 320
* **Discrepancy Description**: Line 168 says hosts run concurrently so wall-clock is about 12 h. The FinMind collection-set datasets start only after the universe exists. About 8 h of universe pass plus 10.5 h of FinMind is about 18.5 h on the critical path. Lines 94 and 278 repeat "12 hours" as the refetch cost, and line 94 omits that snapshot history cannot be refetched. The universe pass is said to need only `MI_INDEX`, `MI_QFIIS` and `otc`, but step 3 (line 246) needs `chtm` and `punish`. Retries, snapshot requests, the 500-sample FinMind cross-check and non-per-stock FinMind calls are not budgeted. TPEx "about 5,760" is not 2 x 2,843, "14 per-stock datasets" is never listed, and line 320's about 17,000 responses does not reconcile with about 14,300 in the table. No evidence shows the hosts tolerate 8 to 12 h at 5 s; probes were about 80 requests.
* **Rationale & Recommendation**: Restate budgets as a table with dependencies and the critical path. Make lines 94, 278 and 320 agree. Stage the first run (one year, then evaluate) before the full backfill. The reviewers re-checked 8,529 requests at 5 s (about 11.9 h) and 14 x 450 at 600/h (10.5 h) as sound in isolation.

### Author decisions and rejections attributed without a record - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 103-104, 291, 295
* **Discrepancy Description**: Line 104 (next trading day 08:30 for date-only sources), line 291 (Option C "Rejected by author") and line 295 (per-dataset time rules rejected by author) have no entry in `docs/DECISIONS.md`. That file records the free tier, token handling, option B, the snapshot job and the backup decision.
* **Rationale & Recommendation**: Record the three decisions with a date in `docs/DECISIONS.md` and link them. If Ken has not decided them, label them Lead proposals.

### `corporate_actions` omits splits and par-value changes, and event fields are untested - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 149, 181; plan section 3 P0
* **Discrepancy Description**: `action_type` has only `ex_dividend`, `ex_rights` and `capital_reduction`. Plan P0 says "Capital reductions, splits". The TPEx par-value change page is untested. The reviewer states from its own knowledge, not from the reading list, that 0050 had a 4-for-1 split in 2025, which would break adjusted benchmark-stock prices and be hidden by check 5's exception list. No research file shows field-level evidence for `TWT49U`, `TWTAUU` or `exDailyQ`, yet the schema assumes `prev_close`, `reference_price`, `cash_dividend` and `stock_dividend_per_1000`.
* **Rationale & Recommendation**: Add a split or par-value action type with a source, or document that none exists. Add a spike dumping the actual field lists of `TWT49U`, `TWTAUU`, `exDailyQ` and `revivt`. State whether ETFs are covered.

### `corporate_actions.available_at` lag creates artefacts and the worked example contradicts the rule - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 201, 211, 222
* **Discrepancy Description**: Line 201 defines "next trading day" as strictly after the source date, so an ex-date on day 2 gives `available_at` of day 3 08:30. The line 222 example says the adjusted close is 95 after day 2 08:30. Between the ex-date open and day 3 08:30 any as-of series shows a fake drop (-5% in the example). Ex-dates and reference prices are public before the ex-date open, so this is an artefact, not leakage. Dividends cluster in July to September.
* **Rationale & Recommendation**: Fix the example. Choose deliberately between ex-date 08:30, the evening before if published, or the current rule. If the current rule stays, record the artefact in the data dictionary and link `dividend_announcements` to the factor.

### First-reported rule makes known-bad source data permanent - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 106, 218, 237, 282
* **Discrepancy Description**: The first-reported view keeps the earliest `fetched_at`, which is the project's first fetch, not the source's first publication (line 218 admits this for pre-2026 history). `finmind_findings.md` documents 2026 in-place corrections (`TaiwanStockPrice` low-volume rows 2022-11 to 2023-03, TPEx margin short-sale columns swapped, ETF dividend duplicates, EPS). A refetch after correction writes a later row that the view discards, and the revisions view is not a join target. Revision rows carry the original `available_at`, which leaks if joined.
* **Rationale & Recommendation**: Choose a policy per dataset. Use the latest fetched value for exchange facts (prices, shares, margin) unless flagged. Add an errata or supersede flag. Require revision rows to have `available_at` of at least `fetched_at`.

### Snapshot job cannot test the `available_at` assumptions it is credited with - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 205, 238, 276, 296
* **Discrepancy Description**: Lines 205 and 276 say snapshot `first_seen_at` tests the 18:00 and 08:30 rules. The job is a manual once-a-day command at an arbitrary hour, and `first_seen_at` is only an upper bound on publication time. It cannot show a rule is too early, which is the leakage risk. Line 296's "measured through `first_seen_at`" is true only for snapshot sources, not for `punish`, `notice` and `disposal`.
* **Rationale & Recommendation**: Add a one-off timing spike polling `MI_INDEX`, `otc` and `MI_QFIIS` at fixed clock times (for example 15:00, 16:30, 18:00, 19:30) on a few trading days. State that the snapshot job is only a late bound.

### Response classifier mishandles range, empty-message and redirect responses, and status-code rules conflict - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 226-229, 274
* **Discrepancy Description**: `drift` includes "no rows on a trading day", but range endpoints (`TWT49U`, `TWTAUU`, `punish`, `notice`, `TWTAWU`, `revivt`, `disposal`, `exDailyQ`) can legitimately be empty. TWSE empty replies carry a non-`OK` `stat` message (`stat` and `total` keys only). TPEx `sprc` returns a message string, and wrong TPEx paths return HTTP 302 to `/errors`, which is not classified. Three false `drift` responses open the circuit breaker on a quiet window. Line 226 says "any 4xx stops the run" while line 228 treats 429 as `transient`, and FinMind 402 is also 4xx. The rule is per-host in one place and global in another. The 403 ban behaviour is documented by FinMind, not observed.
* **Rationale & Recommendation**: Define empty semantics per endpoint class (per-date, per-range, snapshot). Add the TWSE no-data message as `valid_empty` for ranges. Do not follow redirects and classify 302 as `drift`. State one rule per host and per status code.

### Evidence gap for 2015-03 to 2015-12 and the pre-2020 TPEx era - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 155, 159, 242; `OFFICIAL_SOURCES.md` lines 20, 29
* **Discrepancy Description**: The universe window starts 2015-03-02, but `MI_INDEX` and TPEx `otc` were sampled only for 2016 to 2025. TPEx `otc` before 2020 has fewer columns, and it is unverified that it carries shares issued or next-day limit prices. TPEx market cap for 2015-2019 depends on shares issued. Era boundaries are evidenced only for 2025-01-10 and one date per year, so the registry's date ranges are undefined.
* **Rationale & Recommendation**: Extend spike S3 to `MI_INDEX` and `otc` for 2015-03 to 2015-12, check the pre-2020 era for shares, limit columns and benchmark table, and bisect the era boundaries. Make this a gating item.

### TPEx next-day limit columns are not mapped in the schema - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 70, 80, 148, 178
* **Discrepancy Description**: TPEx `otc` carries next-day limit prices (`OFFICIAL_SOURCES.md` line 29) but `prices_raw` stores `limit_up` and `limit_down` on the row `event_date`. S2 asks only about `TWT84U`. A one-day shift in either source makes check 5 compare against the wrong day for part of the market.
* **Rationale & Recommendation**: State the shift rule per source in the schema, extend S2 to TPEx, and define check 5's join.

### Checks 1 and 2 are partly circular and there is no listing-status table - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 66-67, 109, 176-195
* **Discrepancy Description**: Check 1's denominator and check 2's last trading days both derive from the daily files being validated, so a truncated file or dropped suspended row is invisible. Line 109 derives listing status from daily files but no table or view holds it. Independent last-trade dates already exist in the research (2475 on 2019-05-10, 3474 on 2016-11-29, 3299 on 2018-11-21).
* **Rationale & Recommendation**: Add a `listing_status` view (first date, last date, market). Add cross-endpoint row-count reconciliation per date (`MI_INDEX`, `MI_QFIIS`, `TWT84U`). Run check 2 against `STOCK_DAY`, `tradingStock` or FinMind `TaiwanStockPrice`.

### Trading calendar is single-sourced and unvalidated - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 90, 151, 201, 215, 228
* **Discrepancy Description**: FinMind is the only calendar, and no official history exists. The calendar drives which dates are fetched, `valid_empty`, `available_at` nulls and the coverage denominator. A wrong date skips or misclassifies a day silently. Line 151 lists the cross-check as an official schedule, but none was found.
* **Rationale & Recommendation**: Derive a second calendar from dates where `MI_INDEX` and `otc` return rows. Request all weekdays for one validation pass. Diff the calendars as a Phase 0 gate.

### Raw-cache loss is rated Low with no active mitigation - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 94, 235, 278
* **Discrepancy Description**: The backup location is undecided, yet the risk is rated Low with "second copy after each phase" as mitigation. Snapshot-only history is irrecoverable, and a WSL2 disk loss costs it plus 12 or more hours of refetching.
* **Rationale & Recommendation**: Rate it Medium and mark the mitigation "not in effect until `backup_dir` is set". Add an interim copy of snapshot shards and manifests after each daily run.

### Universe goal and check 8 contradict themselves; watchlist and term "turnover" are undefined - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 44, 73, 245-249
* **Discrepancy Description**: "Exactly 200 ranked members" conflicts with "if fewer pass the floor, keep those and report the shortfall", so check 8 has no unambiguous pass condition. "Turnover" means trading value (`turnover_ntd`) and also membership churn ("monthly turnover between 2% and 40%"), and the churn formula is undefined. With PK (`month_end`, `stock_id`), storing a watchlist name already in the top 200 is unspecified, and a per-name start date is not stated (selection bias if applied back to 2015). Step 2 depends on `TaiwanStockInfo` industry category (open in S6) with no rule for a missing category.
* **Rationale & Recommendation**: Write "200 unless fewer pass the floor, shortfall listed" in all three places. Rename churn to "membership churn" and define it. Specify `rank` null for watchlist extras and an `is_watchlist` flag, add a per-name `start_date`, and define the missing-category default.

### "One call per stock per dataset" is generalised from a single probe - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** line 166; `FINMIND_DATASETS.md` line 55
* **Discrepancy Description**: The 11-year call was proven for `TaiwanStockPrice` for one stock (2,795 rows). The other datasets include multi-row-per-day sets (institutional by investor type, securities lending by transaction type) and futures with many contract rows. A silent cap or truncation would return an `ok` response with incomplete data, and no check covers row counts.
* **Rationale & Recommendation**: Probe the largest datasets once. Add a per-call row-count sanity check and fail closed at a round-number cap.

### Several table decisions have no alternatives entry and numbering is not shared - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`
* **Affected Scope:** lines 98-109 against 285-314
* **Discrepancy Description**: The decisions table has 8 rows, Alternatives has 6 numbered decisions, and the numbering differs. No alternatives exist for shares issued from `MI_QFIIS` (line 108), last trading day from daily files (line 109), or Agent A owning all-stock collection (line 107). Decisions 5 and 6 are not in the table. There is no evaluation of the corporate-action source (FinMind `DividendResult` versus official files) or the calendar source. Line 289's "comparable request counts" holds for hours, not requests (about 11,400 official versus about 4,000 to 6,000 FinMind).
* **Rationale & Recommendation**: Share one numbering. Add Pro/Con/Rejected entries for the missing decisions or mark them "no viable alternative" with a reason.

### Alternatives entries are uneven and "rejected by" claims are unlinked - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 287-314
* **Discrepancy Description**: Decision 1 uses Pro/Con, Decisions 2-4 use "Chosen / Rejected by" bullets, and Decisions 5-6 are single paragraphs. Line 314 cites `docs/DECISIONS.md` and the plan as plain text. "Rejected by author" and "Rejected by Lead" (lines 291, 295, 300, 305, 310) point to no record. The trailing "Rejected by Lead" at line 310 is ambiguous about which items are rejected (`requests-cache`, the `FinMind` package, `pandas`).
* **Rationale & Recommendation**: Use one template (Options, Pro, Con, Verdict, Reason) and link each attribution to a `docs/DECISIONS.md` anchor.

### Snapshot-only tables are missing from schema, `available_at` and source-policy tables - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 42, 144-153, 172, 174-216, 238
* **Discrepancy Description**: The snapshot job writes `TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap*`, `warning` and `sprc` tables with `snapshot_date` and `first_seen_at` (line 238). They have no schema row, primary key, `available_at` rule or source-policy row, while lines 42 and 172 say every clean table has `available_at`.
* **Rationale & Recommendation**: Add a snapshot-table group to the schema, `available_at` and source-policy tables.

### Universal `event_date`/`available_at` claim conflicts with exemptions - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 42, 172, 215-216
* **Discrepancy Description**: Goals and "Common table columns" say every clean table has both columns, but `trading_calendar` and `stock_info` are exempt (line 215) and `delistings` is cross-check only (line 216).
* **Rationale & Recommendation**: Scope the claim to "every joinable clean table" or state the exceptions at lines 42 and 172.

### Benchmark index sources are inconsistent and `TPEX_TR` has no primary - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** lines 146, 153, 183
* **Discrepancy Description**: The benchmark appears in two source-policy rows with different cross-checks (`TaiwanStockPrice` versus `TaiwanStockTotalReturnIndex`). `benchmark_index` defines `TPEX_TR` but row 153 lists only TAIEX and Taiwan 50 from `MI_INDEX`. `TAIWAN50_TR` has no FinMind cross-check (none documented), FinMind `TPEx` may return two series (unresolved), and 0050 itself needs split and dividend actions for adjusted benchmark returns.
* **Rationale & Recommendation**: Merge the rows, name a primary for `TPEX_TR`, state which series have no cross-check.

### `status_events` types lack sources and `chtm` mapping - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`
* **Affected Scope:** lines 150, 182
* **Discrepancy Description**: Types `split_trading`, `managed`, `halt` and `suspension` have no source-policy row (line 150 names only disposition, attention and changed trading). `announce_date` is in the PK, but TPEx `chtm` is a per-day state list with no announce date and a full-width `Ｙ` flag. Full-delivery is folded into the changed-trading flag only by inference.
* **Rationale & Recommendation**: Add sources or mark the types deferred. Define how `chtm` states become events (for example first day seen).

### S1 coverage claim compares dates a year apart - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 79, 155
* **Discrepancy Description**: "915 rows against 951 `MI_INDEX` rows on comparable dates" is unsupported. 915 is the 2015-06-01 `MI_QFIIS` file and 951 is the 2016-06-01 `MI_INDEX` file. `MI_INDEX` also includes ETF and DR rows. No gap has been measured. The same wording is in `OFFICIAL_SOURCES.md`.
* **Rationale & Recommendation**: State both counts with their dates and "coverage unmeasured". Correct `OFFICIAL_SOURCES.md` too.

### Delisting-gap and FinMind-coverage claims overgeneralise small samples - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 108, 109
* **Discrepancy Description**: "Last trade is 3 to 13 days before the delisting date" rests on six stocks, and the TPEx sample 5306 has a 1-day gap, so the range is 1 to 13. `OFFICIAL_SOURCES.md` repeats the wrong "3 to 13 in all six". "FinMind lacks delisted TPEx names" rests on one probe (3299 returned 0 rows).
* **Rationale & Recommendation**: Write "in six sampled stocks, 1 to 13 calendar days" and "no rows for 3299, one delisted TPEx stock probed".

### Check 4 states unverified claims as fact - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 69
* **Discrepancy Description**: "FinMind prices derive from exchange data" is an inference (`finmind_findings` Q7 found no page saying so). "Both report two decimals" has no evidence in the reading list. The claim that the check cannot detect errors in the exchange's own files depends on the unverified derivation. At 500 samples, 99.9% is 499.5, so the rule is effectively zero mismatches, and FinMind's documented 2022-11-28 to 2023-03-27 low-volume rows will mismatch.
* **Rationale & Recommendation**: Mark these as assumptions or verify them in a spike. State the exact pass rule and the known exclusion.

### Decision 2's "one conservative rule" contradicts the `available_at` table - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 104, 205, 207, 212, 295-296
* **Discrepancy Description**: The chosen rule is "one conservative rule" with per-dataset rules rejected, yet the table uses at least four timings (18:00 same day, the 10th at 18:00, a statutory deadline, next calendar day 08:30). "Conservative" is subjective and untrue for same-day 18:00.
* **Rationale & Recommendation**: State which datasets Decision 2 covers (date-only flow and status sources) and replace "conservative".

### Decision 1 contradicts its own numbers and carries process narrative - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 163-164, 289-290
* **Discrepancy Description**: Option A is costed at about 2,000 or more requests and B at about 14,000, yet "request counts are comparable" appears under both. "7.5 h versus 8 h" is called not derived, and 2,000 requests at 600/h is about 3.3 h. The history of what the author was told belongs in `docs/DECISIONS.md`. "Achieves most of the benefit" and "about double the storage and work" (line 291) are unsupported.
* **Rationale & Recommendation**: Replace with one derived comparison or keep only the survivorship and shares-issued rationale. Move the narrative to `docs/DECISIONS.md`.

### Check 6 wording conflicts with the revenue `available_at` rule - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 71, 207
* **Discrepancy Description**: Check 6 says revenue `available_at` is "after the first day of the following month", while the rule says the 10th at 18:00 or the next trading day. A test written from line 71 would pass wrong values.
* **Rationale & Recommendation**: Use the rule's wording in check 6.

### Defensive pointer to Open Questions names no open item - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 47, 283
* **Discrepancy Description**: Lines 47 and 283 say open items that could change the design (or force a paid tier) are in Open Questions, which never mentions the tier or names such an item. The risk row's "Low" likelihood has no stated basis, and `DECISIONS.md` asks for a list of what a paid tier would unlock, which the design lacks.
* **Rationale & Recommendation**: Drop the pointer or name the specific open item and the decision it triggers. Add the paid-tier deliverable. Consider `TaiwanStockPriceAdj` as an independent check for check 3.

## Nits

### Structural nits - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 23-27, 62-95, 188-193, 218, 272-283, 289-290
* **Discrepancy Description**: (1) "see Idempotence" at line 218 points to no section; content is under "Raw cache, state and writes" (line 237). (2) "Phase 0", "phase gate" (lines 94, 235, 268, 278), "data dictionary" (line 218) and "collection set" (line 15, defined line 26) are used before definition. (3) Line 26 packs four glossary entries into one bullet and the References and terms H3 mixes links, roles and glossary. (4) Acceptance checks and Open Questions (lines 62-95) come before the Technical Plan but use terms it defines (line 82 "see Universe"). (5) Schema rows 185-193 combine several tables, use "per source columns" as a column list, and put a note in a column cell. (6) The TWSE full-delivery gap is stated at lines 59 and 88, and Open Questions holds accepted gaps and pending decisions that are not questions. (7) Goals lines 43-44 repeat checks 1, 6 and 8. (8) Risk rows 275 ("Medium over 12 hours of requests") and 282 (Owner "All") are not normalised, and there is no security row (token leakage appears only at line 318). (9) Headings differ from the standard's names ("Problem Statement", "Proposed Architecture", "Risks & Mitigations"). (10) Line 218 mixes a daylight-saving note and a first-reported caveat.
* **Rationale & Recommendation**: Fix the cross-reference, define terms at first use, split the glossary, reorder or add forward links, give each table its own schema row, keep one canonical home for accepted gaps, normalise risk cells, add a security risk row, align or map heading names, and split line 218.

### Style nits - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 4, 31, 34, 36, 38, 43, 66, 89, 102, 106, 146, 151, 155, 159-166, 197, 212, 218, 222, 235, 238, 274-275, 310
* **Discrepancy Description**: "A strategy test is only as honest as its data" (line 31) is rhetoric. "Delisted names can have done worse" (line 34) has no cited basis. Line 36 should cite FinMind's 2026 restatements. Line 38 history back to 2015 reflects only tested windows, and TPEx 2002/2003 comes from page notes. The "non-suspended" qualifier (lines 43, 66) cannot be evaluated for TPEx before 2026 (line 89). The three TPEx `otc` era boundaries are evidenced for 2025-01-10 only. Line 197 states one-market-per-date as fact while check 7 tests it and line 109 says codes are reused. Line 212 (08:00 update) is documented, not verified. Line 218's "not first-reported before 2026" is hard to parse. Line 222 "approximates total return" is unquantified and "may be produced by agent B" is ambiguous. `status --verify` (line 235) is undefined and the CLI is shown only as `python -m twdata snapshot` (line 238). The "date parameter catch-up" sentence at line 238 applies to no listed source, and "stateless" conflicts with comparing against the calendar. The user-agent note at line 274 is unrelated to IP blocks. "No-overwrite gate" (line 106) is undefined jargon. Line 102's "original request-count reason" is not stated where used. Line 310 "about 60 lines" and "handles" are vague.
* **Rationale & Recommendation**: Calibrate or cite each claim, drop the rhetoric, define the jargon, and remove or fix the vacuous sentences. Line 4's status line is fine.

### Design nits - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 46, 69-70, 79, 182, 197, 208, 237-238, 240, 318, 320
* **Discrepancy Description**: (1) Financials `available_at` (line 208) is ambiguous between the deadline date at 08:30 or the day after, drops the plan's real MOPS filing dates without reason, and P2 scope is inconsistent. (2) Check 5 needs documented exceptions beyond ex-dates and first listing days (capital-reduction resumption, suspension gaps). (3) `stock_id` joins ignore ISIN, which `MI_QFIIS` provides, despite code reuse. (4) "No duplicate rows" (line 46) conflicts with append-only files, and run-file proliferation needs a batching rule. (5) TPEx `sprc` showed a server date one day ahead, so state whether `snapshot_date` comes from the body or local time. (6) `MI_QFIIS` and `TWT84U` are collected daily but needed only for month-end ranking, and limits can be computed from the prior close. (7) The fixed 5 s spacing assumes a continuous run despite WSL2 sleep, `fcntl` locking needs ext4 not `/mnt/c`, FinMind `user_count` can sync the local counter, and bulk-scraping terms of use are not in Risks. (8) S1 (line 79) has no numeric threshold for missing shares-issued rows, and the 150 KB per-file footprint was measured for one TWSE file type, not multi-table `MI_INDEX`.
* **Rationale & Recommendation**: Resolve each as a short clarification or spike item.
