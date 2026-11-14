# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-341`, everything above `## Detailed Implementation Plan`)

Standard applied: `feature-spec-standard`. The style lens has no standard. Findings reported by more than one reviewer are merged, and every contributing lens is named.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-design` | completed |
| `egm-structural` | completed |
| `egm-style` | completed |

## Severity Summary

Blockers: 0. Majors: 23. Nits: 28.

All five standard blueprint areas are present (under the names "The Problem" and "Technical Plan (Architecture)"). The weak points are these:
- The alternatives section gives no reasons for several rejected options.
- Several acceptance checks have no usable pass rule.
- Several schemas "of record" are deferred or have doubtful keys.
- The "conservative upper bound" claim for `available_at` is stronger than the evidence.
- Several statements are stronger than the research files support.

The reviewers checked the request-budget arithmetic (8,529 and 5,686 requests, 11.8 h, 7.9 h, 10.5 h, 20,700 responses) and found it consistent.

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

### Alternatives section lacks reasons and a common template - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`, `egm-style`
* **Affected Scope:** lines 306-334 (D1-D9), esp. 322, 330, 332, 334
* **Discrepancy Description**: Line 306 says each entry uses the same template. Only D1 does. D4's lighter alternative is "not chosen here, can be revisited", D8 and D9 give no reason, and line 334 rejects a paid tier and a database server as "rejected earlier by the author" with no trade-off or link. Design-weight choices have no entry at all: manual corporate actions against paid `TaiwanStockPriceAdj`, the `chtm` suspension proxy, the `restatement_class` two-view scheme, and the 5 s spacing.
* **Rationale & Recommendation**: The standard requires specific documented reasons. Add the missing entries and one template. Give every "Not chosen" a concrete cost or loss. For D4, say why a rebuildable clean layer over immutable raw is rejected. Link DECISIONS.md and plan section 5, and use the finmind_findings numbers (about 25,200 requests, Backer or higher).

### Attended versus unattended run, and no sleep/resume risk - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** lines 114, 179, 244, 292, 332
* **Discrepancy Description**: D7 justifies stop-on-first-error by "an attended run". The request budget describes one 18-19 h unattended run. D9 says the WSL2 machine sleeps, and no risk row covers sleep or resume. No one is named to be notified on a stop.
* **Rationale & Recommendation**: State the operating mode once. If unattended, name who is notified and how a run resumes. Add a sleep-prevention prerequisite and a risk row. State the expected number of manual restarts.

### Agent F's stated ownership cannot be executed - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 249, 278 against `.claude/agents/qa-goldfish.md` and plan 6.1/6.2
* **Discrepancy Description**: The design gives F sole ownership of `src/twdata/validate/`, `tests/validate/` and the report files. The qa-goldfish definition has only Read, Grep, Glob and Bash, and it may not edit `src/`. Line 249 calls `data/raw/qa/` "the one exception to F's read-only access", which conflicts with the write ownership.
* **Rationale & Recommendation**: Name the real owner of the validation code, or change F's definition. Reconcile the "read-only" wording. Plan 6.2 gives F too little input to implement these thresholds.

### Schemas "of record" are partly unspecified, and several primary keys are doubtful - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-design`
* **Affected Scope:** lines 17, 185-209 (esp. 199-203), 200, 202
* **Discrepancy Description**:
  - Many tables are defined only as "the source columns", and line 209 defers them to Phase 0.
  - There is no table for `TaiwanStockPrice` (checks 1, 3 and 4 depend on it), `TaiwanStockDividendResult` (check 3) or `TaiwanFuturesInstitutionalInvestors`. The last has an investor dimension and no `contract_date`, so it does not fit `futures`. `rates` also merges two datasets.
  - `securities_lending` is keyed on (`stock_id`, `event_date`, `transaction_type`), but probe 2 returned 17,960 rows for 2,795 days (about 6.4 per day). `market_cap`'s key omits `market`.
  - The PK assertion stops the run, so the first run could halt.
