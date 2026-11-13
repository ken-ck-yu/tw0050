# Taiwan Data Platform (Phase 1: data collection)

*   **Author:** ken-ck-yu
*   **Status:** Draft
*   **Date:** 2026-11-13

--------------------------------------------------------------------------------

## Overview

This design covers the local data layer for a research project that tests whether a machine-learning strategy, holding Taiwan stocks for roughly 2 to 10 trading days, earns a real edge after costs. Phase 1 collects and validates data only. It contains no modelling, backtesting, broker or trading code.

The platform collects prices, corporate actions, fundamentals, investor flows and macro series for TWSE and TPEx common stocks from 2015-06-01. It stores them as Parquet files on local disk, queried with DuckDB. Every table records when a value could first have been known to a trader, so later research cannot see the future.

Sources are FinMind (free tier, 600 requests per hour) and the free TWSE and TPEx official endpoints. The official endpoints replace the three FinMind datasets that need a paid tier (`docs/FINMIND_DATASETS.md`, `docs/OFFICIAL_SOURCES.md`).

## The Problem

A strategy test is only as honest as its data. Four things commonly make Taiwan backtests look better than reality:

1.  **Lookahead.** Monthly revenue, quarterly financials and exchange-published flows are known only after a delay. A table keyed on the period they describe lets a model use them early.
2.  **Survivorship.** A universe built from today's listed stocks leaves out names that were delisted, and those names tend to have done badly.
3.  **Untradable prices.** Adjusted prices that are wrong, or trades at limit-locked or disposition-restricted prices, produce returns nobody could have earned.
4.  **Unreproducible inputs.** Free sources can change or overwrite history without notice, so a result cannot be rerun.

The free tier also leaves gaps: no adjusted prices, no capital-reduction reference prices, no market cap, and no filing dates for quarterly financials. Several useful official sources (disposition and attention lists, borrowable shares) publish only a latest snapshot, so their history can only be built by collecting daily from now on.

This design proposes one storage layout, one table convention (`event_date` plus `available_at`), one set of source clients with rate limiting and raw caching, and one point-in-time rule per dataset. A separate QA agent checks the result against official figures.

## Goals

*   Every clean table carries `event_date` and `available_at` (Asia/Taipei). No row has `available_at` earlier than `event_date`. Every dataset has a written rule for how `available_at` is set, and the share of rows that used a fallback rule is reported.
*   Daily prices exist for at least 99% of trading days for every universe member-month, from 2015-06 onward, including stocks later delisted.
*   `universe_membership` has exactly 200 stocks per month-end (the top 200 by market cap after a NT$20M 60-day median turnover floor, plus flagged watchlist names), and 2330 is always present.
*   Adjusted prices are built in-house from raw prices and official ex-rights and capital-reduction events, and match an independent source within a stated tolerance on a sample of 20 stocks.
*   Ingestion is idempotent and resumable: a rerun fills gaps and creates no duplicate rows. Every API response is cached raw before it is parsed.
*   No paid FinMind tier is needed for the P0 and P1 datasets. The design lists what a paid tier would add.
*   Request rates respect each source's limit. The FinMind limit is read from its user-info endpoint at start-up. A token or permission error stops the run and reports.
*   Nothing in git contains the token or data files.

## Non-Goals

*   Feature engineering, modelling, backtesting, broker or order code (plan section 8).
*   News, forums, broker-branch data, and tick or intraday data.
*   A database server, cloud storage, or any storage other than local Parquet and DuckDB.
*   Paying for a data tier. That needs the author's approval.
*   Live or near-real-time collection. Phase 1 is daily batch.
*   Recovering historical values for snapshot-only sources. They start collecting at approval and have no earlier history.
*   Employer account-dealing rules. These are an open item for the later live-trading phase.

## Open Questions

