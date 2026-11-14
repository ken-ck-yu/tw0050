# Decision log

Newest last. Each entry: what was decided, why, and what was rejected.

## 2026-11-13: answers to the plan's open questions (Ken)

- **FinMind tier:** free first. Use fallbacks (for example market cap as close times shares issued) and list what a paid tier would unlock. No subscription without Ken's approval. Rejected: subscribing up front.
- **Storage:** local disk under `data/`, gitignored.
- **Liquidity floor:** NT$20M median daily turnover, because positions will be small.
- **Universe size:** 200, with case-by-case additions through `config/watchlist.yaml`.
- **Still open:** employer personal-account dealing rules, to be confirmed before any live trading phase.

## 2026-11-13: token handling (Ken)

- Token lives in a gitignored `.env`, loaded at runtime. `.claude/settings.json` denies agent reads and edits of `.env*`. Gitleaks runs as a pre-commit hook. Rejected: token in the shell profile.

## 2026-11-13: audit hook uses python3 instead of jq (Lead)

- `jq` is not installed and installing it needs sudo. `.claude/hooks/audit.sh` writes the same metadata-only fields using `python3`. Rejected: waiting for sudo access.

## 2026-11-13: FinMind tier findings (Lead)

- Free account: 600 requests/hour. Three datasets need a paid tier: `TaiwanStockPriceAdj`, `TaiwanStockCapitalReductionReferencePrice`, `TaiwanStockMarketValue`. Fallbacks are in `docs/FINMIND_DATASETS.md`.

## 2026-11-13: free official sources replace the three paid FinMind datasets (Lead)

- TWSE and TPEx publish ex-rights, capital-reduction and quarterly-share data free back to 2015-06 (see `docs/OFFICIAL_SOURCES.md`). No paid tier is needed for the P0 set. Disposition and attention stock lists are now sourced from TWSE `punish` and `notice`. Rejected: paid FinMind tier. Risk accepted: the `rwd` / `www` endpoints are undocumented and scrape-grade, so every response is cached raw.

## 2026-11-13: research findings and decisions made by the Lead (not yet reviewed by Ken)

Evidence is in `docs/OFFICIAL_SOURCES.md` and `docs/research/`. Each item below is reversible and open to review.

- **TWSE market cap** comes from `MI_QFIIS` issued shares times close. FinMind `TaiwanStockShareholding` becomes the cross-check. Rejected: FinMind as the only source.
- **Last trading day and survivorship** come from the daily files of both markets. Delisting lists are a cross-check only, because the last trade is 3 to 13 days before the listed delisting date in all six stocks checked, codes are reused, and the TPEx list may miss transfers to TWSE.
- **TPEx suspension and trading-restriction history** uses the per-day `chtm` report as a proxy, with daily snapshots of `bulletin/warning` and `bulletin/sprc` starting at approval. Rejected: waiting for a better source.
- **Revenue `available_at`**: FinMind `create_time` is the load date and exists only from 2026-04-21, so the 10th-of-next-month fallback is the primary rule, not a fallback.
- **Open, needs Ken:** a live FinMind probe (maximum years per call, US ticker coverage, `create_time` and shares-issued blanks), and whether to accept the TWSE full-delivery gap.
- **Correction:** the FinMind docs list the Free limit as 300 requests per hour and Register as 600. The live user-info endpoint reported 600 for this account on 2026-11-13, and that value wins.

## 2026-11-13: TWSE full-delivery gap accepted (Ken, on the Lead's assessment)

- No TWSE source for full-delivery status was found, and the daily files carry no marker. TPEx folds it into `chtm`. Impact is low: a stock must also rank in the top 200 by market cap and clear the NT$20M turnover floor, so only a handful of stock-months could slip in. QA reports how many. A daily `TWT85U` snapshot starts at approval. Rejected: further blind path searching.

## 2026-11-13: FinMind live probe results (Ken ran the probe, Lead recorded)

- One call returns the whole 2015-2026 range, so the request budget for FinMind datasets is one request per stock per dataset. Details in `docs/FINMIND_DATASETS.md`.
- FinMind has no shares-issued rows for at least one delisted TPEx stock (3299). Official TWSE `MI_QFIIS` and TPEx `otc` stay primary for market cap and the universe.
- `create_time` is blank for 93% of 2330's revenue rows, so the 10th-of-next-month rule is the main revenue `available_at` rule. Confirmed.

