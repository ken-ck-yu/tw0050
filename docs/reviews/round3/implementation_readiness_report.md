# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (lines 342-386, `## Detailed Implementation Plan` to end)

Scope note: this is an approval document. Interface specs, file lists, test vectors and tooling are deferred to Phase 0 specs under `docs/specs/`, so those deferrals are not flagged. Findings concern phases, gates, ownership, prerequisites and undeferred spec gaps. Line references are to the target file. Where reviewers rated a shared finding differently, the higher rating is used and the difference is noted.

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

## Severity Summary

25 findings after deduplication: 1 Blocker, 16 Major, 8 Nit. Verdict: not ready to approve as written. The phase structure (Lead, then A, then B to E in parallel, then F) is sound, and the request-budget arithmetic (8,529 and 5,686 requests, 18 to 19 hour critical path) and the delisting dates (2475 last traded 2019-05-10, 3299 last traded 2018-11-21) check out. The problems are gates that cannot be met or lack pass criteria, ownership that cannot be enforced, and decisions that should be made before approval.

## Prioritized Findings (Blockers -> Major -> Nits)

### 1. Phase 0 gate cannot be passed as written - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 355-357 (also 90, 158, 361)
* **Discrepancy Description**: The gate is labelled "offline" but requires "every spike result is logged". That includes S5 and S6, which lines 90 and 361 assign to agents C and A in later phases, and S10, which needs polling at several clock times on several trading days. It also requires the calendar diff between FinMind and the derived calendar. The derived calendar is the set of dates on which `MI_INDEX` and `otc` return rows (line 158), which needs the Phase 1 all-stock pass of about 8 hours. If it is built only from dates FinMind calls trading days, the diff cannot find days FinMind lacks. Fetching all roughly 3,000 weekdays is not in the budget at lines 170-179.
* **Rationale & Recommendation**: Split the gate into an offline part (tests, lint, spec review) and a live part. Write "spikes S1 to S4 and S7 to S10 logged, S5 and S6 deferred to their agents' gates". State how many days S10 polls. Move the calendar diff to the Phase 1 live gate, and either budget the all-weekday fetch or stop claiming the second source is independent.

### 2. Trading calendar ownership, dependency order and pre-2015-06 coverage - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 272, 275, 285, 361, 257, 179, 241
* **Discrepancy Description**: `trading_calendar` is listed under the Lead's `common/` and under Agent A's ingest. The response classifier (line 241) and every `available_at` rule need the calendar, but line 285 says E needs only Phase 0. The FinMind calendar probe starts 2015-06-01 (`FINMIND_DATASETS.md:73`), while collection starts 2015-03-02, so about 48 days (March to May 2015) have no calendar source. Zero rows on a trading day is drift, and "next trading day" rules would yield pending nulls.
* **Rationale & Recommendation**: Name one owner. Suggested split: the Lead loads the FinMind-based table in Phase 0 and states the source for 2015-03-02 to 2015-05-29, and A adds only the derived second source. Remove the duplicate listing and fix line 285.

### 3. Agent F write mechanism is under-specified and internally inconsistent - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** lines 249, 346-348 (and `.claude/agents/qa-goldfish.md`)
* **Discrepancy Description**: `qa-goldfish.md` lists tools `Read, Grep, Glob, Bash` with no Write or Edit, and the prerequisite does not say the `tools:` frontmatter must change. "Its Bash restriction" is undefined. A PreToolUse hook cannot reliably confine Bash writes (redirects, `python -c` and `duckdb COPY` bypass path checks), and F and all workers have Bash. F's `data/raw/qa/` fetches (line 249) are absent from the allowlist at line 348. `.claude/settings.json` and the hook script are not protected against Write or Bash edits (only `Edit(./.claude/hooks/**)` is denied), so F could alter its own guard. Whether the PreToolUse payload carries `agent_type` is unverified. It is unstated whether the Lead session is blocked. The author, not the Lead, must write the hook because the Lead cannot edit `.claude/hooks/`.
* **Rationale & Recommendation**: The rule that builders never grade their own work (CLAUDE.md rule 5) rests on this hook. Decide the mechanism before approval: state the tool change, give F Write and Edit limited to its paths, restrict F's Bash to a fixed command set, add `data/raw/qa/`, pytest cache and `__pycache__` to the allowlist, protect the hook and settings files, say who writes the hook, and confirm `agent_type` is available to PreToolUse.

