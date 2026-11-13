# Goldfish Review Report

**Target:** `/home/ken/tw0050/docs/designs/data_platform.md` (`lines 322-388`, Detailed Implementation Plan to end of file)

## Reviewer Status

| Reviewer | Status |
| --- | --- |
| `egm-implementation-readiness` | completed |
| `egm-codebase-details` | completed |
| `egm-style` | completed |

Severity totals after deduplication: 6 Blocker, 17 Major, 12 Nit.

Verdict: not implementation-ready. Several design choices are left to implementers, and some gates cannot pass as written.

Notes on evidence: the implementation-readiness reviewer did not open `qa-goldfish.md` or `ingest-worker.md`. The codebase-details reviewer did, and its findings on those files are the verified ones. The codebase-details reviewer did not read `finmind_findings.md` in full.

## Prioritized Findings (Blockers -> Major -> Nits)

### Phase 0 modules have no interface spec - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `335-337` (Phase 0); `359` (CLI)
* **Discrepancy Description**: The `common/` and `clients/` modules are listed by file name only: `timeutil`, `parsing`, `tradingcal`, `schema`, `paths`, `config`, `base`, `limiter`, `rawcache`, `finmind`, `twse`, `tpex`, `cli`. There are no signatures, return types, error types, or era-registry format. Nothing states how a response class is surfaced, how the `qa` cache namespace is selected, or how `settings.yaml` is loaded. Agents A to F code against these in parallel. The limiter and breaker tests (368-369) also need an injectable clock, which `limiter.py` is not said to have.
* **Rationale & Recommendation**: Add a per-file spec (public functions, signatures, inputs, outputs, errors) for at least `clients/base`, `rawcache`, `limiter`, `tradingcal`, `timeutil`, `schema`, `paths`, `config`. Include the injectable clock.

### Ingest, universe and validate modules have no actionable steps; clean-table schemas left open - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `341`, `347`, `353`; table spec `188-191`, `197`
* **Discrepancy Description**: Phase 1 only says `daily_official.py` "collects prices_raw, shares_issued and limit prices". There is no endpoint parameter list, per-era field mapping, partition detail, first-reported view SQL, `adjusted_as_of(t)` signature, `classify.py` or `build.py` API, or check-function interface and report format. Tables for `shareholding`, `valuation_ratios`, `margin`, `day_trading`, `securities_lending`, `fx`, `rates` and `futures` say "exact columns when their module is built". The snapshot tables (`TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap*`, TPEx `warning` and `sprc`) have no names, columns or primary keys. `financials` leaves its item vocabulary open. This breaks the Zero-Decision Rule.
* **Rationale & Recommendation**: Per module, list source endpoint or dataset, column mapping with dtypes, key, and the `available_at` rule reference. Add snapshot table definitions. Alternatively make a recorded schema spike, approved by the Lead, the first step of each Phase 2 agent.

### Spikes S1-S6 have no task list, location or follow-through - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** `324`, `337` against `78-84`
* **Discrepancy Description**: The spikes have exit criteria but no scripts, paths or amendment steps. Outcomes change the design (S1 shares-issued fallback chain, S2 `limit_up`, S4 classifier rule, S6 `stock_info`). Spike code could land in `src/` and break the file boundary.
* **Rationale & Recommendation**: List spike script paths (for example `scripts/spikes/`), the design section each amends, and make each result a gate for its dependent modules.

### Validation-write permission mechanism cannot work as written - Severity: Blocker
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `326-331` (especially `328-329`)
* **Discrepancy Description**: `.claude/settings.json` deny rules are project-wide and do not distinguish agents. Denying `Edit(src/twdata/validate/**)` and `Edit(tests/validate/**)` would also block Agent F, which must write there. Rule strings are not given, and `Write` and Bash redirects are not covered. `qa-goldfish.md` has `tools: Read, Grep, Glob, Bash`, so Bash is already a write path and "F has no write tools" (328) is only partly true. Its body says "You may not edit anything under `src/`" and "Write findings only where the lead tells you", which contradicts the plan. F must also write `docs/COVERAGE_REPORT.md` and `docs/QA_FINDINGS.md`.
* **Rationale & Recommendation**: Replace the deny-rule step with a `PreToolUse` hook (DATA_COLLECTION_PLAN.md section 11.2 already mentions hooks) that reads the agent type and permits those paths only for `qa-goldfish`. Specify the exact edit to `qa-goldfish.md` (tools line, body text, Bash restriction) and test the mechanism before Phase 3.