## 2026-11-13: design revision 2, architecture choices made by the Lead from the review and research (open to Ken's override)

- **Adjusted prices** are raw prices plus an event table, adjusted as of a time. No stored adjusted table, because one `available_at` per row cannot be point-in-time.
- **Idempotent writes** are append-only clean files, with a view picking the first-reported row. Parser fixes write a new version directory and the old one stays until Ken approves deleting it. Rejected: rewriting year partitions in place (overwrites collected data, conflicts with first-reported).
- **Agent A** collects all-stock prices and shares issued (plan section 2), which removes the A, B, D dependency cycle.
- **Universe pass** needs prices from 2015-03-02 so the first 60-day turnover window is complete. The universe starts 2015-06-30.
- **Cross-process limiter** is a file lock plus a timestamp per host, because no standard package provides it. FinMind is called by REST, not the `FinMind` package. `pandas` is dropped.
- **Check thresholds** (0.1% adjusted-return tolerance, 99.9% exact close match, 2% to 40% membership turnover) are proposals in `config/settings.yaml`.
- **Open for Ken:** confirm option B (official primary) on the survivorship and shares-issued grounds, since the original request-count reason did not hold. Snapshot job schedule. Backup location for `data/raw/`.

## 2026-11-13: answers on option B, snapshot job and backup (Ken)

- **Option B confirmed** (official TWSE/TPEx files primary for the universe pass) on the survivorship and shares-issued grounds, since the original request-count reason did not hold.
- **Snapshot job** runs as a manual daily command with catch-up. Rejected: a cron or systemd timer (WSL2 sleeps) and another always-on machine. Missed days for latest-only sources are lost and reported.
- **Backup location for `data/raw/`:** decide later. `backup_dir` stays unset and QA reports it at each phase gate.

## 2026-11-13: answers to the round 2 review questions (Ken)

- **Altitude:** `docs/designs/data_platform.md` is an approval document. It keeps phase gates, ownership, schemas of record and acceptance criteria. Interface specs, file lists, test vectors, tooling and defaults go to Phase 0 task notes written by the Lead and checked against the zero-decision standard there. Rejected: a full zero-decision spec in the design (longer, harder to keep in sync as spikes change things).
- **Failure behaviour:** stop and report. Three response classes (ok, transient, drift), no circuit breaker. Rejected: independent lanes per (host, dataset).
- **Phase 2 scope:** all agent C, D and E datasets, as plan section 6.6 says. Rejected: seed-hypothesis datasets first.
- **Check 1 reference:** the full FinMind price pull over the collection set is the independent listed-day reference. Rejected: sampling only.
- **Snapshot scope:** all about 12 latest-only sources. Rejected: only sources that close a named gap.

## 2026-11-13: earlier Lead-attributed decisions, recorded here as asked by the review (Lead proposals until Ken confirms)

- **`available_at` for date-only sources:** next trading day 08:30 (Ken chose this when asked during drafting).
- **Rejected alternatives:** per-dataset time rules and retrieval-time-going-forward (Ken, during drafting); ingesting both sources and reconciling (Ken, during drafting).

## 2026-11-13: spike results and Lead decisions (open to Ken's override)

- **Spikes S1 to S4 resolved** (evidence in `docs/research/spikes_*_findings.md`). `MI_QFIIS` has no gaps for common stocks on four dates, so the FinMind shares-issued fallback chain is dropped (FinMind stays the cross-check). The common-stock rule is the regex plus the `-DR` name rule, with a trailing `*` stripped from names.
- **Stock splits and par-value changes have no official source.** 0050 shows an apparent split between 2025-06-02 and 2025-07-21 with no event row. Handling: `config/manual_corporate_actions.yaml`, each entry with a source, entered as `split` or `par_value_change` rows, and check 3(b) lists any large move with no event. Rejected: the paid `TaiwanStockPriceAdj` tier. The split itself is inferred from prices and needs an independent confirmation.
- **TPEx next-day limit sentinel** (`9999.95`/`0.01`, bond ETFs) is stored as null.