* **Rationale & Recommendation**: Mark which schemas are deferred. Add the missing tables. Verify the keys on a sample before approval. Add a sequence or fee-rate column, or a stated aggregation rule, for `securities_lending`. Give futures institutional data its own table.

### Snapshot `event_date` can fall after `available_at`, and `event_date` is undefined for several tables - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** line 203 against line 45, and line 209
* **Discrepancy Description**: `snapshot_date` comes from the response body when present. tpex_findings fact 7 shows TPEx returning 115/11/14 on local 2026-11-13, a day ahead. That breaks the goal that no joinable row has `available_at` earlier than `event_date`. The `event_date` meaning for `snapshot_<source>`, `dividend_announcements` and `corporate_actions` is unstated. For capital reductions it could be the ex-date or the resumption date.
* **Rationale & Recommendation**: Define `event_date` for every joinable table. Clamp or flag a snapshot date later than `first_seen_at`. Say that local date means Asia/Taipei.

### Phase terms are used before they are defined, and "Phase 2" collides with the plan - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 17, 100, 115, 285
* **Discrepancy Description**: Phases 0, 1 and 2 are used in the scope but defined below it. D8's "Phase 2 scope" collides with plan section 10, where Phase 2 is the market research loop. Line 17 claims the document fixes phase gates, but the gates come later.
* **Rationale & Recommendation**: Define the phases in the Overview terms list and rename D8's "Phase 2".

### Acceptance-check self-description is false - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** line 67 against lines 45-47 and 69-76
* **Discrepancy Description**: Line 67 says each check has one pass condition and that the Goals do not restate thresholds. Checks 2, 3(a)/(b), 4, 5 and 6 have several conditions. Goals lines 45-47 restate the 99%, the 200 members and 2330.
* **Rationale & Recommendation**: Have the Goals point to the checks only, and reword line 67. Require a DECISIONS entry for any threshold change after the first sample.

### Open Questions is mostly a log of resolved spikes - Severity: Major
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** lines 78-90
* **Discrepancy Description**: S1-S4 and S7-S9 are resolved, along with accepted gaps and one author decision. Only S10, S5/S6, the S8 reference price and the backup decision are open. The order is out of sequence. Line 80 says each spike gates the modules it names, but S10 names none. Line 80 gives the owner as Lead, but line 90 assigns S5 and S6 to agents C and A.
* **Rationale & Recommendation**: Move resolved results to a "Spike results" section or to DECISIONS.md. Keep only open items here, each with an owner and a gate. Make S10 gate the universe pass and `prices_raw`.

### D-number and definition references do not hold - Severity: Major
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 23, 34 against 113, 108, 213
* **Discrepancy Description**:
  - Line 23 says the D1-D9 numbers match `docs/DECISIONS.md`, which has no D-numbers.
  - D2 is "Author" in the design, but DECISIONS.md line 74 files it under "Lead proposals until Ken confirms".
  - The last-trade gap is "3 to 13 days" in line 34 and "1 to 13" in line 113.
  - "Four timings" at line 213 is wrong, because the table has at least seven or eight.
* **Rationale & Recommendation**: Add D-numbers to DECISIONS.md or drop the claim. Reconcile D2's status and the gap range. Correct the timing count.

### "Every rule gives a conservative upper bound" is not supported - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 213, 217, 220, 221, 314
* **Discrepancy Description**:
  - The 18:00 rule for `prices_raw`, `shares_issued` and `benchmark_index` is a "design assumption tested in S10", and S10 is unresolved.
  - S10 polls only `MI_INDEX`, `otc` and `MI_QFIIS`, so nothing measures the 08:30 rule for flows, margin, lending, FX or futures. `first_seen_at` exists only on snapshot tables.
  - Statutory deadlines bound only on-time filers.
  - `dividend_announcements` uses an unverified announcement date, and `financials` carries "restated figures are a known lookahead risk".
  - Check 6's revenue test only checks the rule against itself.
* **Rationale & Recommendation**: Say which rules are bounded by evidence and which are assumptions. Give each exception a bound or a gate. Compare late filers against FinMind or MOPS evidence on a sample.

