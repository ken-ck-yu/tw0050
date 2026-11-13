# Goldfish Review Report (Intermediate Zoom-Out)

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-299`)

Scope: additions and mitigations since `/home/ken/tw0050/zoom_out_report.md`, and whether earlier findings still stand.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |

Context sufficiency passes. Severity totals: 0 Blocker, 11 Major, 10 Nit. Of the 19 earlier findings, 12 are unchanged, 5 are partly mitigated, 1 is largely resolved (downgraded to a Nit) and half of 1 Nit is withdrawn.

## What changed since the earlier report

* Decisions are recorded at lines 72-73 and 177-181: official sources are primary for prices and corporate actions, and there is a single next-trading-day 08:30 rule.
* Line 126 admits adjustment factors are not visible on their own ex-date.
* Line 111 adds the `MI_INDEX` finding, including the total-return table.
* Line 139 adds a request-volume estimate (about 5,600 requests, about 8 hours).
* Lines 26 and 48 state that snapshot-only sources have no earlier history.
* Lines 53-64 expand the open questions.
* Modules, primary keys, dependency order, failure handling and common columns are unchanged.

## Prioritized Findings (Blockers -> Major -> Nits)

### Rejection of Alternative A contradicted by the design's own numbers - Severity: Major (new; sharpens the earlier price-source finding)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 72, 139, 165-169`
* **Discrepancy Description**: Line 139 puts official-primary at about 8 hours because of the 5-second spacing. Line 168 rejects FinMind-primary as "about 7.5 hours at the limit" and says the quota is the bottleneck. The two options cost about the same, and official-primary needs about 5,600 requests against about 4,500 for FinMind. Neither count is derived.
* **Rationale & Recommendation**: The price source is the largest decision in the design, and its stated reason does not hold. `TaiwanStockPrice` takes a date range per `data_id`, so the count is stocks times date chunks, not days. Derive the FinMind count, then fix the rationale or reopen the decision. A sounder reason is that official data is independent and authoritative and the full-market daily file also drives the universe.

### Schema validation calibrated on one sample date per market but must hold across 11 years - Severity: Major (new)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 111, 137-138, 266`
* **Discrepancy Description**: `MI_INDEX` was verified on one saved 2015-06-01 response and TPEx `otc` on one date (OFFICIAL_SOURCES.md lines 14-15). The design makes a schema match a hard stop, with a circuit breaker after 3 bad responses. Layouts, columns and table titles change over a decade.
* **Rationale & Recommendation**: Legitimate historical format changes would halt the 8-hour run, or the check would be loosened until it is useless. Add a spike that samples one date per year for both hosts and records the field-list variants. Have the validator accept a versioned set of known schemas per date range. Do this before any bulk run.

### Adjusted prices cannot be point-in-time as a stored table - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 126, 203-206`
* **Discrepancy Description**: Line 126 acknowledges the lag but does not fix it. There is no as-of view and no computed test. `prices_adjusted` still carries one `available_at`.
* **Rationale & Recommendation**: Provide an as-of derivation or store raw prices plus factors with their own `available_at`, and add a computed test.

### Survivorship rests on unprobed inputs - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 60, 62, 129`
* **Discrepancy Description**: These remain open questions, with no gating spike or fallback. `TaiwanStockInfo` is a snapshot, so classifying delisted names is also unsolved.
* **Rationale & Recommendation**: Add a "Spikes before build" list covering delisted-name price coverage, TWSE shares-issued history and the unlocated endpoints.

### Upsert on partitioned Parquet has no named mechanism, and keys are inconsistent - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 141-143, 203-213`
* **Discrepancy Description**: Unchanged. `prices_adjusted` has no `market`, and `status_events` uses `announce_date`.
* **Rationale & Recommendation**: Name the upsert mechanism and reconcile the primary keys.

### Failure handling can false-trip, and open question 1 duplicates a decision - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 53, 137-138`
* **Discrepancy Description**: Empty or holiday responses are not classified, and line 53 is still open. It is compounded by the schema finding above.
* **Rationale & Recommendation**: Classify empty and holiday responses as expected outcomes, and close open question 1 against the recorded decision.

### Raw price fetch ownership circular between A and B - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 161, 241-242`
* **Discrepancy Description**: Unchanged.
* **Rationale & Recommendation**: Add a `fetch` stage and break the A/B dependency cycle.