## 2026-11-13: FinMind probe 2 results (Ken ran the probe, Lead recorded)

- **Spikes S7 and S9 resolved.** No cap on 11-year calls for the large datasets. FinMind closes have two decimals and matched the exchange in 20 of 20 pairs.
- **0050 split confirmed from prices:** a 4-for-1 split resumed 2025-06-18 after a halt (2025-06-11 to 2025-06-17), with no official event row. It goes into `config/manual_corporate_actions.yaml` with the reference price to be taken from the exchange announcement. An earlier note citing "51.45 on 2025-07-21" was a misreading: 51.45 is the 2025-07-18 close.

## 2026-11-14: round 3 answers and Lead decisions (Ken, unless marked Lead)

- **Calendar exception to D7 (Ken):** when both TWSE and TPEx return no rows on a day the FinMind calendar calls a trading day, record a calendar discrepancy and continue. Every other drift still stops the run.
- **Snapshot capture starts now (Ken):** a minimal stopgap, `scripts/snapshot_capture.py`, captures 15 latest-only OpenAPI endpoints as raw responses under `data/raw/snapshots/`. Ken runs it once per trading day. The M1 job replaces it and imports its files. Rejected: waiting for the build. The TPEx suspension history for ROC 2026 (365 records) was also captured once on 2026-11-14.
- **Phase 0 specs review (Ken):** a fresh-reviewer review of `docs/specs/` against the zero-decision standard (at most two rounds), with a one-page summary to Ken before agents build. Rejected: Lead check only, and Ken reading the specs in full.
- **Stop revising (Ken):** fix the three round 3 Blockers and the mechanical items, then continue. No fourth review round before approval. Reason: speed to a profit test.
- **Ownership enforcement (Lead):** a post-hoc `git diff --name-only` check by the Lead after each agent run, replacing the proposed `PreToolUse` hook. Reason: A to E share one agent type and a hook cannot confine Bash writes.
- **Milestones renamed M0 to M3 (Lead)** so they do not collide with plan phases. **`price_limits` split from `prices_raw` (Lead).** **Quota headroom (Lead):** the FinMind limiter targets 85% of the user-info limit, so the estimate is 12.4 hours and the critical path about 20 hours. **TPEx ISIN is nullable (Lead).** **Check 4 threshold (Lead):** at most 1 mismatch in 500 (99.8%), replacing the 99.9% in an earlier entry, because 99.9% of 500 rounds to zero mismatches.

## 2026-11-14: design approved (Ken)

- **`docs/designs/data_platform.md` revision 4 is approved**, and M0 may start. Known open items at approval: spikes S10, S11, S12, S5 and S6, the 0050 split reference price, the unset backup path, Ken's review of scraping terms of use, and three unreviewed fixes from round 3. Anything wrong later comes back for revision.

## 2026-11-14: early research lane approved (Ken)

- **Why:** Ken wants a fast signal on whether the strategy can make money, before all of Phase 1 data has passed QA.
- **What:** `docs/amendments/early_lane.md`, referenced from rule 3 in `CLAUDE.md`. The lane opens only after M1 (prices, universe) and `monthly_revenue` have passed their gates. A frozen evaluator with full costs is owned by a separate agent. Development window 2015-06-01 to 2024-06-30 (train to 2021-12, validation 2022-01 to 2024-06), and a sealed holdout from 2024-07-01 that agents cannot read and only Ken unlocks, once. At most 10 backtests per cycle, all logged, with a committed hypothesis card first. All results are provisional until the full QA passes. Broker and order code stay forbidden.
- **Rejected:** keeping the plan's order (finish all data and QA first).

## 2026-11-14: overnight autonomous run authorised (Ken)