*   **Undocumented endpoints:** the TWSE and TPEx `rwd` / `www` JSON endpoints are not in the official swagger files and can change without notice. What does the platform do when one changes shape or disappears (stop, fall back to FinMind, or mark the dataset stale)?
*   **Missing time of day:** disposition and attention lists have an announcement date but no time. TWSE and TPEx ex-rights tables and quarterly financials from FinMind and the official `t187ap*` endpoints have no publication timestamp. Decided: next trading day 08:30 (see Technical Plan). Open: whether that is too late to be useful for the status lists.
*   **Source independence:** decided that official TWSE/TPEx is primary for prices and corporate actions, with FinMind as the cross-check. Open: TWSE market cap uses FinMind shares issued with no independent check.
*   **Daily price `available_at`:** the plan does not say when a close becomes usable. The draft assumes trading date 18:00.
*   **Common-stock classification:** the rule for excluding ETFs, ETNs, TDRs, preferred shares and warrants from `TaiwanStockInfo` (industry category and code pattern) is not yet specified or tested.
*   **Unlocated endpoints:** the real paths for price-limit steps (`TWT84U`), TAIEX total return (`MFI94U`), suspended securities (`TWTAWU`) and altered trading (`TWT85U`) are unknown.
*   **FinMind benchmark `data_id`:** the exact FinMind `data_id` for TAIEX total return (cross-check for the `MI_INDEX` series) is unprobed.
*   **Shares issued history:** TWSE shares-issued history is unresolved (`t187ap03_L` is a current snapshot). TPEx quotes carry shares issued daily. Market cap for TWSE names depends on FinMind `TaiwanStockShareholding` unless a better source is found.
*   **TPEx capital reductions:** `exDailyQ` covers ex-rights and dividends. Whether it covers capital reductions is unconfirmed.
*   **Delisted names:** nothing has been probed for the last trading days of delisted stocks, which acceptance check 2 requires.
*   **US overnight tickers:** whether `USStockPrice` carries the full list (NVDA, AMD, AVGO, AAPL, MU, TSM, SOXX, QQQ, SPY, VIX) is unprobed.
*   **Throttling:** the official hosts' throttling behaviour is unknown because too few requests were made to trigger it.

--------------------------------------------------------------------------------

## Technical Plan (Architecture)

### Decisions made by the author (2026-11-13)

*   **Primary source for daily prices, ex-rights and capital reductions: official TWSE/TPEx** (option B). FinMind is the cross-check for these and the primary source for datasets the official endpoints do not offer.
*   **`available_at` when a source gives a date but no time: the next trading day at 08:30 Asia/Taipei** (option A), applied the same way to every such dataset.

### Data flow

```text
  FinMind API (600 req/h)      TWSE rwd / OpenAPI       TPEx www / OpenAPI
         |                            |                         |
         v                            v                         v
  +--------------------------------------------------------------------+
  | clients/: one client per host, each with its own rate limiter,     |
  | response validator and raw cache writer                            |
  +--------------------------------------------------------------------+
         | every response, unparsed
         v
  data/raw/<source>/<dataset>/        (Parquet: request, fetched_at, body)
         | parse (ROC dates, thousands separators, schema check)
         v
  ingest/<dataset>.py  -->  data/clean/<dataset>/year=YYYY/   (typed, deduplicated,
         |                                                      event_date, available_at)
         v
  universe/  -->  data/reference/universe_membership, collection_set
         |
         v
  validate/ (agent F, read-only on data)  -->  docs/COVERAGE_REPORT.md
```

### Source policy

| Data | Primary | Cross-check |
|---|---|---|
| Raw daily OHLCV, turnover | TWSE `MI_INDEX` and TPEx `otc` daily files (one request per day per market) | FinMind `TaiwanStockPrice`, 500 random (stock, date) closes |
| Ex-rights, ex-dividend, capital reductions | TWSE `TWT49U`, `TWTAUU`; TPEx `exDailyQ` | FinMind `TaiwanStockDividend`, `TaiwanStockDividendResult` |
| Adjusted prices | Built in-house from raw prices and the events above | Yahoo `Adj Close` on a sample of 20 stocks |
| Market cap | TPEx: `close` x shares issued from the daily file. TWSE: `close` x `NumberOfSharesIssued` from FinMind `TaiwanStockShareholding` | None yet (open question) |
| Disposition and attention stocks | TWSE `punish`, `notice`; TPEx swagger endpoints | None |
| Trading calendar, stock info, delistings | FinMind | TWSE `holidaySchedule`, `/company/suspendListingCsvAndHtml` |
| Monthly revenue, flows, margin, lending, day trading, PER, US prices, financials, macro | FinMind | TWSE `t187ap05_L`, `BWIBBU_d`, `t187ap06_L_*`, `t187ap07_L_*` where available |

