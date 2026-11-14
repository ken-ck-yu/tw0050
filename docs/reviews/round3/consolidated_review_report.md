# Consolidated Review Report (round 3)

**Target:** `docs/designs/data_platform.md` (386 lines, revision 3, status Draft)
**Mode:** uninterrupted full flow, five stages, 2026-11-13 to 2026-11-14
**Verdict:** not ready to approve as written, but the findings have shifted from design flaws to gates, ownership and wording. Three Blockers remain (round 1 had 10, round 2 had 6). None of the Blockers is a design-direction problem.

## Trend across rounds

| Round | Blockers | Where they came from | What they were about |
| --- | --- | --- | --- |
| 1 | 10 | feature-spec and implementation stages | missing sections, circular ownership, unresolved inputs, wrong claims |
| 2 | 6 | implementation stage only | interface specs, gate errors, a mechanism that could not work |
| 3 | 3 | comprehension (2), implementation (1) | undefined table classification, an unexplained set size, an unpassable gate |

Majors still number in the dozens per round, but most are repeats of a few themes, and reviewers rate overlapping items differently. Fresh reviewers will always find more. The remaining risk is mostly in specs not yet written, which the design already puts behind its own review gate.

## Reviewer status

| Stage | Report | Reviewers | Status | Reported severity |
| --- | --- | --- | --- | --- |
| 5 Zoom out | `zoom_out_report.md` | `egm-zoom-out`, `egm-inventive-catalyst` | completed | 0 B, 11 M, 10 N |
| 6 Comprehension | `comprehension_report.md` | `egm-comprehension` | completed | 2 B, 10 M, 13 N |
| 7 Critic | `critic_report.md` | `egm-design`, `egm-structural`, `egm-style` | completed | 0 B, 23 M, 28 N |
| 8 Intermediate zoom out | `intermediate_zoom_out_report.md` | `egm-zoom-out` | completed | 0 B, 6 M, 4 N (new) |
| 9 Implementation readiness | `implementation_readiness_report.md` | `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` | completed | 1 B, 16 M, 8 N |

Every stage ran once with no retry. Counts are as each report lists them and overlap between stages.

Limits: the Stage 5 zoom-out reviewer opened only part of the research files, and the Stage 6 comprehension reviewer read the document alone by design (and did not check that the linked files exist). Several reviewers' own summaries disagreed with their lists, so the lists were used. Stage 8 found no earlier finding fully resolved, because the earlier answered items were decisions, not fixes.

## Blockers

1. **The Phase 0 gate cannot be passed as written.** It is "offline" but requires every spike logged (S5 and S6 belong to later agents, S10 needs live polling on several trading days) and a calendar diff whose second source only exists after the Phase 1 pass of about 8 hours. (S9 Blocker, S8 N1, S9 Majors 2 and 11)
2. **`collection_set` and several tables have no stated `event_date` or joinable-versus-reference status.** The Goals say every joinable table has `event_date` and `available_at`, but `collection_set` has no date column, `market_cap` and the snapshot tables have unstated semantics, and `dividend_announcements` and `corporate_actions` leave `event_date` ambiguous. (S6 Blocker 1, S7)
3. **The collection set's size and ordering are unexplained.** It is defined as every stock that was ever a member, which needs the market cap from the pass that runs first. "About 450" has no basis, and the 6,300-request budget rests on it. Monthly churn of 3% would already push the union past 450. (S6 Blocker 2, S8 N8)

## Major (by theme)

**Gates, phases and ownership**
* Gates have no pass criteria, owners or exit conditions. The Phase 2 live window (2018-10 to 2018-11) has no corporate-action event, so Agent B's logic may run on an empty table. Fixtures have no owner. Phase terminology is overloaded ("Phase 1" is the project and also Agent A's step, and "Phase 2" collides with plan section 10). (S9, S7)
* Ownership among agents A to E cannot be enforced by an agent-type hook because all five share one agent type. The Agent F write mechanism cannot confine Bash writes, and the hook test belongs to no gate. A post-hoc check of `git diff --name-only` after each agent run covers Bash and all agents. (S9, S8 N5)
* The design cannot be approved without sight of the Phase 0 specs, which hold the defaults that affect data. A fresh review of the specs and a decision-log entry for semantic defaults would close this. (S9)
* Agent F's inputs are stale (`qa-goldfish.md` reads `docs/DATA_DICTIONARY.md` and plan section 7, while the design adds per-topic dictionary files and its own check thresholds). (S9)
* The snapshot job is an unlisted daily author duty with no gate and no backup. History is perishable, and 2026 TPEx suspension history will be lost at year end. (S5, S8 N4, S9)

**Calendar and sequencing**
* The calendar has two owners and starts 2015-06-01 while collection starts 2015-03-02, so March to May 2015 have no source. `chtm` is needed for the universe build but sequenced after it. The 18 to 19 hour critical path is double counted across phases. (S8 N1, N2, S9, S7)

