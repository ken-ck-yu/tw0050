# Goldfish Review Report (intermediate zoom-out)

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-388`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Context: the repo has no code, so the design is greenfield and there is nothing to reuse. The reviewer could not diff the file. It found no mitigation of the earlier findings in `/home/ken/tw0050/zoom_out_report.md`, and the line references in that report still match. It treats the document as unchanged since that report.

## Status of earlier findings

**Still stand:**
- All 13 Majors and the nits, except as noted below.
- Wall-clock time: the critical path is about 8 h plus 10.5 h, so roughly 18-19 h, not about 12 h (lines 168, 278, 320, 384).
- Also unchanged: Phase 2 breadth, the versioned clean store, client-stack weight, TWT84U and chtm cost, detail altitude in lines 322-384, `stock_id` identity, backup of the raw cache, and lane isolation.

**Needs correction or nuance:**
- The nit that "2,843 conflicts with 2,780" should be retracted. The design counts from 2015-03 and the research counts from 2015-06.
- First-reported-wins is narrower than first reported. The first full fetch happens on or after 2026-11-13, after FinMind's 2026-09-01, 10-22 and 11-04 corrections, so "first-fetched" is already the corrected value for the initial collection. The risk is a later re-fetch after a source fix. A revisions view plus a manual "promote" step would be enough.
- The Phase 2 breadth finding conflicts with plan section 6.6, which assigns agents C, D and E to fundamentals, flows and macro. Present it as an explicit author choice, not a silent descope.
- Check 4 scope: see "Check 1 partly circular" below for a caveat.

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers.

### MI_QFIIS coverage gap is probably an artefact - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 79, 108, 280; OFFICIAL_SOURCES line 44
* **Discrepancy Description**: The design says "915 rows against 951 `MI_INDEX` rows on comparable dates". The dates are not comparable. 915 is `MI_QFIIS` on 2015-06-01 and 951 is `MI_INDEX` on 2016-06-01 (twse_findings.md lines 71 and 92). `MI_QFIIS` had 1,141 rows on 2022-06-01. `MI_INDEX` also includes ETFs and DRs, which the universe excludes.
* **Rationale & Recommendation**: The 36-row gap is plausibly one year of listing growth plus ETF/DR rows. Restate the claim as unmeasured. Have S1 compare the same date with the same common-stock filter. Drop the fallback tier (carry forward up to 10 days, then ineligible) until S1 shows a real gap. This also lowers the "Medium" likelihood at line 280.

### Check 3 is circular and contradicts the Goal - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 45, 68, 149, 222
* **Discrepancy Description**: The Goal says adjusted prices "match an independent source". Check 3 compares the adjusted return with the return implied by raw prices and the official reference price. The adjustment factor is `reference_price / prev_close` from the same official events, so the check only tests arithmetic. Yahoo, the only independent source, is explicitly not a pass condition. FinMind `TaiwanStockDividendResult` is already named as the cross-check at line 149 but check 3 does not use it.
* **Rationale & Recommendation**: Make agreement between official reference prices and FinMind `DividendResult` (and `TaiwanStockPrice` day-over-day) the pass condition. Rewrite the Goal to match.

### Check 1 partly circular; qualifies the earlier check-4 finding - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 66, 69, 109
* **Discrepancy Description**: "Listed days" and "last trading day" are derived from the same daily files that check 1 audits. A day missing from a file looks the same as a suspension. The only independent per-stock coverage reference is the FinMind `TaiwanStockPrice` pull over the collection set. The earlier recommendation to fetch FinMind prices only for sampled stocks would remove it.
* **Rationale & Recommendation**: Decide explicitly. Option (a): keep the full collection-set FinMind price pull and state in check 1 that it supplies the independent listed-day reference, as a per-stock-month count comparison and not only 500 closes. Option (b): sample only, and accept that check 1 cannot detect a missing row inside a stock's listing span.

### Snapshot job is speculative and sequenced late - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 62-66, 238, 333-337, 341
* **Discrepancy Description**:
  - Scope: the job collects about 12 latest-only sources (`TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap04_L`, `t187ap09_L`, `t187ap12_L`, `t187ap24_L` to `t187ap27_L`, TPEx `warning`, `sprc`). Only `TWT85U` (the full-delivery gap), `sprc` and `warning` have a stated consumer. The rest have no table schema, no `available_at` row and no check or hypothesis that needs them. This adds daily manual work for the author, and a missed day is permanent.
  - Sequencing: the Phase 0 gate requires spikes S1-S6 and the author prerequisites before Phase 1 begins, yet Phase 1 says snapshots start first because every lost day is permanent. S5 (revenue unit) belongs to Agent C's phase. S6 (FinMind reference tables) belongs to Agent A's `stock_info` and `delistings` modules.
* **Rationale & Recommendation**: Snapshot only the sources that close a named gap, with a one-sentence justification for each. Start the rest when a consumer exists. Split a snapshot-only mini-gate (clients, limiter, raw cache, `snapshots.py`) that starts the daily job at once. Move S5 and S6 into the owning agent's phase.

### Benchmark (0050) is underspecified - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 146, 153, 183; plan sections 1 and 3
* **Discrepancy Description**: The plan's success measure is buy-and-hold 0050. The design's `benchmark_index` holds index total returns (`TAIEX_TR`, `TAIWAN50_TR`, `TPEX_TR`). The Taiwan 50 index is not the 0050 ETF (fees, tracking). 0050 is excluded from the universe and collection set by the `^[1-9][0-9]{3}$` rule, though it remains in the all-stock daily files. The design never states that 0050 is the benchmark of record or how its adjusted series is built. The reviewer recalls a 0050 share split in mid-2025 and does not know whether TWT49U, TWTAUU or `revivt` carry it.
* **Rationale & Recommendation**: State that 0050 comes from `prices_raw` plus `corporate_actions`, flag it as a special collection-set member, and add it to the S3 or S4 spike with a 0050 corporate-action test.

### Wall-clock estimate still wrong - Severity: Major (carried over)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 168, 278, 320, 384
* **Discrepancy Description**: The critical path is about 8 h plus 10.5 h, or 18-19 h, not about 12 h.
* **Rationale & Recommendation**: Correct the figure before approval.

### Design remains too large and too detailed for pre-approval - Severity: Major (carried over)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** whole file, especially lines 322-384
* **Discrepancy Description**: Nothing has been trimmed since the earlier report. The earlier Majors on Phase 2 breadth, the versioned clean store, client-stack weight, TWT84U and chtm cost, `stock_id` identity, raw-cache backup, lane isolation and first-reported-wins still stand. See the nuances above.
* **Rationale & Recommendation**: Phase 2 breadth and lane isolation need an explicit author choice, because plan 6.6 already assigns the agent split.

### TPEx `otc` schema-era boundaries unknown - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 155, 163, 230; OFFICIAL_SOURCES line 48
* **Discrepancy Description**: The research sampled one date per year. It found a label change on 2025-01-10 and an earlier variant "before 2020". The "2020" boundary has no evidence in the research files. The registry stops on the first unregistered field list, so an unattended 12-hour run can halt midway.
* **Rationale & Recommendation**: Add a cheap bisect for era boundaries (or a field-list pre-scan) to S3 so the registry is complete before the long run.

### Universe classification depends on ambiguous `TaiwanStockInfo` - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 245
* **Discrepancy Description**: The regex already excludes ETFs, preferreds and six-digit warrants and ETNs, and the `-DR` name rule covers depositary receipts. The `TaiwanStockInfo` category test is redundant unless S4 proves otherwise, and its date semantics are unresolved (S6).
* **Rationale & Recommendation**: Make the regex plus name rule the default. Add the Info-based exclusion only if S4 shows leaks.

### "Exactly 200" conflicts with allowed shortfall - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 44, 73, 343
* **Discrepancy Description**: The Goal, check 8 and the Phase 1 gate say "exactly 200" while also allowing a shortfall month.
* **Rationale & Recommendation**: Reword to "200, or all that pass, with the shortfall reported", and state whether a shortfall month fails the gate.

### Agent F "read-only on data" but writes a `qa` cache namespace - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 137, 328, 353
* **Discrepancy Description**: The author prerequisites cover only `src/twdata/validate/**`, `tests/validate/**` and two docs.
* **Rationale & Recommendation**: Name the `qa` cache path as allowed, or route F's fetches through the Lead.

### "14 per-stock datasets" not enumerated - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines 166, 188-191, 320
* **Discrepancy Description**: The reviewer counts 14 only by including `TaiwanDailyShortSaleBalances` and three separate financial statements. The schema table has no row or `available_at` entry for short-sale balances. The footprint (line 320) says about 17,000 responses, but the budget implies about 20,000.
* **Rationale & Recommendation**: List the 14 datasets once and reconcile the counts.

### `dividend_announcements` trusts FinMind `AnnouncementDate` - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line 209; finmind_findings.md Q6
* **Discrepancy Description**: FinMind's docs do not say whose announcement it is. Impact is limited because adjusted prices use exchange ex-dates.
* **Rationale & Recommendation**: Add a spike item or a "semantics unverified" note in the data dictionary.

## Net assessment

The design is sound on the root problem. The earlier verdict, "too large and too detailed for pre-approval", is unchanged. The highest-value changes before approval are:
- the corrected wall-clock figure;
- the two circular checks (check 3 and check 1);
- snapshot scope and sequencing;
- the 0050 benchmark;
- author decisions on Phase 2 breadth and lane isolation.

## Severity breakdown

Blockers 0, Majors 7 (5 new, 2 carried over), Nits 6.