`MI_INDEX` was checked against a saved 2015-06-01 response. Its per-stock table (919 rows) has code, name, volume, trade count, value, open, high, low, close, spread and PER. The up/down sign arrives as an HTML snippet and must be parsed. ETFs such as 0050 are in the same table and are excluded by the universe step. The same response has a total return index table that includes the TAIEX and Taiwan 50 total return indexes, so the benchmark index series comes from `MI_INDEX` daily with FinMind `TaiwanStockTotalReturnIndex` as the cross-check. 0050 itself is an ordinary row in the price table.

### Common table columns

Every clean table has: `event_date` (date), `available_at` (timestamp, Asia/Taipei), `source`, `source_dataset`, `fetched_at` (UTC), and `raw_ref` (path and row of the raw response). Stock-level tables add `stock_id` (string, never an integer) and `market` (`TWSE` or `TPEx`). Units are fixed per table and written in `docs/DATA_DICTIONARY.md`: prices in NT$, volume in shares (not lots), revenue in NT$ thousands.

### `available_at` rules

| Dataset | `event_date` | `available_at` |
|---|---|---|
| Raw daily prices | Trading date | Trading date 18:00 (design assumption: the plan does not set this) |
| Institutional flows, margin, lending, day trading | Trading date | Next trading day 08:30 (plan section 4) |
| Monthly revenue | First day of the revenue month | FinMind `create_time` when present. If blank: the 10th of the following month, rolled to the next trading day, 18:00. Fallback share reported |
| Quarterly financials | Period end | Actual filing date when found in MOPS. Otherwise the statutory deadline (Q1 15 May, Q2 14 Aug, Q3 14 Nov, annual 31 Mar), then the next-trading-day 08:30 rule |
| Dividend announcements | Announcement date | FinMind `AnnouncementDate` plus `AnnouncementTime` when present, else next trading day 08:30 |
| Ex-rights, ex-dividend, capital reductions | Ex-date or resumption date | Next trading day 08:30 after the source date. Adjustment factors are therefore not visible on their own ex-date |
| Disposition and attention lists | Source announcement date | Next trading day 08:30 |
| US prices | US trading date | US close converted to Taipei time, plus 30 minutes. Joined on timestamps, never on calendar dates |
| Stock info, calendar | Snapshot date | Retrieval time. Industry and name history is not recoverable, which is stated in the dictionary |
| Restatements | n/a | First-reported value kept. Raw cache keeps every retrieval, so later changes are detectable |

The next-trading-day 08:30 rule is conservative. For events published before the open it makes data appear later than it was knowable. That is the accepted trade-off.

### Rate limiting and failure handling

*   **FinMind:** the hourly limit is read from the user-info endpoint at start-up and sets the limiter. A token or permission error stops the run and reports. The token is read from `FINMIND_TOKEN`, sent as an `Authorization: Bearer` header, and removed from anything written to the cache or logs.
*   **TWSE and TPEx:** one request in flight per host, at least 5 seconds apart, with exponential backoff. Their endpoints answer HTTP 200 with an HTML error page when the path or parameters are wrong, so a response counts as good only if the body is valid JSON, `stat` is `OK`, and the field list matches the expected schema.
*   **Breakage:** a failed validation raises a schema-drift error for that dataset and stops that dataset. There is no silent fallback to another source. After 3 consecutive bad responses a host's client stops and reports, to avoid an IP block.
*   **Volume:** daily price files need about 2,800 trading days for each of the two markets, about 5,600 requests. At 5 seconds each that is about 8 hours of wall-clock time, run once and resumed from the cache.

