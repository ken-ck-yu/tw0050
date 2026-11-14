# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (lines 1-386)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-zoom-out` | completed |
| `egm-inventive-catalyst` | completed |

Totals after deduplication: 0 Blocker, 11 Major, 10 Nit.

Two overlaps were merged. The ex-date artefact was reported by both reviewers. The raw-cache shard design was reported by both, and the Nit-level parts of the inventive-catalyst item (clean-write dedupe, re-pull schedule) are kept separately.

Reviewer caveat: `egm-zoom-out` read only the first 80 lines of `OFFICIAL_SOURCES.md` and did not open the other research and FinMind files. `egm-inventive-catalyst` read all nine context files.

## Prioritized Findings (Blockers -> Major -> Nits)

No Blockers were reported.

### Append-only clean layer is more machinery than the data needs - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `111, 136-139, 252, 318-322`
* **Discrepancy Description**: Append-only `v<N>` clean tables, two views per table and `restatement_class` are built for a one-time backfill. Line 252 admits that "History collected in 2026 is not first-reported before 2026", so `as_first_seen` equals `as_latest_corrected` for almost every table. The immutable raw cache already protects the first-reported value.
* **Rationale & Recommendation**: The design names the lighter option itself (line 322). Make clean tables disposable and rebuilt from raw, and keep append-only only for the `economic` restatement-class tables (monthly revenue, financials, dividends, flows). This drops the pointer files, the `v<N>` directories and the revisions view for `source_error` tables. Revisit it if the Phase 0 specs show a need.

### Twelve `snapshot_<source>` clean tables have no named consumer - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `116, 164, 203, 209, 253, 332`
* **Discrepancy Description**: Twelve per-source clean tables, each with its own parser and schemas deferred to Phase 0 (line 209), are speculative. The real need (D9) is that history cannot be recovered once missed. The raw cache plus `first_seen_at` already meets that need.
* **Rationale & Recommendation**: Keep the daily collection, which is the author's decision. Land snapshots in `data/raw/snapshots/` only, and write a clean table when a feature or check has a consumer. The TPEx `chtm`/`sprc` proxy is the one snapshot with an in-design consumer. This also lightens Agent A's load.

### Ownership concentrates risk in the Lead and Agent A - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `270-277, 283-285, 353-357`
* **Discrepancy Description**: The Lead builds all shared code, the specs and the spikes in Phase 0 before any agent starts, which is a single-threaded bottleneck. Agent A owns the calendar, stock info, delistings, official daily files, market cap, status events, snapshots, classification and the universe, and B, C, D and E all wait on A's gate. The design claims "disjoint files" but does not discuss the imbalance.
* **Rationale & Recommendation**: Move independent items out of A. Candidates are snapshots, stock info and delistings (S6 is only needed for those two), and status events. Alternatively, state explicitly why A is not split.

### Approval document still carries spec-level detail (altitude drift) - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `17, 82-89, 166, 236, 240-245, 249-252, 259-264`
* **Discrepancy Description**: Line 17 says this is an approval document, with interface specs and defaults in Phase 0 notes. Several sections are still at spec level:
  * Response-class rules, TWSE `OK` versus TPEx `ok`, 302 redirects, the 150 s timeout and the lock-file location (240-245).
  * Shard crash semantics and atomic JSON writes (249-252).
  * The universe regex, the `*` strip and the tie-break order (259-264).
  * Era field counts and a worked adjustment example (166, 236).
  * Eight resolved spikes with sample dates and row counts, listed under "Open Questions" (82-89).
* **Rationale & Recommendation**: Move the resolved spikes (S1-S4, S7-S9) to `docs/spikes/`. Leave only S5, S6 and S10 under Open Questions. Keep one sentence per response class in the design and move the rest to the specs. Keep the regex and the worked example in the specs or the data dictionary. The document would shrink to roughly 60% of its length.

