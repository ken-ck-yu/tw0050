# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-299`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Notes: the reviewers found the persona files under underscore names (`zoom_out.md`, `inventive_catalyst.md`). Both read the target and all four reading-list files. Severity: 0 Blocker, 11 Major, 8 Nit (after deduplication). The inventive-catalyst findings are advisory.

## Prioritized Findings (Blockers -> Major -> Nits)

### Adjusted prices cannot be point-in-time as a stored fact table - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** `prices_adjusted` primary key (~line 205), source policy (~105), `available_at` table (~117-132), Agent B scope (~242), acceptance checks 3 and 6
* **Discrepancy Description**: A 2016 adjusted value depends on every corporate action up to 2026, but each row carries one `available_at`. The design says factors become visible the next trading day (~126). `prices_raw` for the ex-date is available at 18:00 the same day and is already ex-adjusted. A consumer joining on `available_at` therefore gets a mis-scaled return on the ex-date or a one-day-late adjustment. No computed check covers this. Check 3 compares to raw plus events, and check 6 only tests `available_at >= event_date`.
* **Rationale & Recommendation**: Persist raw prices and a `corporate_actions` factor table, each with its own `available_at`. Expose adjusted prices as an as-of view (for example `adjusted_as_of(t)`) that applies only factors with `available_at <= t`. Optionally keep one fully adjusted snapshot, labelled return-only and not joinable on `available_at`. Alternatively define the adjusted table's `available_at` as the max of price and event availability. State the choice and add a computed test. Document the holiday roll-forward.

### Price source decision rests on an underived request count - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** Alternatives A and C (~165-175), "quota is the bottleneck" claim (~168-169), source policy (~99-111, 139), validation check 4 (~261)
* **Discrepancy Description**: Official-primary needs about 5,600 requests and about 8 hours, with undocumented endpoints and HTML sign parsing. Alternative A is rejected as "about 7.5 h at the quota" with no derivation. FinMind `TaiwanStockPrice` is queried per `data_id` over a date range. A collection set of about 450 stocks (or about 2,000 for the full universe) would need far fewer requests, roughly under 1 to 3.5 hours. The 500-point sample cross-check cannot reveal systematic or rare parse errors. This point is not in the open questions.
* **Rationale & Recommendation**: Show the actual FinMind request count and fix the lines 168-169 claim. Consider a full-set cross-check. Pull only FinMind close and volume for the collection set into a side table, and diff every row against official closes. Disagreements are reported, with no conflict-resolution rule needed. Official stays primary.

### Survivorship rests on unprobed inputs; open questions are really spikes - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** open questions (~53-64, 62), universe (~145-147, 206), `TaiwanStockShareholding` (~60, 106)
* **Discrepancy Description**: The design commits to a 200-member point-in-time universe with a 99% coverage goal. Its two key inputs are unresolved. These are delisted-name price coverage and the history of shares issued for TWSE market cap.
* **Rationale & Recommendation**: Make these a gating spike before agents B to E fan out. Name a fallback, for example a degraded universe with documented survivorship bias. Convert pre-implementation questions into a "Spikes before build" list with owner and exit criteria.

### Upsert on year-partitioned Parquet has no named mechanism; key inconsistencies - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** idempotence (~141-143), primary keys (~206-213)
* **Discrepancy Description**: "Upsert on primary key" over year-partitioned Parquet means partition rewrites, with no stated safe method. `prices_adjusted` has no `market` in its key. `status_events` uses `announce_date` while the common columns say `event_date`. The rollback story ("rebuilt from `data/raw/`") and the human gate on overwrites both depend on the mechanism.
* **Rationale & Recommendation**: Choose and name one mechanism. Options are append-only run files deduped at read time through a DuckDB view, or an atomic partition rewrite from raw. Reconcile the keys and the column names.

