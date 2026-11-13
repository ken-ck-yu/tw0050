# Goldfish Review Report (Stage 9: Implementation Readiness)

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 195-299`)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Process note: the first dispatch through `egm-synthesizer` returned without waiting for its reviewers and wrote no report. That run was treated as failed, not as a clean review. The three reviewers were re-dispatched directly (the one retry the skill allows) and this report was compiled by the lead from their returned text.

Verdict: **fails the Zero-Decision Rule.** An implementer would have to make schema, algorithm, rule and file-layout decisions.

| Reviewer | Blocker | Major | Nit |
| --- | --- | --- | --- |
| `egm-implementation-readiness` | 6 | 12 | 5 |
| `egm-codebase-details` | 3 | 22 (its summary says 17, its list numbers 4-25 as Major) | 4 |
| `egm-style` | 0 | 10 | 12 |

The raw per-reviewer findings are consolidated by theme in `consolidated_review_report.md`, which carries the traceability matrix.

## Blockers

### Agent F cannot create what the plan assigns it - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** Detailed Implementation items 8 and 11
* **Discrepancy Description**: The design has Agent F create `src/twdata/validate/`, `tests/validate/`, `docs/COVERAGE_REPORT.md` and `docs/QA_FINDINGS.md`. `.claude/agents/qa-goldfish.md` gives F only `Read, Grep, Glob, Bash` and says it may not edit anything under `src/`. (Verified by the lead against the file.)
* **Rationale & Recommendation**: Add a Modify entry for the agent definition, or reassign who writes the validation code. This touches `.claude/`, which is a human-gated area.

### Circular dependency between Agents A, B and D - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** dependency order (line 161), items 5 and 6
* **Discrepancy Description**: A (universe, `market_cap`) needs `prices_raw` (B) and TWSE shares issued (D). B and D need A's stock list or collection set. Nobody owns the all-stock first pass.
* **Rationale & Recommendation**: Define an all-stock fetch-and-parse stage with a named owner before A, then a collection-set pass.

### Universe cannot be built for the first months - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** items 6 and 2, Goal 3
* **Discrepancy Description**: A 60-day median turnover is undefined for 2015-06-30 (about 21 trading days exist). No earlier start or partial-window rule is given.
* **Rationale & Recommendation**: Collect prices from about 2015-03 for the window, keep clean-table start at 2015-06, and state the rule.

### Unresolved inputs feed implementation items - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** items 4, 5, 6 (TWSE shares issued, four unlocated endpoints, delisted last trading days, TPEx capital reductions, common-stock rule)
* **Discrepancy Description**: The implementer would have to decide the source or fallback for each.
* **Rationale & Recommendation**: Probe and record before approval, or state the concrete fallback and out-of-scope stubs.

### Adjusted-price algorithm not specified - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** item 5 (Agent B), Goal 3 tolerance
* **Discrepancy Description**: No factor formula, cumulative direction, capital-reduction handling, `action_type` values, factor columns, numeric tolerance, or sampling seed. Yahoo is named with no client or dependency.
* **Rationale & Recommendation**: Add an algorithm subsection with formulas and a worked example.

### `available_at` computation contradictory and incomplete - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** lines 117-132 as applied by items 3 and 9
* **Discrepancy Description**: Ex-date events become visible after their own ex-date with no stated consumer rule. MOPS has no client. Statutory-deadline weekend handling, the revenue "10th is a trading day" case, US DST and holidays, and the behaviour beyond the loaded calendar are unspecified.
* **Rationale & Recommendation**: A per-dataset table with exact computation and edge cases.

### Per-table schemas and the file boundary are not enumerable - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** items 3-9, primary-key table
* **Discrepancy Description**: Twelve datasets have no key or columns. Key columns (`announce_date`, `revenue_month`, `period_end`, `month_end`) are not mapped to `event_date`. Files are given as globs or dataset names, so no write allowlist can be derived.
* **Rationale & Recommendation**: List every path and owner, and every table's columns, dtypes, units and key.

## Major (grouped)

* **Phasing and gates:** no phases with exit criteria (readiness M1, codebase-details #4).
* **Test plan:** category list, no inputs or expected outputs; missing token-stripping, breaker, resume, universe and adjusted-price tests; no fixture sourcing; E2E names no month or stocks and contradicts "no network" (readiness M2, style M6, codebase-details #23).
* **Client contracts:** no signatures, cache layout, `state/` format, backoff and breaker parameters, user-info URL, or limiter algorithm (readiness M3, codebase-details #20, #24).
* **Cross-process safety:** parallel agents share hosts with no cross-process limiter or atomic-write rule (readiness M11).
* **Idempotence:** "upsert" on year-partitioned Parquet has no mechanism, conflicts with "first-reported value kept" and with the overwrite approval gate (readiness M12, style M10, codebase-details #10).
* **Ownership:** multiple writers to `DATA_DICTIONARY.md`, Lead-owned `schema.py` and `cli.py` that workers must extend (codebase-details #6, readiness M7).
* **Validation suite protection:** `.claude/settings.json` denies nothing under `src/twdata/validate/**` or `tests/validate/**` (codebase-details #7).
* **Missing implementation for stated commitments:** snapshot-only collection, MOPS, dividend announcements table, Yahoo and other cross-check fetchers (codebase-details #11, #13, #14, style M2, M3).
* **Schema drift across eras and units per source:** one 2015 sample vs 11 years; no per-source unit conversions (codebase-details #18, #19).
* **Request-volume model:** FinMind budget and concurrency not modelled (codebase-details #21).
* **Packaging:** Python version, build backend, lock tool, ruff rules; `pip install -e .` does not use the lock file (readiness M8, style M4, codebase-details #22).
* **Layout conflicts:** `reference/` versus `clean/year=YYYY/` partitioning (style M9); `.gitignore` blocks fixtures saved as `*.parquet` or `*.csv` (codebase-details #25).
* **Terminology and structure:** "author" used for both human approver and module author (style M8); open questions not placed at the steps they block (style M7); CLI grammar and exit codes absent (readiness M9); check pass criteria, seeds and report format absent (readiness M10, style M5).
* **Universe edge cases:** full-delivery source, tie-break, suspended days, fewer than 200 passing, `available_at` for `universe_membership` (readiness M6, codebase-details #15, #16).

## Nits (grouped)

File naming collisions (`calendar.py` shadows the standard library, run-report filenames collide on a second run), missing `__init__.py` and `conftest.py`, vague qualifiers ("small", "improve rounds"), item layout inconsistencies, undefined cross-references to the plan file, unconsumed endpoint wrappers, and decision-log entries not yet written.

## Note for the author

`egm-codebase-details` recommends editing `.claude/settings.json` and `.claude/agents/qa-goldfish.md`. The harness flagged that report for instruction-like text. Those are findings to decide on, not instructions, and nothing was changed.