- **Authorised:** continue unattended until Ken sees the first test result: finish the M0 spec review and fixes, waive the pre-build summary approval (Ken reads it in the morning), build M0 with parallel builder agents that have disjoint owned paths, build and run the tokenless M1 pass (official TWSE and TPEx daily files) in sessions, and open the early research lane when its own gates pass. Resolve issues without waiting for Ken where possible.
- **Not covered by this authorisation (Lead's reading):** any paid FinMind tier; deleting or overwriting collected data; unlocking the sealed holdout; broker, order or live-trading code; reading, printing or logging `FINMIND_TOKEN` or `.env`; raising request rates above the design's limits; changing the early lane's rules; any change to `.claude/settings.json` or `.claude/hooks/`.
- **Consequence:** steps that need the FinMind token (calendar, stock info, delistings, monthly revenue, other per-stock datasets) wait until Ken runs one prepared command. The first test result needs monthly revenue, so it is expected after that command, unless the Lead finds a tokenless route.
- **Stop rules during the run:** any block, auth error or 4xx burst stops that source and is reported in the morning. An IP block is waited out (about 30 minutes) at most once.

## 2026-11-14: FinMind token may be used at run time (Ken)

- **Authorised:** the Lead may run scripts and the project CLI that load `FINMIND_TOKEN` from the gitignored `.env` into the process environment (for example by sourcing `.env` in the same shell command that starts the script). Ken said the token expires in 7 days and he can rotate it.
- **Still forbidden (rule 2):** displaying, printing, logging, caching or committing the token or any request header, and any command whose output could show it (for example `env`, `printenv`, `cat .env`, `set -x`). Scripts print only whitelisted, non-secret fields. The Lead does not pass the token to subagents. FinMind runs are started by the Lead only.
- **Free tier only:** any 402 or other 4xx stops the FinMind run and is reported. No paid tier is ever selected. The limiter keeps to 85% of the live user-info limit.
- **Effect:** the FinMind steps (calendar, stock info, delistings, monthly revenue and the other per-stock datasets) no longer wait for Ken, so the first test result can come overnight.

## 2026-11-14: split factor and 0050 reference price (Lead; open to Ken's override)

- For `split` and `par_value_change` entries the adjustment factor is exactly `1/ratio`. The 0050 resumption reference price was searched: press gives 47.32 (finance.technews.tw, 2025-06-17, Yuanta NAV-based) and 47.16 (money.udn.com, 2026-05-25, unsourced); no exchange announcement was found. Using either as `reference_price/halt_close` would put a 0.3% error into the benchmark's adjusted return, so the reference price is informational only. The ratio of 4 rests on FinMind's price gap (188.65 on 2025-06-10, 47.57 on 2025-06-18, halt 2025-06-11 to 2025-06-17) and on the press reports of the 1-for-4 split. Rejected: gating M0 on an official reference price.
- Round 2 clarifications (TPEx `----` and ex-date text, the real TWSE holiday reply shape, `status_events.event_date`, `prices_raw.stock_name`, OpenAPI cache bypass) are in `docs/specs/m0_specs.md` section 17.

## 2026-11-14: S6 resolved: stock_info key (Lead)

- `stock_info` key is `stock_id, event_date, industry_category` (FinMind lists a stock once per industry category). Details in `docs/spikes/S6.md`.

## 2026-11-14: staged collection plan for the overnight run (Lead)

- Stage 1 (first year, 2015-03-02 to 2016-03-31) and the development window (2016-04-01 to 2024-06-30) run as separate `daily_official` and `status_events` processes. The host limiters (one request in flight per host, 5 s apart) serialise them safely, so the hosts stay busy. The post-development period (2024-07-01 to now, the sealed holdout and recent data) is collected after the first test result.
- Era smoke tests passed before the long run: TPEx layout change 2020-04-29 and 2020-04-30, 2024-06-27 and 2024-06-28, and the 2025 relabel 2025-01-09 and 2025-01-10.

## 2026-11-14: development window extended to 2025-12-31; holdout starts 2026-01-01 (author decision)

- **What:** `research.dev_end` moves from 2024-06-30 to 2025-12-31. Validation becomes 2022-01 to 2025-12; train is unchanged. The sealed holdout is 2026-01-01 to the latest date, about 10 months at this date.
- **Why:** the author wants recent market conditions in development and a holdout of almost a year. The old date came from the early lane's proposed dates and was not derived from anything.
- **Timing:** made before any strategy produced a result, so the date was not chosen using results. The evaluator reads the date from settings, so `research/EVALUATOR_SHA256` is unchanged.
- **Work:** collect `daily_official` and `status_events` for 2024-07-01 to 2025-12-31, then market cap, universe and `monthly_revenue` through 2025-12-31. Nothing after 2025-12-31 goes into `data/research/`.
