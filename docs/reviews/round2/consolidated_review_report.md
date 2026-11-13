# Consolidated Review Report (round 2)

**Target:** `docs/designs/data_platform.md` (388 lines, revision 2, status Draft)
**Mode:** uninterrupted full flow, five stages, 2026-11-13
**Verdict:** not ready for approval, but much closer than round 1. Round 1 had 10 consolidated Blockers. Round 2 has 6 Blockers, all from the implementation-readiness stage. The feature-spec stages found none. Most of the remaining work is either corrections to errors in revision 2, or one decision for the author about how detailed a pre-approval design should be.

## Reviewer status

| Stage | Report | Reviewers | Status | Reported severity |
| --- | --- | --- | --- | --- |
| 5 Zoom out | `zoom_out_report.md` | `egm-zoom-out`, `egm-inventive-catalyst` | completed | 0 B, 14 M, 4 N |
| 6 Comprehension | `comprehension_report.md` | `egm-comprehension` | completed | 0 B, 16 M, 17 N |
| 7 Critic | `critic_report.md` | `egm-design`, `egm-structural`, `egm-style` | completed | 0 B, 28 M, 25 N |
| 8 Intermediate zoom out | `intermediate_zoom_out_report.md` | `egm-zoom-out` | completed | 0 B, 7 M, 6 N |
| 9 Implementation readiness | `implementation_readiness_report.md` | `egm-implementation-readiness`, `egm-codebase-details`, `egm-style` | completed | 6 B, 17 M, 12 N |

Every stage ran once with no retry. Counts above are as each report states them, with overlap between stages, so they are not a total.

Limits: reviewers share one model's blind spots and ran no probes. The structural reviewer in Stage 7 did not open the reading list. The implementation-readiness reviewer in Stage 9 did not open `qa-goldfish.md` or `ingest-worker.md`, and the codebase-details reviewer did not read `finmind_findings.md` in full. Stage 8 treated the document as unchanged since Stage 5, so it repeats Stage 5 findings and adds five of its own. The Stage 5 report's header had wrong counts, corrected by the lead.

## The one decision that shapes the rest

The reviewers pull in opposite directions on altitude.
* Stages 5 and 8 say the design is **too large and too detailed for pre-approval**. They want file lists, test vectors, tooling and parameter defaults moved out to Phase 0 task notes or config, leaving phase gates, ownership and acceptance criteria.
* Stage 9 says the plan is **not detailed enough to implement** and breaks the zero-decision rule. It wants interface specs, per-module column mappings, snapshot table definitions and a complete file list.

These cannot both be satisfied in one document. The author needs to choose what this document is. See "Decisions for the author".

## Errors in revision 2 (the lead's own, to fix)

These were caught by reviewers and are not judgement calls.
1. **`MI_QFIIS` coverage gap is an artefact.** The design compares 915 `MI_QFIIS` rows (2015-06-01) with 951 `MI_INDEX` rows (2016-06-01), a year apart. On the same date `MI_INDEX` had 919 stock rows. No gap has been measured. The same wording is in `docs/OFFICIAL_SOURCES.md`. (S7, S8)
2. **The Phase 2 gate month is wrong.** It runs 2020-06 with stock 2475, which was delisted 2019-05-13, so the delisted-name path is never exercised. (S9 Blocker)
3. **The worked example contradicts the rule.** The adjusted close is stated as 95 "after day 2 08:30", but `corporate_actions.available_at` for an ex-date on day 2 is day 3 08:30. The unit test repeats it. (S6, S7, S9)
4. **The Phase 1 gate depends on check 8, which is F's Phase 3 code.** (S9 Blocker)
5. **Check 6 wording conflicts with the revenue rule.** Check 6 says "after the first day of the following month". The rule says the 10th at 18:00. (S6, S7)
6. **Delisting gap range is wrong.** "3 to 13 days" is from six stocks, and TPEx 5306 had a 1-day gap, so it is 1 to 13. The "FinMind lacks delisted TPEx names" claim rests on one probe. (S7)
7. **The wall-clock figure is wrong in four places.** About 12 hours is the TWSE host alone. FinMind collection starts after the universe exists, so the critical path is about 8 + 10.5 = 18 to 19 hours. (S5, S7, S8, S9)
8. **Stale prerequisite text.** Line 331 still lists the snapshot schedule as open and makes the backup path part of the Phase 0 gate. (S9)
9. **Decisions recorded without a decision-log entry.** The `available_at` rule for date-only sources, and the rejections of options C and per-dataset time rules, are attributed to the author but not in `docs/DECISIONS.md`. (S7)
10. **Internal inconsistencies:** "exactly 200" versus allowed shortfall in three places (S6, S7, S8); the "every clean table has `available_at`" claim versus the exempt tables (S7); the benchmark appearing in two source rows with different cross-checks and no primary for `TPEX_TR` (S6, S7); "turnover" used for both trading value and membership churn (S7); one-call-per-stock generalised from a single probe (S7); a dangling "see Idempotence" reference (S7).
11. **Unsupported test fixtures.** The parsing test cites an HTML sign format that appears in no research file. (S9)