### Some acceptance checks have no usable pass rule - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 69-73 (checks 3(a), 3(b), 5)
* **Discrepancy Description**: Check 3(b) "lists" moves beyond 8% and "reconciles" event counts with no tolerance. Check 3(a) compares the adjusted return to FinMind `TaiwanStockPrice`, which is raw (`PriceAdj` is paid), so it can agree only on non-event days. Check 5 allows an exception list with no size cap or approver.
* **Rationale & Recommendation**: Give each check a numeric or set-based rule. Say which days compare to raw returns and which to `DividendResult`. Default unexplained moves to 0. Say who approves exceptions.

### Acceptance coverage misses the C, D and E datasets - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 65-76 against D8 (line 115) and line 241
* **Discrepancy Description**: D8 puts all C, D and E datasets in scope, but checks 1-5 cover only prices, universe and corporate actions. Nothing tests completeness for monthly revenue, flows, financials, shareholding, margin or the macro series. FinMind returns empty answers and the classifier treats them as `ok`, so a tier-gated or thinned dataset would pass. The "fallback share per dataset" metric (line 45) is meaningless where the fallback is the only rule.
* **Rationale & Recommendation**: Add a completeness check per dataset family against the calendar and listing span, with a fail threshold. This also gives COVERAGE_REPORT content.

### TPEx ISIN has no stated source - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 154, 190, 206, 75
* **Discrepancy Description**: The ISIN comes from `MI_QFIIS`, which is TWSE only. The TPEx `otc` fields (spikes_tpex_findings S9a) have no ISIN. `shares_issued.isin` and `universe_membership.isin` are therefore null for TPEx, and check 7's ISIN guard against code reuse does not cover TPEx.
* **Rationale & Recommendation**: Source TPEx ISINs (probe a company-profile endpoint), or say TPEx code reuse is caught by name and date rules only. Mark the column nullable and state check 7's TPEx behaviour.

### Trading-calendar second-source check is mis-sequenced and one-sided - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 96, 158, 285
* **Discrepancy Description**: The diff is "at the Phase 0 gate", but the `MI_INDEX` and `otc` files exist only after Agent A's universe pass. That pass requests only FinMind's 2,843 trading days, so it can find FinMind-only days and cannot find days FinMind omitted. Zero rows on a calendar day is `drift` and stops the run, so the calendar is a single-source stop-the-run dependency.
* **Rationale & Recommendation**: Move the diff to Agent A's gate. Request all weekdays (about 150 extra per host) in the staged year, or state the check is one-sided. Say what happens when FinMind and the exchanges disagree.

### Check 1 reference and the no-trade-row rule - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-structural`
* **Affected Scope:** line 69 against line 72, line 262
* **Discrepancy Description**: Check 1 uses FinMind day counts and does not exclude the documented 2022-11-28 to 2023-03-27 zero-volume backfill, which check 4 excludes. FinMind shows zeros for no-price days in emerging stocks. The `prices_raw` handling of a `--` no-trade row is undefined (null OHLC, volume 0 or no row), which affects check 1 and the observed-days median in the universe.
* **Rationale & Recommendation**: Exclude or special-case the backfill window in check 1. Define the no-trade-row rule in the schema section.

### Vintage and lookahead guarantee is overstated - Severity: Major
* **Reviewer Lens:** `egm-design`, `egm-style`
* **Affected Scope:** lines 36-39, 49, 75, 111, 138, 213-221, 252, 299
* **Discrepancy Description**:
  - Goals, check 7 and D4 promise a "first-reported" view, but the views are `as_first_seen`, and line 252 admits 2026-collected history is not first-reported before 2026.
  - FinMind's changelog records an EPS change (2026-10-11), an ETF dividend duplicate fix (2026-10-22) and institutional buy/sell rising after first publication. The 08:30 next-day rule stamps the backfilled final value as known earlier than it was.
  - `restatement_class` assigns "economic" to dividends and flows, so `as_first_seen` would keep the erroneous duplicate. Many tables have no class.
  - Whether FinMind recomputes `TaiwanStockPER` history is unknown.