### Idempotence and resume

Each ingest module records completed (dataset, key range) in `data/state/`. A rerun requests only missing ranges, upserts on the table's primary key, and never appends duplicates. Anything that would delete or overwrite collected data needs the author's approval.

### Universe

Rebuilt on the last trading day of each month from 2015-06, following plan section 2: all common stocks listed that day (including later-delisted), excluding ETFs, ETNs, TDRs, preferred shares, warrants, and stocks under full-delivery or disposition status as of that date. Then the NT$20M 60-day median turnover floor (a config parameter), rank by market cap, keep the top 200, and add `config/watchlist.yaml` names flagged `watchlist`. Output is `universe_membership` with one row per (month_end, stock_id) holding rank, market cap and turnover. The collection set is the union of all members.

### Modules and ownership

| Module | Contents | Owner |
|---|---|---|
| `src/twdata/clients/` | FinMind, TWSE, TPEx clients; limiter, raw cache, validators, ROC date and number parsing | Lead |
| `src/twdata/ingest/` | One module per dataset | Agents A to E, split as in plan section 6.6 |
| `src/twdata/universe/` | Universe construction | Agent A |
| `src/twdata/validate/` | Acceptance checks | Agent F only |
| `config/settings.yaml`, `config/watchlist.yaml` | Start date, liquidity floor, universe size, watchlist | Lead |

### Dependency order

Lead, then A (reference data, prices needed for universe), then B to E in parallel, then F. B's adjusted prices need A's stock list. C and D need A's collection set.

## Alternatives Considered

### Alternative A: FinMind primary, official data fills gaps

*   **Pros**: Typed, supported API. The 500-close check compares two independent sources without extra design.
*   **Cons**: The 600 requests per hour limit makes prices alone take about 7.5 hours at the limit, before any other dataset. Errors in FinMind price data are caught only on the sample.
*   **Reason for Rejection**: Rejected by author: the quota is the bottleneck, and the official bulk daily files need far fewer requests.

### Alternative C: ingest both sources fully and reconcile

*   **Pros**: Disagreements surface across all data. Either source can fail while the other keeps the table alive.
*   **Cons**: About double the storage and work for prices. The conflict rule is a design decision of its own.
*   **Reason for Rejection**: Rejected by author in favour of option B. This can be revisited if the sampled cross-check shows frequent disagreement.

### Alternative: per-dataset time rules for date-only sources

*   **Pros**: Closer to when a trader could have known the event.
*   **Cons**: Each rule is a guess about publication time that has not been verified against the exchange schedule. A wrong guess leaks future information and no acceptance check would catch it.
*   **Reason for Rejection**: Rejected by author: one conservative rule is easier to test.

### Alternative: real retrieval time going forward, conservative rule for history

*   **Pros**: True timestamps after approval.
*   **Cons**: Two timing regimes in one table. Research spanning the boundary mixes them.
*   **Reason for Rejection**: Rejected by author. Not ruled out for snapshot-only sources if their history is later judged too thin.

## Non-Functional Requirements

*   **Security and privacy:** `FINMIND_TOKEN` comes from the environment or a gitignored `.env` and is never printed, logged, cached or committed. Clients strip the `Authorization` header before anything is written. `data/` and `audit/events.jsonl` are gitignored. Gitleaks runs on commit.
*   **Rollout and rollback:** nothing is deployed. Collected data is rebuilt from `data/raw/`. Deleting or overwriting collected data needs the author's approval.
*   **Footprint:** raw responses for daily files are large (about 150 KB per TWSE day). Order of magnitude for the whole history is a few GB on local disk. Measure after the first year is collected, and report if disk becomes a constraint.

## Detailed Implementation Plan

Nothing below is built until the author approves the reviewed design. No modelling, backtesting or trading code is included.