### Phase 2 gate uses stock 2475 in 2020-06, when it was delisted - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`, `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** `349`, `383`
* **Discrepancy Description**: `twse_findings.md:87` and `FINMIND_DATASETS.md:56` show 2475 delisted 2019-05-13, last traded 2019-05-10. A 2020-06 run returns no rows, so the delisted-name path is never exercised and "no duplicates" is meaningless for an empty result. Agent E datasets (`us_prices`, `fx`, `rates`, `futures`) and B's `benchmark` are not per stock. 6488 is TPEx and the seed universe and data directory for the temporary run are undefined.
* **Rationale & Recommendation**: Use a month when the delisted stock traded (2019-04 for 2475, or 2016-11 for 3474), or two months. Add a TPEx stock listed in that month. Define the sample per agent, pre-seeded inputs, and expected row counts for at least one dataset. The month must fall in the window used by B to E.

### Phase 1 gate depends on check 8, which does not exist until Phase 3 - Severity: Blocker
* **Reviewer Lens:** `egm-codebase-details`, `egm-style`
* **Affected Scope:** `343` against `263`, `353`
* **Discrepancy Description**: The gate is "check 8 passes on a full run". Check 8 is `check_08_universe.py`, owned only by F (263) and built in Phase 3.
* **Rationale & Recommendation**: Give Phase 1 a check A or the Lead can run (for example a `universe/build.py` self-assertion: 200 members per month-end, 2330 present). Or build check 8 first and reorder.

### Stale prerequisite makes the Phase 0 gate unpassable - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** `331`, `337`; decided at `94`, `103-104`
* **Discrepancy Description**: Line 331 lists the snapshot schedule and backup location as open author decisions. The schedule is decided (manual daily command). The author deferred the backup location, with `backup_dir` unset and reported by QA at each gate. The gate requires "the author prerequisites are done".
* **Rationale & Recommendation**: Drop the snapshot schedule from 331. Reword the backup item to "`backup_dir` may stay unset; QA reports it" and keep it out of the gate.

### Adjusted-close worked example contradicts the `available_at` rule - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** `222`, `373` against `210`
* **Discrepancy Description**: Corporate-action `available_at` is the next trading day 08:30 after the ex-date. With the ex-date on day 2, an as-of query at day 2 08:30 returns 100, not 95.
* **Rationale & Recommendation**: Change both lines to day 3 08:30 and add the expected value just before that time (100).

### Pass conditions are vacuous or inconsistent - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** `355`, `384`; thresholds `66-69`
* **Discrepancy Description**: Line 355 says "zero failing keys". Line 384 adds "or listed exceptions". The Phase 3 gate "all pass, or failures go to QA_FINDINGS" always passes. Check 1 passes at 99% and check 4 at 99.9% by design, and check 3 treats Yahoo `Adj Close` as a non-pass comparison.
* **Rationale & Recommendation**: State one pass condition per check by pointing to the Acceptance checks thresholds. Keep the escalation path separate. Delete "zero failing keys".

### Collection time estimate conflicts with the request budget - Severity: Major
* **Reviewer Lens:** `egm-style`
* **Affected Scope:** `384` against `161-168`, `278`
* **Discrepancy Description**: The budget implies about 18.5 hours (8 for the universe pass plus 10.5 for FinMind, which starts after the universe). Line 384 says about 12 hours.
* **Rationale & Recommendation**: Correct the figure here and at 168 and 278, or state the overlap assumption.

### Yahoo cross-check has no client, owner or `qa` namespace - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`, `egm-codebase-details`
* **Affected Scope:** `353`, `335`, `258`
* **Discrepancy Description**: F fetches Yahoo `Adj Close` "through the Lead's clients and a `qa` cache namespace". Only `finmind`, `twse` and `tpex` clients are listed, and the `qa` namespace is defined nowhere. `yfinance` versus a REST client is undecided.
* **Rationale & Recommendation**: Add `clients/yahoo.py` to Phase 0 and the ownership table, or say F writes its own fetcher under `src/twdata/validate/`. Define the `qa` namespace in the raw-cache section.

### Spike results recorded in one file regardless of source - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-implementation-readiness`
* **Affected Scope:** `337`
* **Discrepancy Description**: All spike results go to `docs/OFFICIAL_SOURCES.md`, but S4 to S6 concern FinMind. The Lead is the writer of a file also used as a research record.
* **Rationale & Recommendation**: Name the file per spike, or define one spike log, and reflect it in ownership.

