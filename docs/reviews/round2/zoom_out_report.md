# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 1-388`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Severity totals after deduplication: 0 Blocker, 14 Major, 4 Nit (corrected by the lead: the file lists 14 Major entries and 5 Nit entries, and two of the Nit entries are the same item). Two reviewer findings (the wall-clock arithmetic) were merged into one. Line numbers are as the reviewers reported them.

Overall: no blockers. The design is sound on the root problem, but it is too large and too detailed for a pre-approval design. There are also several places where one policy is applied to data that needs two.

## Prioritized Findings (Blockers -> Major -> Nits)

### Wall-clock estimate contradicts the dependency order - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst`
* **Affected Scope:** `Lines 163-168, 266-268, 278, 320, 384`
* **Discrepancy Description**: The doc says unattended wall-clock is about 12 h. The TWSE request table alone is about 11.9 h (8,529 requests, host-serial). FinMind work starts only after the universe exists, so the critical path is about 8 h plus 10.5 h, or about 18-19 h. During the 8 h official pass, about 4,800 free FinMind requests (600 per hour) go unused.
* **Rationale & Recommendation**: Correct every occurrence, for example "12 h per host, about 18 h critical path". Optionally make the collection set grow incrementally as month-end builds land, so a FinMind queue drains during the official pass. If so, define the queue state and what A's gate waits on.

### Phase 2 and P1 breadth built before any hypothesis needs it - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 27, 146-153, 176-195, 345-347 (Phase 2)`
* **Discrepancy Description**: About 14 FinMind datasets are fully scoped, tabled and tested across several agents. These include futures, rates, FX, securities lending, day trading, shareholding, margin and `us_prices`. The plan's seed hypotheses (plan section 10.5) need only monthly revenue, flows, US prices, margin and day-trading share. Line 27 says P2 is schema-only, but line 347 builds `fx`, `rates` and `futures` modules.
* **Rationale & Recommendation**: Build P0 plus the seed-hypothesis datasets first. Keep `fx`, `rates`, `futures` and `securities_lending` as schema and `available_at` entries only, until a hypothesis card needs them. Resolve the line 27 versus 347 inconsistency.

### Append-only versioned clean store is heavy for what it protects - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 218, 234-237, 303-306`
* **Discrepancy Description**: Raw is already immutable, checksummed and replayable, so the clean layer is derivable. Versioning clean as well (`v<N>/year=/run-*.parquet`, pointer file, `v<N+1>` convention, deletion needs author approval) doubles the protection. First-reported also only means something for data collected from 2026 on (line 218).
* **Rationale & Recommendation**: Make clean tables rebuildable and disposable from raw, written atomically via a staging directory. Keep append-only and first-reported only for tables where restatement matters (`monthly_revenue`, `dividends`, institutional flows, `us_prices.adj_close`).

### First-reported-wins selects the wrong value for sources that correct in place - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Lines 237, 282, 303-306`
* **Discrepancy Description**: The one rule "first-reported row per key (earliest `fetched_at`)" is applied to all data. FinMind corrects history in place (the `TaiwanStockPrice` backfill on 2026-11-04, the TPEx margin column swap on 2026-09-01, the ETF dividend duplicates on 2026-10-22). For pre-2026 rows, first-reported means first-fetched, so it can select the buggy value. The doc never says which view checks 3 and 4 or downstream consumers use per dataset.
* **Rationale & Recommendation**: Add a per-dataset `restatement_class`. Use `economic` (keep first) or `source_error` (prefer latest). Expose two named views, `as_first_seen` and `as_latest_corrected`. Record explicitly when a parser fix makes `v<N+1>` supersede `v<N>`. This interacts with the previous finding, so settle both together.

### Detailed Implementation Plan is at file and test-case altitude - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 322-384 (also 228-230, 234, 310)`
* **Discrepancy Description**: The section lists module filenames (`check_01_coverage` to `check_08_universe`, line 353), ruff rules and line length (335), the pip freeze procedure, parse test vectors such as `113/02/29` (367), exit codes (359), the 300 KB fixture cap (363) and the `tradingcal.py` naming rationale. Parameter detail also appears elsewhere: retry waits of 5, 10, 20, 40 and 80 s, the 500-response or 64 MB shard size, breaker half-open mechanics, and "about 60 lines, `fcntl`".
* **Rationale & Recommendation**: Keep phase gates, ownership and acceptance criteria in the design. Move file lists, test vectors and tooling to the Lead's Phase 0 task notes or to the code. Move parameter defaults to `config/settings.yaml`. This detail will drift and invites bikeshedding.

