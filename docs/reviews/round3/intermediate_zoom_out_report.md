# Goldfish Review Report (intermediate zoom-out)

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (lines 1-386, revision 3)

Focus: additions and mitigations since `/home/ken/tw0050/zoom_out_report.md`, and whether earlier findings still stand.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Severity totals for new findings: 0 Blocker, 6 Major, 4 Nit (10 findings). The reviewer's own summary said 5 Major, but it lists 6 Major findings (N1, N2, N3, N4, N5, N8). The listed findings are authoritative.

Context was sufficient. No `src/`, `config/`, `scripts/`, `tests/` or `docs/specs/` exists yet, so the "hand-rolled" items are judged on design only. The new References and terms section is a real improvement.

## Prioritized Findings (Blockers -> Major -> Nits)

### N1. Phase 0 gate needs a calendar the Lead cannot build offline - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 96, 158, 357, 363
* **Discrepancy Description**: The Phase 0 gate is "offline" yet requires the calendar diff between FinMind and the derived calendar. The derived calendar is the dates on which `MI_INDEX` and `otc` return rows. That is the output of the roughly 8-hour all-date official pass that Agent A runs in Phase 1.
* **Rationale & Recommendation**: Move the diff to the Phase 1 live gate and make it A's or F's deliverable. Phase 0 keeps only "FinMind calendar loads and is tested".

### N2. Calendar source starts 2015-06-01 but collection starts 2015-03-02 - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 158, 179, 213, 241, 257
* **Discrepancy Description**: FinMind `TaiwanStockTradingDate` has 2,795 rows from 2015-06-01. The universe pass requests `MI_INDEX`, `MI_QFIIS`, `otc` and `chtm` from 2015-03-02. The classifier treats an empty reply as `ok` only on a non-trading day in the calendar, and zero rows on a trading day is `drift` and stops the run. For 2015-03-02 to 2015-05-29 no calendar entry says which empty dates are holidays.
* **Rationale & Recommendation**: State where the pre-June-2015 calendar comes from. Options are the derived calendar only for that stub, or a weekday request list where an empty reply on both exchanges in one day means a holiday.

### N3. `prices_raw` merges three endpoints and append-only does not say how - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 155, 174, 189, 209, 252
* **Discrepancy Description**: `prices_raw` carries OHLCV from `MI_INDEX` or `otc`, and `limit_up` and `limit_down` from the separate `TWT84U` request. For TPEx the limits come from the previous file (S2). These are separate fetches with different `fetched_at`. Under append-only writes with a unique key in `as_first_seen`, a second write of the same key is a duplicate-key failure or a "revision", and `source_error` then lets `as_latest_corrected` choose between partial rows.
* **Rationale & Recommendation**: Split limits into their own table (for example `price_limits` keyed on `market`, `stock_id`, `event_date`) and join in a view. This gives limits their own `available_at` (S2 showed limits are known before the open) and removes the TPEx cross-file shift from the price ingest.

### N4. 2026 TPEx suspension history will be lost at year end and is not in the snapshot set - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 95, 164, 253; `docs/research/tpex_findings.md` Q1(d)
* **Discrepancy Description**: TPEx OpenAPI `tpex_spendi_history` returns only the current ROC year (365 rows, all 2026). The accepted gap implies 2026 is covered, but the snapshot list (line 164) names only `warning` and `sprc`, and `sprc` is today only. Today is 2026-11-13, so this is a perishable capture and the only source with real suspension timestamps. Once the year rolls over, the gap statement becomes untrue.
* **Rationale & Recommendation**: Add `tpex_spendi_history` as a snapshot source now, or capture it once before year end, and check whether each yearly rollover drops history. Related, not new: the `warning` count is derivable from the `attention` cumulative column, so the `warning` snapshot is redundant.

### N5. Enforcement for agent F's write access cannot cover Bash - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 346-351 (Author prerequisites)
* **Discrepancy Description**: A custom `PreToolUse` hook keyed on agent type is proposed to permit `qa-goldfish` writes only to the validate paths. The text admits F has Bash, "already a write path". A hook cannot path-match shell redirection or `duckdb` writes, and "updated to match, including its Bash restriction" is unspecified. The independence guarantee (plan section 6.3) rests on this, and it is a Phase 0 gate prerequisite.
* **Rationale & Recommendation**: Prefer a post-hoc check. After each F run, assert that `git diff --name-only` or `git status` touches only the allowed paths, and fail the round otherwise. It covers Bash and is testable. Keep the hook only if the Lead can show it blocks Bash writes.

### N8. Collection-set size of 450 is inconsistent with check 8's churn ceiling and the quota plan - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 76, 177-179, 340; plan section 2
* **Discrepancy Description**: 6,300 FinMind requests (14 datasets x 450 stocks) fill the hourly quota exactly (earlier finding, still open). The 450 figure is carried from the plan's "expect 350 to 450" with no derivation. Check 8 allows 2% to 40% monthly churn, and at even 3% monthly churn on 200 members over 137 months the union grows well past 450. Each extra 100 stocks adds 1,400 requests, about 2.3 hours at the full limit.
* **Rationale & Recommendation**: After the staged first year, recompute the collection-set size and extrapolate. State the set-size sensitivity in the budget, and pair it with a limiter target below 100% of the quota.