### As-of adjusted series gives a spurious ex-date drop; the `available_at` rule may be over-conservative - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst` (merged)
* **Affected Scope:** `213, 222, 230, 232`
* **Discrepancy Description**: The rule "next trading day 08:30 after the ex-date" for `corporate_actions` makes the as-of series show a spurious drop equal to the dividend from the ex-date open until the next trading day 08:30. Line 232 labels this "not leakage", which is true. It is still a bias: every return-style feature carries the drop on every ex-date, concentrated in the July to August dividend season. Live, the ex-date and the dividend are known beforehand. Labels use the fully adjusted series (line 230), so features and labels disagree on ex-days.
* **Rationale & Recommendation**: The conservatism comes from not knowing the publication time. Options:
  1. Add a spike (S11, or extend S10) to find a pre-ex-date source. The exchange ex-rights and ex-dividend notices and the capital-reduction resumption reference price were not probed. Give `corporate_actions` two timestamps, `announced_at` and `effective_at`. `dividend_announcements` (line 197) already holds `announce_date`/`announcement_time`, and the reference price is roughly `prev_close - cash_dividend` with the stock ratio applied. If a source is found, the factor's `available_at` becomes the notice time. Check 3 would compare the exchange price with the locally computed one.
  2. If no source is found, keep the conservative rule, add an `is_ex_date_artifact` flag or mask, and state who is responsible for masking in the feature layer. A dictionary column alone is not enough.
  3. Risks: more event tables and sources, unverified notice times, and the "whose announcement" question for `TaiwanStockDividend` is unresolved.

### Raw cache as checksummed Parquet shards accepts a loss window the volume does not justify - Severity: Major
* **Reviewer Lens:** `egm-zoom-out`, `egm-inventive-catalyst` (merged)
* **Affected Scope:** `133, 249, 250, 340`
* **Discrepancy Description**: A crash can lose the responses in the shard being written, and a shard-size config is required. The project has only about 20,700 responses, so small-file pressure is trivial. For snapshots, a lost response is irreplaceable once the day has passed. The plan (line 105) says "Parquet", but its point is untouched responses, which files also satisfy.
* **Rationale & Recommendation**: Write one immutable file per response, named by sha256 and gzipped, plus an appended manifest line. Compact into shards later if needed. If Parquet shards stay, state the reason (for example DuckDB queryability of raw bodies). Cost: a compaction job and checksum bookkeeping.

### Stored point-in-time adjusted returns are rejected on a premise that only holds for levels - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `110, 236, 316-318`
* **Discrepancy Description**: D3 rejects any stored adjusted table because one stored `available_at` per row cannot be point-in-time. It then forbids Agent B's returns table as a feature input ("validation only"). That holds only for adjusted price levels. An adjusted daily return, `close(t) × f(t) / close(t-1)` with `f` the factor of the event on t only, depends on no future event. Its `available_at` is max(price time, action `available_at`), which is point-in-time correct and storable. Only levels need the as-of product. The cost of computing `adjusted_as_of(t)` for every research timestamp is unaddressed.
* **Rationale & Recommendation**: Materialise a point-in-time `returns_adjusted` table with its own `available_at` as the feature-safe artefact. Keep the as-of level view for validation. An as-of level for T equals the fully adjusted series except for events with `event_date` <= T < `available_at`, typically 1 or 2 pending events, which is cheaper than a full product per T. Risks: one more table with a restatement class, return-chain drift if consumers compound carelessly, and tests must prove stored returns equal view-derived returns at every as-of point.

### Snapshot capture and backup depend on a human and an unbuilt pipeline - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `60, 100, 116, 253, 295-296, 355-361`
* **Discrepancy Description**: Latest-only snapshot sources are the only irrecoverable data in the project. Capture starts only after approval and the Phase 0 clients and `snapshots.py` tests, and depends on a daily human-run command. Missed days are rated "High" risk and accepted. Cron and systemd were rejected because "WSL2 sleeps", which ignores Windows-host schedulers. `backup_dir` (line 100) is left as "decide later", while the risk table admits snapshot history is lost without it.
* **Rationale & Recommendation**:
  1. Split capture from parse. Raw responses are stored unparsed, so a minimal fetch-and-checksum script can start immediately, subject to the author's approval, with a later import into the shard format. It must still honour the per-host spacing and lock, and it bypasses the rule at line 382 that all network access goes through `src/twdata/clients/`, so it creates a migration step.
  2. Use Windows Task Scheduler with "wake the computer to run" invoking `wsl.exe -e <cmd>`, keeping the command manually runnable. This depends on BIOS, power and WSL start-up settings.
  3. Triage sources by recoverability. Sources with a date parameter or a history list (for example the TPEx `spendi` history, or the `warning` count derivable from the attention file) need weekly runs, not daily.
  4. Give `backup_dir` a no-cost reversible default, such as a second local volume or a synced Windows path.