**Checks and evidence**
* Some checks have no usable pass rule (3(a), 3(b), 5), some compare against raw FinMind prices that cannot agree on event days, and nothing tests completeness for the C, D and E datasets. Check 1 does not exclude FinMind's documented 2022-11 to 2023-03 backfill. Cross-check columns name comparisons no numbered check performs. (S7)
* Statements are stronger than the evidence in several places. "Every rule gives a conservative upper bound" (S10 is unresolved). "No official feed carries splits" (TWSE equivalents and two TPEx pages were not probed). "TWT49U excludes split capital reductions" may mean demerger reductions. The TPEx `chtm` to full-delivery mapping is inferred, not verified. "Resolved S7" covers about 10 of 14 datasets. (S7, S5)
* Vintage guarantees are overstated. `as_first_seen` for history collected in 2026 carries 2026 values, and FinMind corrected EPS, ETF dividends and flows in 2026. (S7, S5)

**Design and data model**
* Schemas of record are partly deferred or have doubtful keys (`securities_lending` returns about 6.4 rows per day against a three-column key, futures institutional data has its own dimension). `prices_raw` merges three endpoints under append-only writes, so limits should be a separate table. The shared clean-writer and views layer has no owner. The TPEx ISIN has no source. (S7, S8)
* The ex-date lag creates a spurious as-of drop on every ex-date, and the rule may be over-conservative because the reference price may be known earlier. Stored point-in-time adjusted returns are rejected on a premise that holds only for price levels. (S5)
* The append-only versioned clean layer is more machinery than the data needs. Twelve snapshot clean tables have no consumer. The raw cache as Parquet shards has a crash-loss window. A hand-rolled limiter was not checked against `filelock` or `pyrate-limiter`. (S5)

**Resilience**
* The FinMind plan uses 100% of the quota. Stop-and-report on any `drift` makes benign oddities fatal to an 18 to 19 hour run (author decision D7, flagged for a narrow revisit only). The run is described as attended and as unattended, with no risk row for the machine sleeping. (S5, S7, S8)

**Altitude and structure**
* The approval document still carries spec-level detail, and resolved spikes sit under "Open Questions" (the document would shrink to about 60% if moved). The Alternatives section does not use one template and omits several design-weight choices. Open Questions mostly logs resolved spikes. (S5, S7)

## Nits

About 60 across stages: heading names, forward references, repeated statements, undefined abbreviations and endpoint names, snapshot source count (13, not "about 12"), spike results stated more strongly than their samples, and wording items listed in the stage reports.

## Decisions for the author (one by one)

1. **Calendar disagreement:** treat both exchanges returning empty on a day FinMind calls a trading day as a recorded calendar discrepancy instead of `drift`. It is a narrow change to your stop-and-report decision D7.
2. **Snapshot capture timing:** start raw capture of the latest-only sources now with a minimal script, or keep the start at the beginning of the build. (The TPEx suspension history has been captured once, now.)
3. **Spec review gate:** whether you want to see the Phase 0 specs, or a fresh-reviewer pass on them is enough before agents build.
4. **Stop revising?** Whether to fix the three Blockers and the clear mechanical items, then ask you to approve with a short list of accepted open items, or run a fourth review round first.

## Recommended order of work

1. Fix the three Blockers and the mechanical Majors (gate wording, table classification, collection-set basis, phase renaming, calendar stub and owner, `chtm` ordering, TPEx ISIN nullable, price limits as their own table, quota headroom, resolved spikes moved out of Open Questions).
2. Replace the hook with a post-hoc ownership check by the Lead, and update the author prerequisites to match.
3. Calibrate the overstated statements against their evidence.
4. Run the remaining probes the reviewers named (TWSE and TPEx splits, the TPEx `chtm` mapping, `securities_lending` key, financial statement call limits).
5. Ask for approval.

## Traceability matrix

| Consolidated item | Source findings |
| --- | --- |
| Blocker 1 (Phase 0 gate) | S9 Blocker, S8 N1, S9 Major 2 and 11 |
| Blocker 2 (table classification) | S6 Blocker 1, S7 snapshot `event_date` |
| Blocker 3 (collection set basis) | S6 Blocker 2, S8 N8 |
| Calendar start and ownership | S8 N2, S9 Major 2, S7 calendar |
| `chtm` ordering and `status_events` | S8 N10, S9 Major 9, S7 `chtm` nit |
| Agent F and ownership enforcement | S9 Majors 3, 4, 5, S8 N5, S7 F ownership |
| Gates and criteria | S9 Majors 6, 8, 10, 12, 13, 15 |
| Snapshot job and capture | S5, S8 N4, S9 Major 14 |
| Overstated evidence | S7 split and halt, upper bound, S7 `chtm`, S7 "resolved S7" |
| Clean layer, snapshots, shards, limiter | S5 Majors and Nits |
| Altitude and structure | S5 altitude, S7 Open Questions and Alternatives |