### Failure handling can false-trip; open question 1 duplicates a decision - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** rate limiting and failure handling (~137-138), client `base.py` (~235), open question (~53)
* **Discrepancy Description**: "Good only if `stat` is OK" plus "3 consecutive bad responses stop the host" would treat legitimate empty answers (holidays, typhoon days, event-less windows such as Lunar New Year) as drift and halt a long run. The response to genuine drift ("stop, no fallback") is a report only. Open question 1 asks what happens on an endpoint change, which lines 137-138 already answer. A single endpoint change would block universe construction and everything after it. Spacing is fixed at 5 s although throttling behaviour is unknown (~64).
* **Rationale & Recommendation**: Classify responses as `ok`, `valid_empty` (checked against the trading calendar), `transient` (retry) and `drift` (counts toward the breaker). Use a half-open breaker that probes after a cooldown. On drift, mark the dataset stale and quarantine the raw response. Decide whether a loudly flagged `degraded` FinMind fallback is allowed. Remove or reconcile the open question. Consider adaptive spacing.

### Raw price fetch ownership is circular across agents A and B - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** dependency order (~161), module table (~149-157), ingest split (~241-242)
* **Discrepancy Description**: A needs prices to build the universe. B owns `prices_raw` and needs A's stock list. A owns `market_cap`, whose TPEx half comes from B's daily file. The 8-hour fetch is serialised across agents, and nobody owns triggering it.
* **Rationale & Recommendation**: Make `fetch` a separate stage that owns only raw-cache acquisition of the shared daily files (`MI_INDEX`, TPEx `otc`, `exDailyQ`, `TWT49U`, `TWTAUU`). A and B become pure parsers over `data/raw/` and can be tested on fixtures. Check this against plan section 6.2, which says the lead writes no ingestion code. Assign the stage accordingly.

### Snapshot-only sources have no collector, though history is irrecoverable - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** non-goals (~48), scope (~47), problem (~26), ingest list (~237-246), `docs/OFFICIAL_SOURCES.md` lines 30-33
* **Discrepancy Description**: `OFFICIAL_SOURCES.md` says snapshot collection should start as soon as ingestion is approved. The design has no module, scheduler or schedule for `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap04_L`, `t187ap09_L`, `t187ap12_L` and similar. Each day of delay loses history permanently. `fetched_at` exists in raw but never reaches the clean tables.
* **Rationale & Recommendation**: Add a small stateless daily fetch job (cron or systemd timer) using the same client and cache, and start it before the heavy build. Add `first_seen_at` to snapshot-derived tables without changing `available_at`. Add a gap-count metric. This also weakens the "two timing regimes" objection at ~186.

### 08:30 next-day rule: pre-announced events and tradability - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** `available_at` rules (~117-132, 126-127, 132), alternative (~177), goal (~32)
* **Discrepancy Description**: Applying the next-trading-day rule to a pre-announced ex-date discards information, since `TaiwanStockDividend` `AnnouncementDate` is weeks earlier. For disposition and attention lists, a late `available_at` lets a model trade a name whose restriction was already public. That is the "untradable prices" failure from line 23. The design's reason for rejecting per-dataset rules (a wrong guess leaks future data) applies equally to a rule that is too late.
* **Rationale & Recommendation**: State whether the lateness is intended. Consider keeping `available_at` as the conservative value and adding `available_at_earliest` from a config-driven rule table, to support sensitivity analysis. Add a check comparing empirical publication evidence (`fetched_at`) to the rule table.

### One ingest module per dataset instead of a table-driven ingestor - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** modules and ownership (~154-155, 239-246)
* **Discrepancy Description**: About 20 per-dataset modules are planned before the shared client and cache exist. Most FinMind datasets share one shape: fetch by `data_id` and date range, add `available_at`, write a partition, update state.
* **Rationale & Recommendation**: Build one generic FinMind ingestor driven by a per-dataset spec (name, keys, `available_at` rule, unit). Keep bespoke modules for the official TWSE/TPEx parsers, `prices_adjusted`, the universe and the status lists. This removes duplicated idempotence and state code.