* **Rationale & Recommendation**: Use `as_first_seen` everywhere. State a guarantee level per dataset (true point-in-time, last-vintage, conservative-lag) in Goals or Non-Goals. Name the datasets whose results carry hindsight (financials, valuation ratios, flows). Add a risk row. Assign a class to every table. Consider ruling out financials as features until filing dates exist.

### Shared clean-writer and views layer has no owner - Severity: Major
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 252, 270-281
* **Discrepancy Description**: The append-only Parquet writer, `v<N>` pointer switching, `restatement_class` registry, PK assertion and the generic DuckDB views (`as_first_seen`, `as_latest_corrected`, `revisions`) belong to no agent. Derived tables (`market_cap`, `universe_membership`, `collection_set`, `data/reference/`) have no versioning or rebuild rule. A parser fix can change historical membership silently.
* **Rationale & Recommendation**: Assign a Lead-owned module for the clean writer and views. State how derived tables are versioned so a past membership can be reproduced.

### Split and halt claims go beyond the evidence - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 87, 236 (also line 88)
* **Discrepancy Description**: "No official feed carries stock splits or par-value changes" rests on `TWT49U` in full and on `TWTAUU` and TPEx `exDailyQ` for 2025 only. TPEx `revivt` was checked by field list, and the TPEx par-value reference page is untested. "Confirms a 4-for-1 split" and "a halt from 2025-06-11 to 2025-06-17" rest on FinMind prices only (188.65 to 47.57, ratio 3.97). DECISIONS.md line 82 says an independent confirmation is needed, while line 88 says "confirmed from prices".
* **Rationale & Recommendation**: Write "none of the four feeds checked, for the years searched". Write "consistent with a 4-for-1 split and a halt". State that the exact ratio comes from the announcement.

### `TWT49U` "split capital reductions are excluded" is ambiguous - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 87
* **Discrepancy Description**: The source wording 分割減資 usually means a demerger capital reduction, not a stock split. The sentence reads as support for the stock-split gap. If it is a demerger, that uncovered gap is not in the accepted gaps.
* **Rationale & Recommendation**: Translate precisely and state whether the gap exists. Record it under accepted gaps if so.

### TPEx full-delivery mapping into `chtm` is inferred, not verified - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 30, 62, 94, 261
* **Discrepancy Description**: Line 30 states as fact that TPEx reports both conditions in one `chtm` column. tpex_findings Q1(c) says the mapping is "inferred, not verified". Universe step 3 and the accepted gap depend on it. If the mapping is wrong, TPEx full-delivery is a second unrecorded gap.
* **Rationale & Recommendation**: Write "inferred, not verified" and have QA verify the mapping.

### Cross-check column names comparisons that no check performs - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 154-162, 155, 230
* **Discrepancy Description**: No numbered check consumes the `TaiwanStockShareholding`, `t187ap05_L`/`BWIBBU_d`/`t187ap06_L_*`/`t187ap07_L_*`, `TAIEX` benchmark or prior-close limit comparisons. Line 230 says a check confirms mask consumers use the effective window, but no check does. OFFICIAL_SOURCES line 73 shows the `t187ap*` endpoints are latest-snapshot only, which the table does not say.
* **Rationale & Recommendation**: Add numbered checks, or mark these comparisons informational and give their scope.

### Failure taxonomy is incomplete - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 240-241
* **Discrepancy Description**: Line 240 says any block stops the run. Line 241 defines only `ok`, `transient` and `drift`. A TWSE or TPEx 403 or other 4xx fits none of them, and an exhausted retry has no class.
* **Rationale & Recommendation**: Assign every case to a class, including blocks and exhausted retries.

### "Resolved S7" and "14 datasets probed" overstate the evidence - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 86, 300
* **Discrepancy Description**: Long-range calls were verified for about 10 of the 14 per-stock datasets. `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`, `TaiwanStockCashFlowsStatement` and `TaiwanStockDividend` were not long-range probed, and the first three have many rows per quarter, so they are likeliest to hit a cap. The "27 of 27" probe was one small request per dataset.
* **Rationale & Recommendation**: State which datasets were tested over the full range and which were only existence-checked.