### Bespoke client stack is a framework to build before any data flows - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 120-124, 224-236, 310`
* **Discrepancy Description**: The design combines a raw cache and manifest, a file-lock limiter, a circuit breaker, a response classifier and a schema-era registry. Line 310's claim that no standard package fits is unsubstantiated, since `filelock` plus a timestamp file or `pyrate-limiter` would do. A half-open breaker with a 15-minute cooldown is not needed for a manually launched, attended run that already stops on any 4xx or failed probe. The shard, manifest, rename-on-write and verify design is more complex than per-response files keyed by sha256.
* **Rationale & Recommendation**: Use an existing lock or limiter library. Replace the breaker with stop-and-report. Reduce response classes to ok, transient and drift. Consider per-response gzipped files with an index (about 17,000 small files is acceptable). See the lane-isolation finding for the opposing view on the stop behaviour.

### Fixed per-date, per-dataset fetching at 5 s inflates the gating universe pass - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Lines 157-168, 227, 240-251`
* **Discrepancy Description**: The universe is ranked only at month-ends and needs `shares_issued` and `chtm` restriction flags only on those dates. Yet `MI_QFIIS`, `TWT84U` and `chtm` are fetched daily (about 8.5k of the 14k official requests), which makes the gate about 8 h and host-serial. The 5 s spacing is admitted to be a chosen default, not an observed limit.
* **Rationale & Recommendation**: Split the pass into two lanes. The gating lane has `MI_INDEX` and `otc` daily plus `MI_QFIIS` and `chtm` on about 137 month-ends, so the gate drops to about 4 h. A background lane fetches the remaining days after the gate. Optionally use an adaptive (AIMD) limiter with a hard floor (about 3 s) and a per-hour cap. Cost: sparse shares-issued data until the background lane finishes, and less predictable block risk.

### TWT84U and chtm daily collection costs more than the checks they serve - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 146, 150, 163-165`
* **Discrepancy Description**: `TWT84U` is about 2,843 requests (about 4 h) and serves only check 5 and the `limit_up`/`limit_down` columns. The limits can be computed from the prior close and the rule, which the design already lists as the cross-check. `chtm` serves only the TPEx restriction and suspension proxy. S2 (same-day or next-day row dates) is also still open.
* **Rationale & Recommendation**: Demote `TWT84U` to a sampled cross-check, as `BWIBBU_d` already is. Keep the computed limit as primary, and keep the TPEx `otc` limit columns since they cost nothing extra. Make `chtm` bounded or flag-driven. TWSE host-serial cost falls from about 8,529 to about 5,700 requests (about 8 h).

### Universe depends on one undocumented endpoint with a long fallback chain - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 79, 108, 280`
* **Discrepancy Description**: Ranking by market cap depends on `MI_QFIIS`, with an unmeasured 915 versus 951 row gap. The fallback chain is FinMind `TaiwanStockShareholding`, then 10-day carry-forward, then ineligible. The FinMind cross-check of shares issued over the collection set adds about 450 requests and has no defined mismatch handling.
* **Rationale & Recommendation**: Have spike S1 decide between exactly two outcomes, either accept `MI_QFIIS` or use FinMind plus carry-forward, and build no third path. Define the mismatch rule for the cross-check or drop it.

### Check 4 fetches FinMind prices for the whole collection set - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 69, 146, 152`
* **Discrepancy Description**: Check 4 compares exchange-derived values with their own derivative, as line 69 admits, so it cannot catch exchange-file errors. Fetching `TaiwanStockPrice` for the whole collection set (about 450 requests) is more than the roughly 500 sampled comparisons need. Checks 3 and 5 are the real guards.
* **Rationale & Recommendation**: Keep check 4 because the plan requires it, but fetch FinMind prices only for the sampled stocks.

### One conservative available_at serves both feature-safety and tradability masking - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Line 211, Decision 2 (lines 293-296)`
* **Discrepancy Description**: Next-day 08:30 after `announce_date` is safe for features. For disposition and attention events it is the wrong direction for the universe "not restricted that date" filter and for fill feasibility. The doc admits a restriction can become visible after its first session, and that a future `start_date` does not change this.
* **Rationale & Recommendation**: Keep `available_at` as the feature timestamp. Add a documented contract that masks join on the exchange-declared `start_date`/`end_date` window. Add a check that mask consumers use the effective window and feature consumers do not. Handle retroactive declarations explicitly.