### Stop-and-report on any `drift` makes benign oddities fatal to an 18-19 h run - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `114, 179, 240-241, 292, 328`
* **Discrepancy Description**: D7 stops the whole run on any `drift`, and restart is by a human. Zero rows on a trading day counts as `drift` (line 241). The calendar comes from FinMind, and its second source is derived from the same endpoints (line 96), so an unscheduled closure or a calendar disagreement stops everything. The rejected option, independent lanes with a dead-letter ledger (line 328), treats two designs as the only choices. The reviewer flags this as an explicit author decision, so it is a proposal to revisit narrowly, not a defect.
* **Rationale & Recommendation**: Keep a hard stop for ban-risk classes only (block, 403, 4xx bursts, auth). For `drift` on one date, write a row to a `parked_requests` list in `data/state/`, skip the date, continue, and exit non-zero at the end with the list. When both TWSE and TPEx return empty on a calendar trading day, record a calendar discrepancy instead of `drift`. Needs a deterministic retry command, a rule that parked gaps block the phase gate, and a per-endpoint cap (stop after N parked dates) so a schema change does not park thousands.

### FinMind plan uses 100% of the quota with no headroom - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `177-179, 238, 243-244, 291`
* **Discrepancy Description**: Collection is planned at exactly the full quota (6,300 requests at 600 an hour is 10.5 h, line 177). Spikes, retries, the 500-close sample and the author's own use share the token. The "under 5%" extras guarantee the limit is exceeded. Any 402 or 429 then stops the run, and a 4xx burst also risks the IP ban.
* **Rationale & Recommendation**: Have the limiter target a configurable 80 to 90% of the user-info limit. Re-read `user_count` and `api_request_limit` periodically. Sleep until the hour rolls over when the count approaches the limit, so a 402 is never sent (an arriving 402 remains a stop). Restate the estimate as about 12 h. Risks: the user-info call has its own failure mode, a shared token can make the counter lag, and the limiter becomes stateful.

### "No official feed carries splits or par-value changes" rests on partial evidence - Severity: Major
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `87, 236`; `docs/research/tpex_findings.md` line 33
* **Discrepancy Description**: The evidence covers only `TWT49U`, `TWTAUU`, `exDailyQ` and `revivt`. The TPEx findings name two untested pages (par-value change reference, `/zh-tw/announce/market/change/reference.html`, and the reduction notice, `/reduction.html`). TWSE equivalents were never searched, nor was MOPS probed for the 0050 reference price. `config/manual_corporate_actions.yaml` is a single-person entry channel for a lookahead-critical table, and gaps are caught only by check 3(b) after the 18 h run.
* **Rationale & Recommendation**: Spend a few probe requests on the two TPEx pages and a TWSE equivalent before accepting "no source". Generate candidates automatically: dates where a stock has a trading halt and the price ratio is near a rational factor (2, 3, 4, 1/2, ...), emitted for human confirmation so the YAML holds confirmations, not discoveries. State ownership of the detector (`validate/` or `ingest/`). It should not be F's check, because F would then produce its own ground truth. Expect false candidates from other halts.

### Hand-rolled limiter versus existing packages - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `334`
* **Discrepancy Description**: The claim "No standard package gives a per-host cross-process spacing lock" is not backed by a stated check. `filelock` and `pyrate-limiter` (SQLite and file-based multiprocess backends) are candidates. The reviewer could not verify this offline.
* **Rationale & Recommendation**: State that the packages were checked. If the limiter stays custom, keep it to a lock plus a last-timestamp.