### 4. Hook test belongs to no gate; prerequisites list contradicts itself - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** lines 346-351, 357, 371-375
* **Discrepancy Description**: The heading says the prerequisites come "before Phase 0 can pass". Line 348 says the hook is tested "before Phase 3". No gate lists the hook test, and the Phase 3 gate checks only the acceptance checks. Line 351 (`backup_dir`) is not a prerequisite and says it is "not part of any gate", yet lines 100 and 250 say QA reports it and copies happen at each gate. Passive voice leaves the owner open (author or Lead).
* **Rationale & Recommendation**: Put the hook test (F blocked outside its allowlist and workers blocked from validate paths, via both Write and Bash) in the Phase 0 or Phase 2 exit gate with a named owner. Move the `backup_dir` bullet to a one-line note. Name who performs each prerequisite.

### 5. Ownership among agents A to E cannot be enforced by the described mechanism - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 281, 348 (and `.claude/agents/ingest-worker.md`)
* **Discrepancy Description**: A to E all use the single `ingest-worker` agent type, so a hook keyed on agent type cannot stop B editing A's files. All workers have Bash. Lead-owned paths (`config/`, `common/`, `clients/`) are equally open to workers.
* **Rationale & Recommendation**: Either define per-agent types with per-agent hook allowlists, or make a mandatory gate step in which the Lead diffs each agent's commit against its Phase 0 spec allowlist and rejects out-of-scope paths. State which one.

### 6. Phase 2 live-gate window does not exercise Agent B's logic, has no assertions or owner - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** line 369 (also 161, 236)
* **Discrepancy Description**: The window 2018-10-01 to 2018-11-30 is justified by the 3299 delisting only. No split, capital reduction or `exDailyQ`/`revivt` event is named in it, so `corporate_actions` and `adjusted_as_of` may run on an empty table. The only assertion is "no duplicate rows in `as_first_seen`". Missing are expected row counts against the calendar and official files, expected-empty cases (for example no FinMind shares-issued rows for 3299), and a rerun rule (state complete means zero new files, since D4 is append-only). The gate has no named owner, unlike Phase 1.
* **Rationale & Recommendation**: Add a stock with an event inside the window or a second small window, state per-dataset pass assertions and the rerun rule, and name the owner.

### 7. 0050 split reference price has no gate - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** lines 355, 357, 236, 369, 382
* **Discrepancy Description**: 0050 is the benchmark of record, and `config/manual_corporate_actions.yaml` is the only source of its 2025 split factor. The exchange announcement is open Phase 0 work, but no gate requires the entry to exist, the 2018 window never exercises it, and check 3 samples 20 stocks so 0050 need not be in it. The announcement is a web fetch outside `clients/`, with no named obtainer. (Rated Nit by one reviewer, Major by two.)
* **Rationale & Recommendation**: Require a sourced yaml entry in a gate, add an offline fixture test that the 2025-06-18 adjusted close is continuous, include 0050 explicitly in check 3, and name who fetches the announcement.