### Snapshot-only sources have no collector - Severity: Major (earlier finding, partly mitigated)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 26, 48`
* **Discrepancy Description**: The loss of history is now stated honestly. There is still no collector module, no schedule and no `first_seen_at`. Line 48 says "start collecting at approval" with nothing that does it.
* **Rationale & Recommendation**: Add a snapshot collector with a schedule and `first_seen_at`.

### One ingest module per dataset instead of a table-driven ingestor - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 237, 242-245`
* **Discrepancy Description**: Unchanged.
* **Rationale & Recommendation**: Use a table-driven ingestor with per-dataset configuration.

### Row-level provenance columns inflate every table - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `line 115`
* **Discrepancy Description**: Unchanged.
* **Rationale & Recommendation**: Move provenance to partition or manifest level.

### Bespoke client stack without considering standard libraries - Severity: Major (earlier finding, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 220, 232-235`
* **Discrepancy Description**: Line 220 lists `requests` but no limiter or retry library, and it does not say whether the FinMind package or raw REST is used.
* **Rationale & Recommendation**: Evaluate standard retry and rate-limit libraries and state the choice.

### 08:30 rule on pre-announced events and tradability - Severity: Nit (earlier Major, largely resolved by author decision)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 54, 132, 177-181`
* **Discrepancy Description**: The decision and trade-off are recorded. Only the status-list question (line 54) remains open, and the design flags it.
* **Rationale & Recommendation**: The optional `available_at_earliest` suggestion is no longer needed. Close line 54 when the status list is probed.

### Goal 3 and the plan disagree on what "exactly 200" means - Severity: Nit (new)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 34, 147`
* **Discrepancy Description**: The goal says exactly 200 plus watchlist names. In 2015 the NT$20M floor or missing shares-issued history could leave fewer than 200 eligible names.
* **Rationale & Recommendation**: Define the check as exactly 200 non-watchlist members, count watchlist rows separately, and state the behaviour if fewer than 200 pass the floor.

### 8-hour estimate ignores the per-host design - Severity: Nit (new)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 137, 139`
* **Discrepancy Description**: The limiter is per host, so TWSE and TPEx could run concurrently (about 4 hours). The estimate also omits corporate-action, status-list and snapshot requests.
* **Rationale & Recommendation**: State the concurrency assumption and include the omitted requests.

### US price availability rule assumes a close timestamp - Severity: Nit (earlier, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `line 128`
* **Discrepancy Description**: Unchanged.
* **Rationale & Recommendation**: Define the rule without relying on a close timestamp.

### Derived tables and several datasets lack `available_at` rules - Severity: Nit (earlier, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 119-130`
* **Discrepancy Description**: `universe_membership`, `market_cap`, `benchmark_index`, fx, rates, futures, valuation and shareholding still have no row.
* **Rationale & Recommendation**: Add a rule for each.

### TWSE market cap has a single source - Severity: Nit (earlier, acknowledged not resolved)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 55, 60, 106`
* **Discrepancy Description**: The design now says so openly.
* **Rationale & Recommendation**: Keep as an accepted risk.

### Adjusted-price validation sample skews to survivors - Severity: Nit (earlier, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 35, 106`
* **Discrepancy Description**: Unchanged.
* **Rationale & Recommendation**: Include delisted names in the sample.

### `MI_INDEX` sign-versus-close-change check missing - Severity: Nit (earlier, half withdrawn)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `line 266, 294`
* **Discrepancy Description**: The 200-member count is already plan check 8, covered by line 294. The sign-versus-close-change check is still missing. Line 266 only unit-tests the parser.
* **Rationale & Recommendation**: Add the computed check.

### Target Files section reads as code layout - Severity: Nit (earlier, still stands)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 220, 227-230`
* **Discrepancy Description**: Unchanged, including the `pandas` dependency at line 220.
* **Rationale & Recommendation**: Describe ownership and outputs rather than code layout.

### Alternative labels skip B - Severity: Nit (earlier, still stands, minor)
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `lines 72, 165-187`
* **Discrepancy Description**: Line 72 calls the chosen design "option B", but the alternatives are still labelled A and C.
* **Rationale & Recommendation**: Label the alternatives consistently.

## Recommended order before approval

1. Fix the Alternative A rationale.
2. Add a "Spikes before build" list: cross-era schema probe, delisted-name price coverage, TWSE shares-issued history, unlocated endpoints.
3. Name the upsert mechanism and reconcile the keys.
4. Add a `fetch` stage and a snapshot collector, and break the A/B dependency cycle.

Everything else can be handled during implementation.