### Row-level provenance columns inflate every table - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** common columns (~87, 115, 246)
* **Discrepancy Description**: `raw_ref` (path and row), `source`, `source_dataset` and `fetched_at` on every row add storage and force parsers to carry row-level lineage.
* **Rationale & Recommendation**: Keep `event_date` and `available_at` on every table, as the plan requires. Record the rest once per partition in a manifest under `data/state/`. Drop `raw_ref` unless a concrete debugging use is named.

### Bespoke client stack without considering standard libraries - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** rate limiting and clients (~134-139, 232-235)
* **Discrepancy Description**: The need is real (HTTP 200 with an HTML error page, IP-block risk). The design never considers existing packages for the limiter, backoff or raw caching, and does not say whether the `FinMind` pip package from plan section 3 is used. About 5,600 one-row-per-request Parquet cache writes would fragment the data.
* **Rationale & Recommendation**: Say which libraries are used (for example `requests` with `urllib3.Retry`, `pyrate-limiter`, `requests-cache`), or why not. State FinMind package versus raw REST. Batch or shard the raw cache storage.

### US price availability rule assumes a close timestamp - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** line ~128
* **Discrepancy Description**: "US close converted to Taipei time plus 30 minutes" needs a timestamp, but `USStockPrice` is a date-only daily series. DST shifts twice a year make this a likely bug site.
* **Rationale & Recommendation**: Use a fixed rule on the US trading date with an exchange calendar and DST handling. Name the calendar source.

### Derived tables and several datasets lack `available_at` rules - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `available_at` table (~119-130), goal (~32)
* **Discrepancy Description**: `universe_membership`, `market_cap`, `benchmark_index`, `valuation_ratios`, `shareholding`, fx, rates and futures have no rule. A membership row dated month-end 00:00 would leak the closing data it was built from.
* **Rationale & Recommendation**: Enforce `available_at = max(available_at of inputs)` for derived tables through a shared tested helper. Add rows for the remaining source datasets.

### TWSE market cap has a single source - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** source policy (~106), open questions (~55, 60)
* **Discrepancy Description**: No cross-check exists for TWSE shares issued.
* **Rationale & Recommendation**: Roll the `t187ap03_L` share snapshot using the collected `TWT49U` and `TWTAUU` events and compare to FinMind `NumberOfSharesIssued` with a coarse tolerance. Probe for a TWSE foreign-holding report. Expect false mismatches from unmodelled events.

### Adjusted-price validation sample skews to survivors - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** goal (~35), source policy (~105)
* **Discrepancy Description**: A 20-stock Yahoo `Adj Close` sample will mostly be survivors, where distortion is smallest. Yahoo coverage of delisted names is weak.
* **Rationale & Recommendation**: Stratify the sample to include capital reductions, large stock dividends and delisted names. Add an internal `reference_price` identity check from `TWT49U` and `TWTAUU` on every event. Report which strata could not be checked.

### Two cheap computed checks are missing - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** verification plan (~192-193, 259-266)
* **Discrepancy Description**: The two likeliest silent errors have no computed check.
* **Rationale & Recommendation**: Add a check that `MI_INDEX` sign parsing matches close minus previous close on all rows. Add a count assertion of 200 members per month.

### Target Files section reads as code layout - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines ~215-286 (items 3 and 4 helper modules)
* **Discrepancy Description**: File names such as `timeutil.py`, `parsing.py`, `calendar.py`, `schema.py` and `paths.py` may be taken as binding.
* **Rationale & Recommendation**: Collapse to package level. Also consider dropping `pandas` (line ~220) if DuckDB and `pyarrow` suffice.

### Alternative labels skip B - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** lines ~165-187
* **Discrepancy Description**: Alternatives are labelled A and C with no B, and the rejection reasoning is short.
* **Rationale & Recommendation**: Label the chosen design B consistently. Confirm the `docs/DECISIONS.md` entry is written after approval (item 12 in the design).