## Blockers

All six are from Stage 9.
1. **Phase 0 modules have no interface spec.** Files are listed by name only, with no signatures, error types or registry format, and agents A to F code against them in parallel. The limiter and breaker tests need an injectable clock that is not specified.
2. **Ingest, universe and validate modules have no actionable steps, and several schemas are left open.** Eight tables say "exact columns when their module is built". Snapshot tables have no names, columns or keys.
3. **Spikes S1 to S6 have no scripts, locations or follow-through.** Their outcomes change the design.
4. **The validation-write protection cannot work as written.** `.claude/settings.json` deny rules apply to every agent, so denying edits to the validation paths would also block Agent F. `qa-goldfish.md` also has Bash, which is a write path, and its body text contradicts the plan. A `PreToolUse` hook that checks the agent type is the workable mechanism (the audit hook already records `agent_type`).
5. **The Phase 2 gate uses a delisted stock in a month it did not trade** (error 2 above).
6. **The Phase 1 gate depends on code that does not exist until Phase 3** (error 4 above).

## Major (by theme)

**Evidence and checks**
* Check 3 is circular: it tests the arithmetic of the same reference price that builds the factor, and contradicts the Goal's "independent source". Pass on agreement with FinMind `DividendResult` plus a completeness check for large moves with no event. Yahoo is excluded with an unsupported reason. (S7, S8)
* Check 1 and check 2 are partly circular: listed days and last trading days come from the files being audited. Independent references exist in the research. (S7, S8)
* Check 4 states unverified premises (FinMind derives from exchange data, both report two decimals) and its 99.9% rule means zero mismatches at 500 samples. (S7)
* The universe depends on one undocumented endpoint with a long fallback chain. S1 should decide between two outcomes only. (S5, S8)
* Evidence gaps: 2015-03 to 2015-12 and the pre-2020 TPEx era were never sampled, TPEx next-day limit columns are not mapped, the benchmark 0050 has no stated construction and may have had a share split not covered by the event sources, and `corporate_actions` has no split or par-value type. (S7, S8)
* The calendar has a single source (FinMind). (S7)

**`available_at` and data semantics**
* One conservative rule serves both feature joins and tradability masks. For disposition and attention it can make a restriction visible after its first session. Keep `available_at` for features and add an explicit mask contract on the exchange's `start_date`/`end_date`. (S5, S7)
* The ex-date lag creates a fake drop between ex-date open and day 3 08:30. (S7)
* First-reported-wins can make known-bad source data permanent, since FinMind corrected history in place in 2026. The risk is narrower than first stated, because the initial full fetch already postdates those fixes. It matters on a later re-fetch. A per-dataset restatement class and two named views would settle it. (S5, S7, S8)
* The snapshot job cannot test the `available_at` rules it is credited with testing. A one-off timing spike polling at fixed clock times would. (S7)
* Identity is keyed on `stock_id` alone despite code reuse. The ISIN is available in `MI_QFIIS`. (S5)
* "Decision 2: one conservative rule" is contradicted by four timings in the table. (S7)

**Operations and resilience**
* The response classifier mishandles empty range responses, TPEx 302 redirects and some status codes, and the rules conflict (any 4xx stops, 429 is transient). (S6, S7, S9)
* A single drift stops the whole unattended run. Lane isolation is the opposing view to a simple stop-and-report. (S5, S8)
* Irreplaceable daily snapshots share a deferred backup decision with replaceable bulk data. Raw-cache loss is rated Low with no mitigation in effect. (S5, S7)
* The snapshot job covers about 12 sources, and only three have a named consumer. It is also sequenced after the Phase 0 gate although each lost day is permanent. (S8, S9)
* Fetching `TWT84U`, `MI_QFIIS` and `chtm` daily costs more than the month-end ranking and checks need. (S5)