### N6. D7's basis contradicts the run profile - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 114, 179, 240, 292
* **Discrepancy Description**: D7 is justified as "fewer moving parts for an attended run", but the budget calls the 18-19 hour collection "one unattended run". An unattended run that halts on its first `drift` mostly stops overnight. The choice is the author's and is not reopened.
* **Rationale & Recommendation**: Reconcile the wording: either "attended in sessions, resumable", or state the cost of an overnight stop in D7.

### N7. Whole-table field lists make unconsumed header changes fatal - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 166, 241, 245
* **Discrepancy Description**: TPEx `otc` has three era field lists. The only 2025-era change is a relabel of bid and ask volume columns, which `prices_raw` does not store. Under "a field list outside the registered set is `drift`", such a relabel stops an 18-hour run.
* **Rationale & Recommendation**: Validate consumed columns by name and position and treat the rest as informational. This removes most of the era registry.

### N9. Check 2 may be unsatisfiable for 3299 - Severity: Nit (low confidence, not verified offline)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 70
* **Discrepancy Description**: Check 2 requires the universe to hold 2475, 3474 and 3299 in months before delisting. 3299 is a small TPEx stock and it is unverified that it ever ranked in the top 200 by market cap. The check could fail on correct data, and acceptance via the watchlist is not stated.
* **Rationale & Recommendation**: Require "in the collection set and priced to the last trading day" for all three, and "in the universe" only where the stock ranked. Alternatively verify 3299's rank in the Phase 1 live gate and add it to the watchlist with a reason.

### N10. `status_events` from `chtm` has no defined `end_date` - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 193, 261
* **Discrepancy Description**: `chtm` is a full state list per day. The design turns it into an event on the first day seen with `announce_date` null. Universe rule 3 and the tradability mask need a window, but `end_date` derivation and the handling of states already present on 2015-03-02 are not defined.
* **Rationale & Recommendation**: Keep `chtm` as a per-day state table, which matches the source, or define the end-date derivation in one sentence.

## Earlier Findings: Status

**Still stand (unchanged or only restated):**
- Append-only clean layer and `v<N>` machinery (111, 136-139, 252, 318-322). Line 252 still admits 2026 history is not first-reported before 2026.
- Twelve `snapshot_<source>` clean tables with no consumer (164, 203, 253). D9 reaffirmed collection, but "raw only, clean table on demand" was never addressed.
- Ownership concentration in the Lead and Agent A (270-285).
- Altitude drift (17, 82-89, 166, 236, 240-252, 259-264). It has grown: resolved spikes S1-S4 and S7-S9 now carry sample dates and row counts under "Open Questions", and the adjusted-price paragraph (236) is longer.
- Raw-cache Parquet shards with a crash-loss window (249).
- Stored point-in-time adjusted returns rejected only for levels (D3, 236, 316-318).
- Snapshot capture depends on a human and on Phase 0 (253, 295-296, 355-361). The `backup_dir` choice is now an explicit author decision (100), but the risk remains.
- Stop-and-report on any `drift` (240-241). It is now an explicit author decision. The narrow proposal (calendar disagreement is not `drift`) is unaddressed; see N2 and N6.
- FinMind quota at 100% with no headroom (177-179); see N8.
- Nits: hand-rolled limiter with no stated package check (334); calendar third cross-check, where the second source is now stated as derived and `exchange_calendars` is unaddressed (96, 158); `market_cap` stored although derived (191, 227); decisions recorded three times (45-52, 106-116, 308-334); "zero-decision standard" undefined (17, 355); critical-path text on `chtm` (179 versus 261); "four timings" against more than four rules (213); critical path serialises the universe pass before FinMind (178-179, 285, 363); no identical-value dedupe or re-pull schedule (252, 299).

**Partly resolved:**
- Ex-date artefact (213, 222, 230, 232). Line 230 now separates features from tradability masks, and line 232 records the artefact in the data dictionary. Still open: no `is_ex_date_artifact` flag, no owner for masking in the feature layer, and no spike for a pre-ex-date source. S2 showed `TWT84U` rows are published before the open, so the reference price may be known earlier than the rule assumes.
- "No official feed carries splits or par-value changes" (87, 236). The 0050 split is evidenced from prices and a manual YAML path exists, but the TPEx pages `/zh-tw/announce/market/change/reference.html` and `/reduction.html` and any TWSE equivalent remain unprobed. Soften the wording to "none found in four endpoints".
- Invented thresholds (71, 76). Line 67 now says the author can change them after the first sample, but "calibrate after first year" is not stated for the 8% and 2% to 40% values.
- Missing context for fresh readers. The References and terms section and the Problem section close the earlier gaps.

**Resolved:** none fully. The items the author answered (approval-document altitude, D7, D8, check 1 reference, snapshot scope) are decisions, not fixes.

## Reuse Check
No code exists, so there is nothing to reuse yet. The Lead still needs to record that `filelock`, `pyrate-limiter` and `exchange_calendars` were checked before the custom limiter and calendar are accepted.