### 8. Gates lack measurable pass criteria and exit conditions - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`, `egm-codebase-details`
* **Affected Scope:** lines 363, 369, 375, 179
* **Discrepancy Description**: The Phase 1 gate says the official pass "has run for one year, then for the full range", which is an activity. No year is named (it must cover the 60-day warm-up from 2015-03-02), nobody decides, and no criteria are given (zero drift stops, row counts, disk per year against line 298, universe dry run). No gate sits between the end of the full collection and F starting. Phase 2 gates omit the dictionary section (`docs/data_dictionary/<topic>.md`), run report (`audit/runs/`, CLAUDE.md rule 8) and one-commit-per-task (rule 9). The Phase 3 gate ("each check meets its own pass condition") conflicts with line 373, where failures after three rounds go to the author, and its outcome is undefined.
* **Rationale & Recommendation**: For each gate state what passes it, who decides, and what the author's acceptance means after round 3. Suggested: accepted failures are recorded in `docs/DECISIONS.md`. Add an exit condition for full collection (all `data/state/<dataset>.json` complete, run reports and dictionary sections present).

### 9. `chtm` ordering conflicts with the universe build - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** lines 261, 179, 363
* **Discrepancy Description**: Universe step 3 excludes stocks in TPEx `chtm`, which must therefore be fetched for all dates before the build. Line 179 says `chtm` finishes "in the background" after the universe exists, and the 8-hour universe pass lists only `MI_INDEX`, `MI_QFIIS` and `otc`. The `punish`, `disposal` and `exDailyQ` ranges needed for status events are likewise unplaced. The universe could be built, then change when these arrive.
* **Rationale & Recommendation**: Put `chtm` (and the needed status ranges) in the universe pass and keep only `TWT84U` in the background, or state that the universe is rebuilt as a new version. Make the Phase 1 gate say which datasets must be complete.

### 10. Critical-path figure is double counted and contradicts the "one unattended run" - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 369, 363, 179
* **Discrepancy Description**: Line 179 describes one staged run with an 18 to 19 hour critical path. Phase 1 already completes the roughly 8 hour pass, but line 369 says "The full collection (critical path 18 to 19 hours) follows" after Phase 2. The remainder is about 10.5 hours of FinMind plus the event endpoints and background tail. It is also unclear whether "official pass" includes `TWT84U` and `chtm`.
* **Rationale & Recommendation**: State the Phase 2 duration, or reword line 179 to say the run is split across Phases 1 and 2.

### 11. Spike ownership conflicts with path ownership and the clients-only network rule - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** lines 80, 90, 274, 281, 355, 361, 367, 382
* **Discrepancy Description**: S5 and S6 belong to agents C and A, but `scripts/spikes/` and `docs/spikes/` belong to the Lead and "no agent edits a path it does not own". Spikes make requests while line 382 says all network access goes through `clients/`. Line 361 ("S5's counterpart S6") is confusing. No gate requires S6 resolved before Phase 1 datasets or S5 before Phase 2.
* **Rationale & Recommendation**: Either the Lead runs S5 and S6 in Phase 0, or give C and A explicit spike paths. Add "S6 logged" to the Phase 1 gate and "S5 logged" to the Phase 2 gate. State whether spikes use `clients/`.

### 12. Improve loop and its escalation are incomplete - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** lines 373-375, 27
* **Discrepancy Description**: Failures in Lead-owned code (time rules, `clients/`, calendar, `config/`) are tagged "Lead", but the loop describes only re-spawning workers. The three-round cap is not defined as rounds or wall clock, and it is not stated whether a fix needing a refetch (potentially 18 hours or more) needs author approval. Nothing tests F's own checks, so a check that never fails goes undetected.
* **Rationale & Recommendation**: State that the Lead fixes its own findings and F re-runs, define the refetch rule, and add fault-injection fixtures under F-owned `tests/validate/`.

### 13. Lead's Phase 0 specs are not reviewed by the author or a named checker - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 17, 355-357
* **Discrepancy Description**: The specs hold retry counts, sanity caps, spacing, parameter defaults and `restatement_class` assignments. The design says the Lead checks them against the zero-decision standard, but the gate has no checker, pass criterion or author sight of them before agents build.
* **Rationale & Recommendation**: Add a spec review (for example a fresh Goldfish pass with a round limit) to the gate. Record semantics-affecting defaults in `docs/DECISIONS.md` (anything that changes data or `available_at`). Log any threshold change after the first sample so thresholds cannot drift to fit data.