### Primary keys

| Table | Primary key |
|---|---|
| `prices_raw` | (`market`, `stock_id`, `event_date`) |
| `corporate_actions` | (`market`, `stock_id`, `event_date`, `action_type`) |
| `prices_adjusted` | (`stock_id`, `event_date`) |
| `market_cap` | (`stock_id`, `event_date`) |
| `benchmark_index` | (`index_id`, `event_date`) |
| `status_events` | (`market`, `stock_id`, `status_type`, `announce_date`) |
| `monthly_revenue` | (`stock_id`, `revenue_month`) |
| `financials` | (`stock_id`, `period_end`, `statement`, `item`) |
| `flows_institutional` | (`stock_id`, `event_date`, `investor_type`) |
| `universe_membership` | (`month_end`, `stock_id`) |
| Other daily FinMind tables | (`stock_id` or series id, `event_date`) plus any sub-key in the source |

### Target Files to Create/Modify

#### 1. `pyproject.toml`, `requirements.lock` (Create)

*   **Type / Scope**: Build and dependencies.
*   **Proposed Changes**: Python package `twdata`. Dependencies: `pyarrow`, `duckdb`, `pandas`, `requests`, `pyyaml`, `tzdata`. Dev: `pytest`, `ruff`. Lock file pins versions so reruns are reproducible.

#### 2. `config/settings.yaml`, `config/watchlist.yaml` (Create)

*   **Type / Scope**: Configuration.
*   **Proposed Changes**: Settings: start date `2015-06-01`, liquidity floor `20000000`, universe size `200`, per-host minimum request spacing, timezone. Watchlist: list of entries with `stock_id`, `added_on`, `reason`. Ships empty.

#### 3. `src/twdata/common/` (Create: `timeutil.py`, `parsing.py`, `calendar.py`, `schema.py`, `paths.py`)

*   **Type / Scope**: Shared library. Owner: Lead.
*   **Proposed Changes**: `timeutil`: Asia/Taipei handling and the next-trading-day 08:30 rule, the 18:00 rule and the US-close conversion. `parsing`: ROC date to date, thousands-separator numbers, HTML sign snippets in `MI_INDEX`. `calendar`: trading-day lookup from the loaded calendar. `schema`: column and type definitions per table, the common columns, and the check that field lists match expectations. `paths`: raw, clean, reference and state locations.

#### 4. `src/twdata/clients/` (Create: `base.py`, `finmind.py`, `twse.py`, `tpex.py`)

*   **Type / Scope**: Source clients. Owner: Lead.
*   **Proposed Changes**: `base`: per-host limiter, backoff, circuit breaker (3 consecutive bad responses), validation of body, `stat` and field list, and the raw cache writer (request without credentials, `fetched_at`, HTTP status, body). `finmind`: reads the hourly limit from the user-info endpoint and sets the limiter, stops on token or permission errors. `twse` and `tpex`: endpoint wrappers for the paths in `docs/OFFICIAL_SOURCES.md`. The four unlocated endpoints (`TWT84U`, `MFI94U`, `TWTAWU`, `TWT85U`) get paths here only after they are found from the site's own requests.

#### 5. `src/twdata/ingest/` (Create: one module per dataset)

*   **Type / Scope**: Per-dataset ingestion, each idempotent and resumable. Owners follow plan section 6.6.
*   **Proposed Changes**:
    *   Agent A: `stock_info`, `delistings`, `trading_calendar`, `market_cap`, `status_events` (disposition and attention).
    *   Agent B: `prices_raw` (from `MI_INDEX` and TPEx `otc`), `corporate_actions` (`TWT49U`, `TWTAUU`, `exDailyQ`, FinMind dividends as cross-check), `prices_adjusted` (built from the two), `benchmark_index` (`MI_INDEX` total return table).
    *   Agent C: `monthly_revenue`, `financials`, `valuation_ratios`.
    *   Agent D: `flows_institutional`, `shareholding`, `margin`, `securities_lending`, `day_trading`.
    *   Agent E: `us_prices`, `fx`, `rates`, `futures`.
    *   Each writes `data/clean/<dataset>/year=YYYY/` with the common columns and updates `data/state/`.