## Nits

### Heading names deviate from the standard - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 32, 102
* **Discrepancy Description**: "The Problem" is used for Problem Statement and "Technical Plan (Architecture)" for Proposed Architecture.
* **Rationale & Recommendation**: Optionally rename.

### Acceptance checks come before the architecture they test - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 65, 49
* **Discrepancy Description**: The checks use `available_at`, the universe, the views and `restatement_class`, which are defined later. Goals line 49 uses "first-reported view" before the views are named.
* **Rationale & Recommendation**: Add forward references or reorder.

### Referenced plan sections are incomplete - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 21, 28, 56, 334
* **Discrepancy Description**: Line 21 lists plan sections 2, 4, 6 and 7. The design also relies on sections 3, 5 and 8.
* **Rationale & Recommendation**: List all of them.

### Pre-roll start date is not stated in the Overview - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** lines 13, 17, 257, 170
* **Discrepancy Description**: The Overview says collection runs from 2015-06-01, while line 257 and the budget use 2015-03-02. Line 170 estimates 2,843 trading days. The measured count including March-May 2015 is about 2,856.
* **Rationale & Recommendation**: State the pre-roll in Overview or Goals, and use the measured count.

### Snapshot source count is inconsistent - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** lines 116, 164, 253, D9
* **Discrepancy Description**: Line 164 names 13 sources (11 TWSE, 2 TPEx). D9 and line 116 say "about 12". Line 253 also says latest-only sources with a date parameter "catch up", which is self-contradictory.
* **Rationale & Recommendation**: State the exact number and fix the wording.

### TWSE `TWTAWU` is verified but not carried into the design - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** line 84, source policy, `status_events`
* **Discrepancy Description**: `TWTAWU` (suspended securities) appears in S3 but not in the source policy or schemas. It is unclear which source defines "suspended" for Goals line 46. `chtm` also includes the stop-trading flag, but the `status_type` enum has no suspension type.
* **Rationale & Recommendation**: Add it to the source policy or state it is excluded. Say where the suspension proxy lives.

### Manifest, `revisions` view and reference-table storage are unclear - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** lines 138, 146, 183, 249
* **Discrepancy Description**: Two manifests are described (`data/state/manifest/` and one carried by raw shards). The `revisions` view appears in the data flow and is not described. Reference tables (calendar, stock info, delistings) have no stated path.
* **Rationale & Recommendation**: Define each manifest once, describe the view, and give the paths.

### Repeated statements will drift - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`
* **Affected Scope:** lines 52, 243, 301, 338 (token), 84 and 242 (150 s timeout), 100, 250, 295 (`backup_dir`), 88, 166, 87 (era text), 47 and check 8
* **Discrepancy Description**: The same rules and facts are restated in several places. Line 166 says "three field-list eras" and also "the same 17 fields" (two lists and one relabel).
* **Rationale & Recommendation**: Choose one home for each and cross-reference.

### Terms-of-use risk row is non-actionable - Severity: Nit
* **Reviewer Lens:** `egm-structural`, `egm-style`, `egm-design`
* **Affected Scope:** line 302
* **Discrepancy Description**: Likelihood is "Unknown" and the mitigation is "not reviewed". It is an author action that precedes about 14,000 requests to public endpoints.
* **Rationale & Recommendation**: Give a concrete action or a deferral with an owner, and list it under author decisions pending.

### Problem section mixes evidence with the problem statement - Severity: Nit
* **Reviewer Lens:** `egm-structural`
* **Affected Scope:** line 41
* **Discrepancy Description**: Gap lists and sampled windows sit in the problem text.
* **Rationale & Recommendation**: Move them to references or a short Constraints subsection.

### Narration of earlier revisions - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 4, 82, 108, 334
* **Discrepancy Description**: The text narrates notes the reader never saw ("915 versus 951 was an artefact", "the original request-count reason did not hold", "dropped").
* **Rationale & Recommendation**: DROP, and keep it in DECISIONS.md.