### 14. Daily snapshot job: unlisted author duty, no gate, no backup - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** lines 253, 100, 61, 250, 351
* **Discrepancy Description**: The job starts in Phase 1, after the Phase 0 gate, and the author runs it by hand every trading day for weeks. This is not among the author prerequisites. No phase says when it ends, who verifies it at gates, or that continuity is checked at Phase 3. Missed days surface only through QA, and `status` warnings are read by no gate. `backup_dir` is unset, so the irrecoverable snapshot history is unprotected from day 1 (and line 351 conflicts with line 250).
* **Rationale & Recommendation**: List the daily run as an explicit author commitment, add "snapshot continuity" to each gate, and decide at least an interim local `backup_dir` for `data/raw/snapshots/` before approval.

### 15. Fixture capture has no owner - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 350, 379
* **Discrepancy Description**: Verification requires fixtures "one set per schema era per endpoint", but nobody is assigned to capture them and the prerequisite at line 350 covers only `.gitignore`. Eras are known from S9 (for example `otc` has three, `MI_INDEX` one).
* **Rationale & Recommendation**: Make fixture capture a Lead Phase 0 deliverable and list it in the gate. Also state who owns parsing the `MI_INDEX` return-index table (ingested by A, parsed by B for `benchmark_index`).

### 16. "Phase" terminology is overloaded - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** lines 1, 11, 61, 115, 253, 285, 295, 344-375
* **Discrepancy Description**: "Phase 1" means the whole data-collection project (title, lines 11, 60, 61), the implementation Phase 1 (Agent A) and the snapshot-job start (line 253). "Phase 2" means implementation Phase 2 (D8, line 115) and plan section 10's research phase. A reader cannot tell which is meant. (Rated Nit by one reviewer.)
* **Rationale & Recommendation**: Rename the implementation phases (for example M0 to M3) and update the cited lines. Keep "Phase 1" for the project.

### 17. Agent F inputs are stale and the acceptance checks live in the design - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`
* **Affected Scope:** lines 349, 373, 274, 279, 26 (and `qa-goldfish.md` line 8, plan sections 6.2 and 6.6)
* **Discrepancy Description**: `qa-goldfish.md` says F reads only `docs/DATA_DICTIONARY.md` and plan section 7, but the design uses per-topic files under `docs/data_dictionary/` plus a Lead-owned index (lines 274, 279). No phase says when the Lead writes the index, yet F needs it. The design's acceptance-check text (thresholds, "three delistings", check 3(b)) differs from plan section 7 and lives only in this document, so if F reads it, its context is not fresh. Plan sections 6.2 step 4 and 6.6 carry the old wording.
* **Rationale & Recommendation**: State that the `qa-goldfish.md` edit also changes F's inputs. Extract the checks to a Lead-owned file such as `docs/specs/acceptance_checks.md`, schedule the index, and name the deviation from plan 6.6.

### 18. `.gitignore` claim is inaccurate and the fixtures path is unnamed - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** line 350 (also 52)
* **Discrepancy Description**: `*.parquet`, `*.csv` and `data/` rules are in the project `.gitignore` (lines 7-9), not a "global" one. The fix needs a negation scoped to a named fixtures directory, which is not given, and fixtures in git sit awkwardly against line 52 ("Nothing in git contains ... data files").
* **Rationale & Recommendation**: Say "project `.gitignore`", name the path (for example `tests/fixtures/`) and state fixtures are the sole exception, or defer to the specs explicitly.