### Parsing test cites a sign format with no evidence - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** `367`
* **Discrepancy Description**: `<p style= color:green>-</p>` giving -1 and red `+` giving +1 appear nowhere in `docs/` or `docs/research/`. The "leading tab in a name" case is also unevidenced. Handling of unchanged ("X" or blank), `--` placeholder variants, negatives and TPEx date formats is undefined.
* **Rationale & Recommendation**: Cite the fixture or research file, or mark "to be confirmed from the `MI_INDEX` fixture" and add it to a spike. Add the missing cases with expected outputs.

### Response-class and status handling disagree - Severity: Major
* **Reviewer Lens:** `egm-style`, `egm-codebase-details`
* **Affected Scope:** `226`, `228`, `368`, `370`
* **Discrepancy Description**: Line 368 treats non-OK `stat` on a trading day as `drift`, but 228 does not list it (`twse_findings.md` shows `STOCK_DAY` returning non-OK `stat` for months with no data). Line 226 stops the run on any 4xx, but 370 tests only 401, 402 and 403, and FinMind `TokenIllegal` is a 400. 429 is transient (228). Exit code 4 versus the breaker stop (229) is unclear for a failed half-open probe. TPEx lowercase `ok` and 302 to `/errors` are untested, and 302 is unclassified.
* **Rationale & Recommendation**: Reconcile 226 and 228, then test 400, another 4xx, 429, lowercase `ok`, 302 and the breaker exit code.

### Data dictionary has two writers and `ingest-worker.md` is not updated - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** `347` against `.claude/agents/ingest-worker.md:12`, plan section 6.6
* **Discrepancy Description**: The design has A to E write `docs/data_dictionary/{a..e}.md` with the Lead owning an index. `ingest-worker.md` tells each worker to write "your section of `docs/DATA_DICTIONARY.md`" plus a run report in `audit/runs/`. `ingest-worker.md` is not in the Modify list, `audit/runs/*` is in no file boundary, and the index timing is unstated.
* **Rationale & Recommendation**: Add `ingest-worker.md` to Modify with the exact change. List `audit/runs/<date>_<agent>.md` and when the Lead builds the index.

### File boundary is incomplete for a write allowlist - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `335`, `347`, `359`, `361-363`
* **Discrepancy Description**: Missing or unowned files: `src/twdata/__main__.py` (needed for `python -m twdata`; only a console entry point is declared), the clean-table writer (`run-*.parquet`, `v<N>`, pointer), state and manifest writer, quarantine handling, DuckDB views (first-reported, revisions, `adjusted_as_of`), `status --verify`, per-source parsers, `data/` creation, `.gitignore` entries, `docs/ITERATION_LOG.md`, `docs/DATA_DICTIONARY.md`, Gitleaks config, and test package files and conftests. Phase 0 creates no tests although its gate is "pytest passes offline". Brace and template paths (`test_ingest_<module>.py`, `test_check_0{1..8}.py`, `{a,b,c,d,e}.md`) are not literal. Fixture filenames and format are unspecified. No guard stops a fixture subdirectory named `data/`.
* **Rationale & Recommendation**: Give one consolidated list per phase with literal paths marked Create, Modify or Delete, including docs, config and hooks, and a per-phase test list.

### Datasets with no ingest module - Severity: Major
* **Reviewer Lens:** `egm-codebase-details`
* **Affected Scope:** `335-341`
* **Discrepancy Description**: `trading_calendar` (FinMind calendar) is read by `tradingcal.py` but fetched and stored by nothing, yet `valid_empty` and every `available_at` rule depend on it. `dividend_announcements` is in no phase.
* **Rationale & Recommendation**: Assign each an exact module and agent.

### CLI and ingest-module contract undefined - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `359`
* **Discrepancy Description**: No dataset-name registry or run signature maps `fetch --dataset NAME` to A to E modules, though the Lead owns `cli.py`. Valid names are not enumerated. Output and side effects of `status`, `status --verify`, `rebuild-universe` and `snapshot` catch-up are unstated. Per-stock datasets have no stated source for the stock list. Exit code 1 is unspecified. `--data-dir` exists only on `fetch`, yet the Phase 2 gate needs a temporary directory for the other commands. Line 235 copies `data/raw/` after each phase gate with no command.
* **Rationale & Recommendation**: Add a module contract, registry and global `--data-dir`. Define each command's output, and say whether the copy is manual.