### A drift or breaker stop halts the whole unattended run - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Lines 226-230, 275`
* **Discrepancy Description**: "A failed probe stops the run", "any 4xx stops the run" and exit codes 3 and 4 end a 12 to 19 hour run. One drifted endpoint, such as `chtm` or `TWT84U` on one date, blocks unrelated healthy datasets and hosts.
* **Rationale & Recommendation**: Make each (host, dataset) an independent lane with its own breaker and dead-letter ledger. Park drifted lanes and continue the others. Keep a global stop only for auth failure, IP ban (403) and FinMind 402 or a 4xx burst. Add `retry-quarantine`. Make `status --verify` and check 1 treat a parked lane as a hard coverage gap. Note the tension with the stop-and-report recommendation in the client-stack finding. The author should choose one.

### Irreplaceable snapshots share a deferred backup decision with replaceable bulk data - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Lines 94, 235, 278-279`
* **Discrepancy Description**: Backing up `data/raw/` is treated as one deferred 2.5 GB decision justified by about 12 h of refetching. That cost applies only to replaceable official and FinMind data. Daily snapshots are small, their history cannot be recovered, and the manual runner is a high-likelihood miss.
* **Rationale & Recommendation**: Give `data/raw/snapshots/` a separate second-copy path, such as a Windows-side directory. Leave the bulk raw backup deferred. Any cloud copy touches the "no cloud storage" non-goal and needs author approval. A second path on the same disk does not protect against disk loss.

### Identity is keyed on stock_id alone despite code reuse - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 195, 197`
* **Discrepancy Description**: Line 197 says a code is on one market on any date. `prices_raw` keys on `market`, `stock_id` and `event_date`, while `universe_membership` and `monthly_revenue` omit `market`. `OFFICIAL_SOURCES.md` (line 14) records code reuse. The collection set uses `stock_id` as its primary key, so it cannot distinguish two companies sharing a code in different periods.
* **Rationale & Recommendation**: Carry the ISIN, which `MI_QFIIS` provides, as a stable identity key. Alternatively, state that every table is date-scoped and that the collection set key includes a validity window. The reviewer rated this as a low risk, but it is the one decision that is expensive to reverse later.

### Document hygiene and enforcement wording - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 17-27, 98-111, 105-106, 328-329`
* **Discrepancy Description**: The Overview carries a long glossary of agents, MOPS and ROC terms. The decision log duplicates `docs/DECISIONS.md`. Lead-made architecture decisions (rows 105-106) precede author review. Lines 328-329 ask the author to change `.claude/settings.json` and `qa-goldfish.md` for F's write access, which sits awkwardly with the plan's rule that F has no write access to `src/`.
* **Rationale & Recommendation**: Move the glossary to a short separate section. Keep one decision log and link to the other. State that F's restriction is enforced by path deny rules, not by trust.

### Overstated or unreconciled claims - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 12, 38, 155, 163-166, 289-290`
* **Discrepancy Description**: Line 38 says the TWSE disposition and attention lists reach back to 2015, but only the 2015 and 2024 windows were sampled. The "values did not change" claim for the 2025 TPEx relabel (lines 12, 155) rests on medians only. About 2,843 trading days (lines 163-166) conflicts with about 2,780 in the research docs. Lines 289 and 290 repeat the Option B rationale.
* **Rationale & Recommendation**: Say "verified for sampled windows", reconcile the day count and trim the repeated rationale.

### Check-4 text duplicates Decision rationale - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `Lines 289-290`
* **Discrepancy Description**: This is the same duplicated Option B rationale noted above, listed by the reviewer under two heads.
* **Rationale & Recommendation**: Merged with the previous nit. Trim once.

### Manual snapshot cadence has an untried automation path - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Line 103, line 238`
* **Discrepancy Description**: `docs/DECISIONS.md` rejected cron and systemd because WSL2 sleeps. A Windows-host trigger was not considered, and missed days for latest-only sources are permanent.
* **Rationale & Recommendation**: Consider a Windows Task Scheduler job running `wsl.exe python -m twdata snapshot` with run-as-soon-as-possible after a missed start and wake-to-run. Keep the manual command as the fallback. The author must configure it outside the repo, and the `status` reminder still has to catch silent failures.

### Raw shards of up to 500 responses widen the crash loss window - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `Line 234, line 371`
* **Discrepancy Description**: Writes are atomic per shard, so a crash or sleep loses up to 499 fetched responses (about 40 minutes of rate-limited work). The loss window is implicit.
* **Rationale & Recommendation**: Either state the window, or use a per-response append journal (fsynced line with sha256) compacted into shards. Note that the per-response-file option in the client-stack finding also removes this window.