**Scope and altitude**
* Phase 2 builds about 14 FinMind datasets before any seed hypothesis needs them. This conflicts with the plan's section 6.6 agent split, so it is an author choice. (S5, S8)
* The append-only versioned clean store is heavy when raw is already immutable. (S5)
* The client stack (limiter, breaker, classifier, manifest, shards) is a framework to build before any data flows. (S5)

**Plan completeness (Stage 9)**
* Dependencies, test cases, the CLI contract and the file boundary are incomplete. Datasets with no module: `trading_calendar`, `dividend_announcements`. Yahoo has no client. The data dictionary has two writers and `ingest-worker.md` is not in the Modify list. Pass conditions are vacuous ("zero failing keys or listed exceptions"). The Phase 1 gate needs live data, so phases are not offline-buildable. The improve loop is undefined. The 17,000-response figure and the "14 datasets" are not derived or listed.

**Comprehension (Stage 6)**
* A cold reader cannot tell which list is authoritative, the checks or the Goals. `available_at` is defined as "first known" but the rules are conservative upper bounds. The request-budget arithmetic is not shown. Several research-dependent terms are undefined (`F-`, `KY`, `chtm`, lots, disposition, full-delivery).

## Nits

Roughly 60 across the stages: glossary placement, heading names, rhetoric and unsourced claims, vague qualifiers, naming (`tradingcal.py` and dictionary files named by agent letter), test-case dates without years, tie-break direction, tooling details, and duplicated statements. They are listed in the stage reports.

## Decisions for the author

1. **What is this document?** Option A: an approval document with phase gates, ownership and acceptance criteria. Detailed interface specs, file lists and test vectors move to Phase 0 task notes owned by the Lead, and the zero-decision rule is applied there. Option B: the full zero-decision plan, with interface specs added here, which makes the design longer. The two stage groups disagree and this sets how I revise.
2. **Failure behaviour:** simple stop-and-report with fewer response classes (Stage 5 zoom-out), or independent lanes per host and dataset with a dead-letter ledger (inventive catalyst).
3. **Phase 2 breadth:** build all agent C, D and E datasets as plan 6.6 says, or only the seed-hypothesis datasets first and the rest as schema entries.
4. **Check 1 reference:** keep the full collection-set FinMind price pull as the independent listed-day reference, or sample only and accept that check 1 cannot see a missing row inside a stock's listing span.
5. **Snapshot scope:** all about 12 sources, or only those that close a named gap.

## Recommended order of work

1. Correct the 11 errors above (all mechanical).
2. Resolve the validation-write mechanism (hook on agent type) and add it to the author prerequisites. Do not edit `.claude/`.
3. Make decisions 1 to 5 above.
4. Fix the circular checks (3 and 1), the first-reported policy, the mask contract, and the classifier rules.
5. Run the three missing spikes (2015 and pre-2020 TPEx sampling, 0050 corporate actions, same-date `MI_QFIIS` coverage) and record results.
6. Re-review.

## Traceability matrix

| Consolidated item | Source findings |
| --- | --- |
| Error 1 (`MI_QFIIS` gap) | S7 style, S8 Major |
| Error 2 and Blocker 5 (gate month) | S9 Blocker (three reviewers) |
| Error 3 (worked example) | S6 #7, S7 design, S9 style |
| Error 4 and Blocker 6 (Phase 1 gate) | S9 Blocker |
| Error 7 (wall-clock) | S5, S7, S8, S9 |
| Blocker 4 (deny rules) | S9 readiness and codebase-details |
| Check 3 circular | S7 design and style, S8 |
| Check 1, 2 circular | S7 design, S8 |
| Lane isolation versus stop | S5 inventive-catalyst and zoom-out, S8 |
| Phase 2 breadth | S5, S8 |
| Detailed-plan altitude | S5, S8 versus S9 Blockers 1 to 3 |
| Snapshot scope and sequence | S5, S7, S8, S9 |
| 0050 and splits | S7 design, S8 |
| Identity and ISIN | S5, S7 nit |
| First-reported policy | S5, S7, S8 |