### Smaller overstatements in spike results - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 83-85, 155, 166
* **Discrepancy Description**:
  - "1,094 of 1,094" omits the denominator (1,116 rows).
  - The TPEx limit rule was value-tested on 2025 pairs only, yet line 155 applies it to all history.
  - "No truncation" is inferred from counts.
  - The "-DR" clause is TWSE only.
  - The "11 TPEx dates" are 10 distinct years.
  - The "seven 2015 dates" claim is TWSE only, and TPEx has three.
* **Rationale & Recommendation**: CALIBRATE each statement to its evidence.

### Disclaimers without a reader decision - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 71, 72, 197, 220
* **Discrepancy Description**: Inherent-limit sentences lead to no action. "Restated figures are a known lookahead risk" names no mitigation. The unverified-announcement note belongs in the line 221 rule row.
* **Rationale & Recommendation**: RELOCATE or DROP.

### D5 rationale cites the wrong evidence - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 112, 324
* **Discrepancy Description**: D5 covers TWSE shares issued, but the basis cites missing TPEx stock 3299. The TWSE evidence is FinMind continuing 19 months past 2475's last trade, and `MI_QFIIS` having no gaps on four dates.
* **Rationale & Recommendation**: Cite the TWSE evidence.

### Overhead and trading-day figures lack derivation - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** line 179
* **Discrepancy Description**: The "under 5%" overhead has no derivation. The 500-close sample reuses already-pulled data and needs no new requests, but the macro and US requests are not counted.
* **Rationale & Recommendation**: Derive or remove the figure and fix the request list.

### D1 request-count comparison is inaccurate - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** lines 309-311, 178
* **Discrepancy Description**: "Request counts are comparable" conflicts with line 178 (about 14,400 official against about 6,300 FinMind, roughly 2.3 times). Option B is about 14,200 requests against about 3,800 FinMind for price and shareholding. Wall-clock is comparable (about 6 h against 8 h), and host risk is not.
* **Rationale & Recommendation**: State the figures. The survivorship and shares-issued reasons stand alone.

### Unbacked claim that no package provides a cross-process spacing lock - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 334
* **Discrepancy Description**: Packages such as `pyrate-limiter` advertise multi-process backends.
* **Rationale & Recommendation**: Name what was evaluated or soften the sentence.

### Smaller wording and precision items - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 13, 38, 39, 47, 49, 72, 160, 161, 183, 192, 195, 199, 236, 249, 253, 261, 293, 298, 340
* **Discrepancy Description**:
  - "Avoid using the future" should be "avoid lookahead". "Returns nobody could have earned" should be "returns that were not achievable".
  - "Without notice" (line 39) conflicts with FinMind's public changelog.
  - `snapshots.py` is a file name in a document that defers file lists.
  - "If any" (line 261) hedges whether TWSE has a changed-trading source.
  - "Cached raw before parse" (line 249) conflicts with "a crash can lose the shard" (line 49).
  - `TPEX_TR` is unverified as a total-return index (line 160), and `cash_dividend` and `stock_dividend_per_1000` fields exist in TPEx `exDailyQ` but not in the `TWT49U` field list (line 192).
  - The 0050 benchmark row's place in `universe_membership` is unclear (line 161). `revenue_ntd_thousand` (lines 183, 195) is hard-coded before S5 confirms the unit.
  - The roughly 3 GB figure multiplies all 20,700 responses by one 150 KB file size.
  - The "Medium" likelihood for an endpoint changing shape mid-run is unsupported.
  - The adjusted-prices paragraph (line 236) and S8 (line 87) each mix several topics.
* **Rationale & Recommendation**: Apply the wording and precision fixes listed.

### Request savings and sequencing options not considered - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 174, 179, 262
* **Discrepancy Description**: `MI_QFIIS` is collected daily (about 4 h), but market cap is needed only at month-ends (about 138 dates) plus corporate-action dates. `MI_QFIIS` and `TWT84U` for March-May 2015 are untested. The FinMind pull could start incrementally rather than after the whole pass, which sets the 18-19 h figure.
* **Rationale & Recommendation**: Record the choice as an alternative, or cut the request count.