### Trading calendar lacks a cheap third cross-check - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `96, 158`
* **Discrepancy Description**: The second calendar source is derived from the same endpoints as the first (see also the D7 finding).
* **Rationale & Recommendation**: Add `exchange_calendars` (XTAI) as a Phase 0 cross-check only. Its typhoon-closure accuracy is unverified.

### `market_cap` stored as a table although purely derived - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `191, 227`
* **Discrepancy Description**: `market_cap` derives from `prices_raw` and `shares_issued`, with `available_at` the latest of its inputs. The stored table adds append-only versions with no new information.
* **Rationale & Recommendation**: Make it a DuckDB view, like `listing_status` (line 209) and the adjusted prices (D3).

### Decisions and goals recorded three times - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `45-52, 65-76, 106-116, 308-334`; `docs/DECISIONS.md`
* **Discrepancy Description**: D1-D9 appear in the decisions table, again in Alternatives, and again in `docs/DECISIONS.md`. The goals partly repeat the checks, and the `available_at` table repeats D2.
* **Rationale & Recommendation**: Keep one place per fact. Make Alternatives reference the decision table and list only the options not chosen.

### "Zero-decision standard" is undefined - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `17, 355`
* **Discrepancy Description**: The term is used without a definition or link.
* **Rationale & Recommendation**: Define it in one line or link to its source.

### Critical-path text is inconsistent about `chtm` and the 5 s spacing - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `179, 243, 261`
* **Discrepancy Description**: Line 179 says `chtm` finishes in the background, but universe rule 3 (line 261) needs `chtm` for TPEx exclusions. TPEx `otc` plus `chtm` is 7.9 h on that host, which fits inside the 8 h universe pass, but the text does not say so. The 5 s spacing is a chosen default, not an observed limit.
* **Rationale & Recommendation**: State the 7.9 h fit. Make the choice not to probe shorter spacing a conscious one, given the IP-block risk (line 243).

### "Four timings" in the `available_at` section does not match the table - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `213`
* **Discrepancy Description**: The text says "four timings", but the table lists more distinct rules (18:00 same day, next-day 08:30, 10th at 18:00, statutory deadline then 08:30, announcement time, `first_seen_at`, US next Taiwan calendar day, latest of inputs).
* **Rationale & Recommendation**: Count them correctly or rename the grouping.

### Invented acceptance thresholds - Severity: Nit
* **Reviewer Lens:** `egm-zoom-out`
* **Affected Scope:** `71, 76`
* **Discrepancy Description**: The churn range of 2% to 40% and the 8% unexplained-move threshold are proposals. Check 3(b) also depends on checks working as designed.
* **Rationale & Recommendation**: Record them as "calibrate after first year" so that failures do not become noise.

### Critical path serialises the universe pass before FinMind - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `178-179, 285, 363`
* **Discrepancy Description**: The universe pass (about 8 h) must finish before FinMind (about 10.5 h) starts, but FinMind calls are per stock for the whole date range. A stock first seen in 2015 could be requested as soon as it first becomes a member.
* **Rationale & Recommendation**: Run the official pass chronologically, evaluate each month-end once its 60-day window exists, and feed new members to the FinMind queue incrementally (state already tracks completed stock ids per dataset, line 251). The critical path would become the longest single host chain, about 12 h, not 18-19 h. Phase gates would change to streaming, and QA must verify no stock was missed. The reviewer rates it as not worth it if the run is staged anyway.

### Clean rewrites lack identical-value dedupe and a re-pull schedule - Severity: Nit
* **Reviewer Lens:** `egm-inventive-catalyst`
* **Affected Scope:** `252, 299`
* **Discrepancy Description**: Clean writes are append-only per run, but the design does not say that a rerun writes no rows when values are identical, so files grow by duplicates. The `economic` and `source_error` views show revisions only if data is re-pulled, yet no refresh cadence is defined, while the risk table (line 299) treats the views as the mitigation.
* **Rationale & Recommendation**: Skip rows identical to the latest stored value (costs a read-before-write on large partitions). Define a re-pull schedule for the volatile subset (the last N days for flows and margin, monthly revenue monthly), and say which datasets are never re-pulled and so cannot show revisions. Re-pulls consume FinMind quota (see the quota finding).