### 19. Tooling named in the gate and "zero-decision standard" undefined - Severity: Nit
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** lines 344, 357, 17, 355
* **Discrepancy Description**: The gate requires `ruff` clean, although tooling is deferred (lines 17, 344) and no `pyproject.toml`, ruff config, pytest config or Python version exists. "Zero-decision standard" is the acceptance test for the specs but is defined only in `docs/DECISIONS.md`.
* **Rationale & Recommendation**: Write "lint passes" and define the zero-decision standard in one line under "References and terms".

### 20. S10 and S5 have no decision rule or amender - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 87, 89, 217, 355
* **Discrepancy Description**: S10 gates `available_at` for `prices_raw`, `shares_issued` and `benchmark_index`, but the design does not say which result would change the 18:00 rule or who amends it.
* **Rationale & Recommendation**: State the decision rule and the owner of the amendment.

### 21. Redundant sentences in the section opening - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** line 344
* **Discrepancy Description**: The second sentence repeats line 11 and Non-Goals (line 56), and the third repeats line 17.
* **Rationale & Recommendation**: Keep only "Nothing below is built until the author approves the reviewed design."

### 22. Prerequisite bullet at line 348 is dense and asserts without evidence - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 348-349
* **Discrepancy Description**: One bullet of about 130 words mixes problem, mechanism and path list. "Already a write path" is informal, and the claim that project-wide deny rules cannot allow F while blocking others is stated as fact with no citation. Line 349 ("so the definition changes") does not say what changes.
* **Rationale & Recommendation**: Use three short statements (problem, mechanism, writable paths), cite documentation or a test for the claim, and write "the definition must be changed to write `docs/data_dictionary/<topic>.md`".

### 23. Wording and file names in the phase text - Severity: Nit
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** lines 361, 363, 253
* **Discrepancy Description**: "A runs S5's counterpart S6" is confusing (S5 is C's). "Classification" is undefined. `universe/build.py` and `snapshots.py` are file names in a document that defers file lists.
* **Rationale & Recommendation**: Write "A resolves S6 before building `stock_info` and `delistings`", use "common-stock classification", and use module or step names.

### 24. Gate formatting, cross-references and Phase 3 omissions - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** lines 351, 373, 375, 380-382
* **Discrepancy Description**: Gate formats differ by phase (one "Gate (offline)", two inline gates, plain "Gate:"). Line 351 lacks the bold lead-in the other bullets have. "The worked example above" (line 380) is over 140 lines up and unnamed. Line 381 says live gates have a named owner "in the Phase 0 specs", but only Phase 1 names one. Line 382 is a rule rather than a check (suggest a test that fails if a module outside `clients/` imports an HTTP library). Line 373 says F has "read access to data" but F also writes `data/raw/qa/`. Phase 3 omits F's `docs/COVERAGE_REPORT.md` and plan 6.2 step 6 (drift check against the approved design), which may be dropped silently.
* **Rationale & Recommendation**: Use a consistent two-line "Gate, offline / Gate, live (owner)" block per phase, name the section for the example, name every gate owner, make line 382 checkable, and restore or explicitly drop the omitted outputs.

### 25. Snapshot source count and worker run-report path - Severity: Nit
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 116, 164, 253 (and `ingest-worker.md`)
* **Discrepancy Description**: Line 164 lists 13 snapshot sources (TWSE 11, TPEx 2), but lines 116 and 253 say "about 12". `ingest-worker.md` tells workers to write run reports in `audit/runs/`, which is absent from their owned paths.
* **Rationale & Recommendation**: Fix the count in D9 and add `audit/runs/` to each worker's owned paths.

## Verified claims (no finding)

`.claude/agents/ingest-worker.md` and `qa-goldfish.md` exist as described. `settings.json` has no per-agent rules or PreToolUse hook. `audit.sh` records `agent_type`. Gitleaks is configured. `audit/events.jsonl` and `data/` are gitignored. The improve loop cap and `docs/ITERATION_LOG.md` match plan sections 6.2 and 6.3. Request-budget arithmetic holds. The Phase 2 window facts for 2475 and 3299 hold.