#### 6. `src/twdata/universe/` (Create: `classify.py`, `build.py`)

*   **Type / Scope**: Universe construction. Owner: Agent A.
*   **Proposed Changes**: `classify`: marks common stocks and excludes ETFs, ETNs, TDRs, preferred shares and warrants, with the rule documented and tested against known examples (for example 0050 excluded, 2330 included). `build`: month-end rebuild (disposition status as of that date, turnover floor, rank, top 200, watchlist flag), writes `data/reference/universe_membership` and the collection set.

#### 7. `src/twdata/cli.py` (Create)

*   **Type / Scope**: Command line entry point. Owner: Lead.
*   **Proposed Changes**: Commands to run one dataset or a date range, show state, and run the limiter check. No command deletes data.

#### 8. `src/twdata/validate/` and `tests/validate/` (Create)

*   **Type / Scope**: Acceptance checks 1 to 8. Owner: Agent F only. No worker edits these.
*   **Proposed Changes**: One module per check, computed from data, and each reports the failing keys and the owning agent. Check 4 samples 500 (stock, date) closes between the official files and FinMind `TaiwanStockPrice`. Check 6 also reports the share of monthly revenue rows that used the fallback.

#### 9. `tests/` (Create: `test_parsing.py`, `test_timeutil.py`, `test_clients.py`, `test_ingest_*.py`, `fixtures/`)

*   **Type / Scope**: Unit tests for everything outside `validate/`. Owners: the author of each module.
*   **Proposed Changes**: Fixtures are small saved responses with no token and no personal data. Tests cover ROC dates, HTML sign parsing, the HTML-error-page-with-200 case, schema drift, rate-limit spacing, idempotent rerun, and each `available_at` rule including holiday roll-forward.

#### 10. `docs/DATA_DICTIONARY.md` (Create)

*   **Type / Scope**: Documentation. Each agent writes its own section.
*   **Proposed Changes**: Every table, column, unit, source, `available_at` rule, and caveat (volume in shares, revenue in NT$ thousands, snapshot-only history limits).

#### 11. `docs/COVERAGE_REPORT.md`, `docs/QA_FINDINGS.md` (Create)

*   **Type / Scope**: QA output. Owner: Agent F.
*   **Proposed Changes**: Coverage and gap listings; findings tagged by owning agent.

#### 12. `docs/ITERATION_LOG.md`, `docs/DECISIONS.md`, `docs/OFFICIAL_SOURCES.md` (Modify)

*   **Type / Scope**: Records. Owner: Lead.
*   **Proposed Changes**: Iteration log gets one entry per QA round. Decisions gets this design's choices (official-primary prices, next-trading-day 08:30 rule) after approval. `OFFICIAL_SOURCES.md` gets the `MI_INDEX` finding and the located paths.

#### 13. `audit/runs/<date>_<agent>.md` (Create, one per agent)

*   **Type / Scope**: Run reports. Each agent writes its own, using `audit/RUN_REPORT_TEMPLATE.md`.
*   **Proposed Changes**: Includes what in the instructions was missing, ambiguous or wrong.

### Verification Plan

*   **Compilation/Build**: `pip install -e .` succeeds from the lock file.
*   **Unit Tests**: `pytest tests/` passes, with recorded fixtures and no network.
*   **Static Analysis & Linting**: `ruff check src tests`.
*   **Test Coverage Requirement**: every `available_at` rule and every parser has at least one test, including the holiday and weekend roll-forward cases.
*   **E2E/Integration**: a one-month, five-stock run into a temporary data directory, executed twice to confirm no duplicates, then Agent F's checks 1 to 8 on the full data. Failing keys go to `docs/QA_FINDINGS.md`. At most three improve rounds, then anything still failing goes to the author with the evidence.


--------------------------------------------------------------------------------

*Drafted with EGM*