### `chtm` chronology conflicts with universe step 3 - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 179, 193, 261, 262, 285
* **Discrepancy Description**: Universe step 3 needs `chtm` and `punish` status at month-ends, but line 179 puts `chtm` in the post-pass background. On its first day seen a `chtm` state may predate collection, so `start_date` is the collection date. Agent E's "needs only Phase 0" conflicts with Agent A owning the calendar ingest.
* **Rationale & Recommendation**: Collect `chtm` at least at month-ends, state the `start_date` limit, and fix the dependency.

### TWSE `punish` and `notice` evidence is not cited - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 41, 157, 164
* **Discrepancy Description**: They are the only sources for TWSE disposition and attention, with cross-check "None". The supplied research gives no field list or sample, and `OFFICIAL_SOURCES.md` line 34 only asserts windows. `status_events` needs `announce_date`, `start_date` and `end_date` from them.
* **Rationale & Recommendation**: Confirm the fields in a spike note or cite the evidence file.

### Corporate-action ratio, 0050 and index cross-checks - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 160, 161, 192, 236
* **Discrepancy Description**: `corporate_actions` has no `ratio` column, and the formula does not say how the split and `par_value_change` factor is computed. 0050's split depends on one hand-entered number whose reference price is open. `TAIWAN50_TR` from `MI_INDEX` is an independent cross-check, yet line 160 says "no cross-check".
* **Rationale & Recommendation**: Add the column and the factor rule. Always include 0050 in the check-3 sample. Use `TAIWAN50_TR` as a cross-check.

### Check 2 assumes 2475, 3474 and 3299 were ranked members - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** line 70
* **Discrepancy Description**: 3299 is a small TPEx stock and may never have ranked in the top 200 above the NT$20M floor. FinMind prices were probed only for 2475.
* **Rationale & Recommendation**: Test whether each was ever a member, or relax to "present in the collection candidate set before the rank step".

### Watchlist and collection-set definitions are ambiguous - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 207, 264
* **Discrepancy Description**: The `rank` and `is_watchlist` combination for a stock that is both is undefined. The `collection_set` PK (`stock_id`, `first_month_end`) hints at multiple spans, and re-entry is undefined. A watchlist added in 2026 with an earlier `start_date` is hindsight selection. The about-450 set size is unproven, and 40% monthly churn could grow it and the 6,300 request budget.
* **Rationale & Recommendation**: Define each, and note `is_watchlist` membership is not point-in-time.

### Operational preconditions (backup, timezone, rate assumption) - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 100, 203, 240, 295
* **Discrepancy Description**: `backup_dir` is unset while the snapshot job collects irrecoverable history. "Local date" for `snapshot_date` should be Asia/Taipei. The 600/h rate is a live reading, while FinMind's pricing page says 300 for Free (about 21 h for the FinMind pull). The design does not state that effect.
* **Rationale & Recommendation**: Set `backup_dir` before the first snapshot, state Asia/Taipei, and state the effect of 300/h.

### Check 4 mismatch threshold differs from DECISIONS.md - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-design`
* **Affected Scope:** line 72 against `docs/DECISIONS.md` line 57
* **Discrepancy Description**: The design allows at most 1 in 500 mismatches (99.8%). DECISIONS.md proposes a 99.9% exact close match.
* **Rationale & Recommendation**: Reconcile the two.

### Minor inconsistencies and gaps - Severity: Nit
* **Reviewer Lens:** `egm-design`
* **Affected Scope:** lines 45, 87, 88, 166, 179, 228, 252, 285
* **Discrepancy Description**:
  - Many small `run-*.parquet` files per partition are possible, and compaction is not stated.
  - Reference tables are exempt from `available_at` (line 228), and the design does not say they are not feature inputs.
  - The `restatement_class` list leaves out `valuation_ratios`, `shareholding`, `securities_lending` and `short_sale_balances`.
  - The 150 KB footprint estimate uses a single file type.
  - S8 text repeats S9 text.
* **Rationale & Recommendation**: State a compaction policy, class the unclassified tables, and note the reference-table exemption.