### Dependencies and tooling not chosen - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`, `egm-style`
* **Affected Scope:** `335`, `381`
* **Discrepancy Description**: `pyproject.toml` lists no runtime or dev dependencies (`duckdb`, `pyarrow`, `requests`, `urllib3`, a YAML library, `pytest`, `ruff`, a fake-clock or HTTP-mock tool). `requirements.lock` from `pip freeze` is circular without them, and the interpreter is not pinned. The setuptools `src` layout needs `packages.find where = ["src"]`. The ruff and Python choices have no recorded decision, and the Phase 0 gate does not run `ruff`.
* **Rationale & Recommendation**: List dependencies and test tooling. Add `ruff check` to the Phase 0 gate or point to the Verification Plan.

### Test plan has missing and under-specified cases - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `365-375`
* **Discrepancy Description**: Line 365 promises inputs and expected outputs but many cases give none (limiter spacing for 600 per hour, what a probe "succeeds or stops" means, raw-cache resume request list, "a synthetic dataset with a known gap" per check). Missing cases: first-reported and revisions views, `v<N+1>` pointer switch, atomic state write, manifest and `status --verify`, PK-uniqueness failure, snapshot catch-up and missed-day report, carry-forward up to 10 days, null market cap, `limiter-check`, exit codes 2, 3 and 4, quarantine, `ok` and `valid_empty` classes, era registration, 40-day boundary on both markets, suspended days as missing, 99% coverage rule, watchlist rows, 2330 always present, exact-200 case, and a tie on market cap.
* **Rationale & Recommendation**: Add these with inputs and expected outputs.

### Phase 1 gate needs live data, so phases are not offline-buildable - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`
* **Affected Scope:** `343`, `363`
* **Discrepancy Description**: The Phase 1 gate is a full run (about 8 to 12 hours of network use) with unclear ownership. Fixture-based per-module tests do not gate the phase.
* **Rationale & Recommendation**: Split into an offline fixture gate and a live gate with an explicit owner and procedure.

### Snapshot work is sequenced before its dependencies and schema - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** `341`, `238`
* **Discrepancy Description**: `snapshots.py` is built first in Phase 1 but depends on Phase 0 clients, the calendar and snapshot table schema (`snapshot_date`, `first_seen_at`), which is not in the table list at 176-195. One table per source versus one generic table is unstated.
* **Rationale & Recommendation**: State the order of the Phase 0 gate and snapshot start, because each lost day is permanent, and add snapshot table definitions.

### Phase 3 improve loop not actionable - Severity: Major
* **Reviewer Lens:** `egm-implementation-readiness`, `egm-style`
* **Affected Scope:** `353-355`
* **Discrepancy Description**: "At most three rounds" has no log format, no statement of who fixes failures (the Lead spawns owners by tag) and no recheck procedure. "The improve loop" is defined only in plan section 6.2, step 5, and not in the terms list. The spawn prompt for F (fresh context) is not specified.
* **Rationale & Recommendation**: Specify the fix-and-recheck procedure, log format and F's spawn inputs. Add a one-line definition of the loop.

### Nits - Severity: Nit
* **Reviewer Lens:** `egm-style`, `egm-implementation-readiness`, `egm-codebase-details`
* **Affected Scope:** various
* **Discrepancy Description / Recommendation**:
  * `347`: dictionary files named by agent letter. Use content names such as `prices.md`.
  * `363`, `300 KB` fixture cap: a TWSE daily file is about 150 KB and TPEx `attention` is 895 KB per year. State how oversize fixtures are trimmed. Trimming changes sha256 and shard format.
  * `372`: "the 9-day Lunar New Year break" names no year, and "a revenue month whose 10th is a Saturday" names no month. Name them.
  * `374`: tie-break "turnover then `stock_id`" lacks direction. State descending turnover and ascending `stock_id`, or the intended order.
  * `382`: "Every parser has at least one test" has no tool or threshold, and "coverage requirement" collides with data coverage. Use "test coverage requirement" and name a tool (for example `pytest-cov`).
  * `381`: `ruff check src tests` omits `ruff format --check` although a line length is configured.
  * `383`: "no network beyond the clients" is vague. Use "all network access goes through `clients/`". State whether A is exempt from the small integration run.
  * `324`: "No modelling, backtesting or trading code is included" repeats lines 11 and 53, and "machine setup" matches no listed item. Drop both.
  * `335`: a long one-sentence file list mixing tool settings and file names. Split into a list.
  * `340-341`: snapshot order dependency (see Major finding).
  * `353`: F's spawn prompt must supply the client layout and fixtures, though F has fresh context.
  * `359`: exit code 3 "on a block or auth error" omits the circuit-breaker stop at 229.
