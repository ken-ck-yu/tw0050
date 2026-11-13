# Taiwan Data Platform (Phase 1: data collection)

*   **Author:** ken-ck-yu
*   **Status:** Draft, revision 3 (revised after review round 2 and the author's answers). Not yet re-reviewed or approved.
*   **Date:** 2026-11-13

--------------------------------------------------------------------------------

## Overview

This design covers the local data layer for a research project that tests whether a machine-learning strategy, holding Taiwan stocks for roughly 2 to 10 trading days, earns an edge after costs. Phase 1 collects and validates data only. It contains no modelling, backtesting, broker or trading code.

The platform collects prices, corporate actions, fundamentals, investor flows and macro series for stocks listed on TWSE (the Taiwan Stock Exchange) and TPEx (the Taipei Exchange, the over-the-counter market) from 2015-06-01. It stores them as Parquet files on local disk, queried with DuckDB. Every joinable table records the time a value is assumed to be known, so later research can join on that time and avoid using the future.

Sources are the free TWSE and TPEx official files and FinMind (free tier, 600 requests per hour). The official files build the universe, because they list every stock on every date including stocks later delisted. FinMind supplies the per-stock datasets for the collection set.

This is an **approval document**. It fixes the decisions, table schemas of record, ownership, phase gates and acceptance criteria. Interface specs, file-level lists, test vectors, tooling and parameter defaults are written by the Lead as Phase 0 task notes (`docs/specs/`) and checked there against the zero-decision standard before any agent builds from them.

### References and terms

*   [`DATA_COLLECTION_PLAN.md`](../../DATA_COLLECTION_PLAN.md): the project plan. This design builds on its sections 2 (universe rule), 4 (point-in-time rules), 6 (agent framework, including the improve loop in 6.2 step 5 and the agent split in 6.6) and 7 (acceptance checks).
*   [`docs/FINMIND_DATASETS.md`](../FINMIND_DATASETS.md): FinMind dataset names, tiers and the live probe results. [`docs/OFFICIAL_SOURCES.md`](../OFFICIAL_SOURCES.md): verified TWSE and TPEx endpoints. Endpoint names used below (`MI_INDEX`, `MI_QFIIS`, `TWT84U`, `chtm` and others) are explained there, with evidence in [`docs/research/`](../research/).
*   [`docs/DECISIONS.md`](../DECISIONS.md): every author and Lead decision, with reasons. The decision numbers (D1 to D9) below match the Alternatives section.
*   **Author:** ken-ck-yu, who approves the design and any paid tier or data deletion.
*   **Lead:** the main Claude Code session. It owns shared code and coordinates, and writes no dataset ingestion code.
*   **Agents A to F:** subagents spawned by the Lead. A to E are `ingest-worker` agents (definition in `.claude/agents/ingest-worker.md`), each owning disjoint files. F is the `qa-goldfish` agent (`.claude/agents/qa-goldfish.md`), with fresh context.
*   **Improve loop:** plan section 6.2 step 5. F lists failures tagged by owning agent in `docs/QA_FINDINGS.md`, the Lead re-spawns each owner with its findings, the owner fixes, and F re-runs all checks. At most three rounds, logged in `docs/ITERATION_LOG.md`.
*   **Collection set:** every stock that was ever a universe member. **P0, P1, P2:** the plan's dataset priority tiers (plan section 3).
*   **MOPS:** the Market Observation Post System where listed companies file reports. **ROC date:** the Republic of China calendar in TWSE and TPEx files (add 1911 to the year: 104/06/01 is 2015-06-01). **PER, PBR:** price to earnings and price to book ratios. **ISIN:** the international securities identification number, which is stable when a stock code is reused.
*   **Lot:** 1,000 shares. **`F-` and `KY` names:** prefixes for foreign companies listed in Taiwan, which are common stocks. **Disposition:** a short-term trading restriction on a stock (matching only every few minutes, for example). **Attention:** a warning list for unusual trading. **Changed trading, full delivery:** restrictions under which a stock trades by call auction or with cash paid in full. TPEx reports both in one `chtm` column.

## The Problem

Four things can make Taiwan backtests look better than reality:

1.  **Lookahead.** Monthly revenue, quarterly financials and exchange-published flows are known only after a delay. A table keyed on the period they describe lets a model use them early.
2.  **Survivorship.** A universe built from today's listed stocks leaves out delisted names.
3.  **Price errors and untradable prices.** Wrongly adjusted prices, and trades at limit-locked or restricted prices, produce returns nobody could have earned.
4.  **Unreproducible inputs.** Free sources can change or overwrite history without notice. FinMind did so in 2026 for prices, TPEx margin columns and ETF dividends.

The free FinMind tier also leaves gaps: no adjusted prices, no capital-reduction reference prices, no market cap, no filing dates for quarterly financials, and no shares-issued rows for 3299, the one delisted TPEx stock probed. Several official lists publish only a latest snapshot, so their history can only be built by collecting daily from now on. TWSE disposition and attention lists have history for the windows sampled (2015 and 2024), and TPEx's go back to 2003 and 2002 by the pages' own notes.

## Goals

*   Every joinable clean table has `event_date` and `available_at` (Asia/Taipei). Reference tables (calendar, stock info, delistings) are exempt and are joined on `event_date` only. No joinable row has `available_at` earlier than `event_date`. Every dataset has a written `available_at` rule, and the share of rows that used a fallback is reported per dataset.
*   For every universe member-month, daily prices exist for at least 99% of the trading days on which the stock was listed and not suspended, including stocks later delisted.
*   `universe_membership` has 200 ranked members at each month-end from 2015-06-30, and 2330 is always among them. Watchlist names are extra rows flagged `is_watchlist`. If fewer than 200 stocks pass the liquidity floor, all that pass are kept and the shortfall is reported. A shortfall month is reported, not failed.
*   Adjusted prices are built in-house from raw prices and official ex-rights and capital-reduction events, and produced as of a time using only events available by then. Their agreement with FinMind `TaiwanStockDividendResult` and `TaiwanStockPrice` is checked (check 3).
*   Ingestion is idempotent and resumable. A rerun fills gaps and adds no duplicate rows to the first-reported view. Every response is cached raw before it is parsed.
*   No paid FinMind tier is known to be needed for the P0 to P2 datasets here. Anything that could change this is a gating spike, and the author decides on any tier.
*   FinMind's hourly limit is read from its user-info endpoint at start-up. A token or permission error stops the run and reports.
*   Nothing in git contains the token or data files.

## Non-Goals

*   Feature engineering, modelling, backtesting, broker or order code (plan section 8).
*   News, forums, broker-branch data, and tick or intraday data.
*   A database server, cloud storage, or any storage other than local Parquet and DuckDB.
*   Paying for a data tier, which needs the author's approval.
*   Live or near-real-time collection. Phase 1 is daily batch.
*   Recovering history for sources that publish only a latest snapshot. Their daily collection starts at the beginning of Phase 1.
*   A TWSE full-delivery stock list (accepted gap in `docs/DECISIONS.md`).
*   Employer account-dealing rules, an open item for the later live-trading phase.

## Acceptance checks (agent F)

These are plan section 7's checks, with this design's thresholds. They live in `config/settings.yaml` and the author can change them after the first sample. Each check has one pass condition, the one stated here. Failures and exceptions go to `docs/QA_FINDINGS.md` and the improve loop. The Goals above point to these checks and do not restate their thresholds.

1.  **Coverage:** each universe member-month has daily prices on at least 99% of the stock's listed, non-suspended trading days. The listed-day reference is the FinMind `TaiwanStockPrice` pull over the whole collection set, compared as per-stock-month day counts. A missing row inside a stock's listing span shows up as a count mismatch.
2.  **Survivorship:** the collection set contains delisted names, and at least three known delistings (2475, 3474, 3299) have prices up to their last trading day, checked against `STOCK_DAY`/`tradingStock` or FinMind and not only the daily files. The universe holds each of them in months before it delisted.
3.  **Adjusted prices:** (a) on a stratified sample of 20 stocks (capital reductions, large stock dividends, delisted names, seeded), the as-of adjusted daily return agrees with FinMind `TaiwanStockPrice` day-over-day and with FinMind `TaiwanStockDividendResult` reference prices, within a tick-aware tolerance (the larger of 0.1% and one tick of the prior close). (b) Completeness: every raw close-to-prior-close move beyond 8% with no limit-lock explanation and no event is listed, and yearly event counts are reconciled across `TWT49U`/`TWTAUU`, `exDailyQ`/`revivt` and `DividendResult`. A missing event is the failure this check exists to find. The check detects missing or inconsistent events. It does not prove the official reference prices themselves are right.
4.  **Cross-source:** 500 seeded (stock, date) closes from universe member-days compare the official daily files with FinMind `TaiwanStockPrice`. It assumes both report two decimals and that FinMind prices derive from exchange data. Both are inferences to verify in spike S9. Pass if no more than 1 in 500 mismatches, excluding FinMind's documented 2022-11-28 to 2023-03-27 backfill window, and every mismatch is listed with a reason. The check finds errors in FinMind or in ingestion. It cannot find an error present in the exchange's own files.
5.  **Price limits:** no raw daily move beyond the stated `limit_up`/`limit_down`, except on ex-dates, first listing days, capital-reduction resumption days, suspension gaps, or a documented exception list. A second computed check confirms the parsed up/down sign matches close minus previous close on every TWSE row.
6.  **Point-in-time:** no joinable row has `available_at` before `event_date`. Monthly revenue `available_at` is never earlier than the 10th of the following month at 18:00 (or the next trading day). The share of rows using a fallback is reported per dataset. Snapshot `first_seen_at` is compared with the rule table as a late bound on publication time.
7.  **Duplicates and types:** primary keys are unique in the first-reported view. No mixed units (volume in shares, revenue in NT$ thousands). A stock code is listed on at most one market on any date, and a code that changes company is caught by ISIN.
8.  **Universe sanity:** 200 ranked members per month-end, or all that pass the floor with the shortfall listed. Membership churn (the share of members that changed since the prior month-end) between 2% and 40%, with months outside that range explained. 2330 present every month.

## Open Questions

**Gating spikes (owner Lead, results in `docs/spikes/S<n>.md`, scripts under `scripts/spikes/`, never under `src/`).** Each spike gates the modules it names and amends the design section named in its log.

*   **S1. `MI_QFIIS` coverage. Resolved.** On four dates (2015-06-01, 2018-06-01, 2022-06-01, 2025-06-02) none of 858, 915, 964 and 1,041 common-stock codes lacked a `MI_QFIIS` row. The earlier 915 versus 951 comparison used dates a year apart and was an artefact. FinMind `TaiwanStockShareholding` stays the cross-check only.
*   **S2. Limit-price date meaning. Resolved.** A `TWT84U` row dated D gives the limits for D (its `收盤價` is the previous trading day's close), verified on 1,094 of 1,094 stocks on 2020-06-15. TPEx `otc` next-day limit columns in file D apply to the next trading day with a non-empty file, verified on three consecutive pairs. About 98 TPEx rows carry a `9999.95`/`0.01` no-limit sentinel (bond ETFs) and are stored as null. Publication times are unverified.
*   **S3. Endpoint ranges. Resolved.** `TWTAWU` works for 2015 (2 rows). `TWT49U` returned 11,863 rows for 2015-06-01 to 2026-11-13 in one call with no truncation, but takes 9 to over 60 seconds, so the client timeout is at least 150 seconds, or calls are chunked by year. TPEx `revivt` returns 21 to 29 rows per year for 2016 to 2021.
*   **S4. Common-stock rule. Resolved on 11 TWSE and 11 TPEx dates.** The regex plus the `-DR` name rule has no leaks and no misses among ordinary common stocks. The `-DR` clause is needed (4 to 7 four-digit DR codes pass the regex). Strip a trailing `*` from names before matching. Other dates are not ruled out, so QA re-tests the rule on one date per year.
*   **S7. FinMind call limits.** Probe the largest FinMind datasets (institutional flows by investor type, securities lending, futures) for an 11-year call, because the one-call-per-stock result is proven only for `TaiwanStockPrice` on one stock. Exit: a fail-closed row-count cap per dataset.
*   **S8. Corporate-action coverage. Partly resolved.** `TWT49U` covers ETFs, including every 0050 dividend from 2015 to 2026. No official feed carries stock splits or par-value changes: no row in `TWT49U`, `TWTAUU`, `exDailyQ` or `revivt` has such wording, and `TWT49U` states that split capital reductions are excluded. 0050 closed 175.90 on 2025-06-02 and 51.45 on 2025-07-21 with no event row, so an apparent split is missing (inferred from prices only). Handling is `config/manual_corporate_actions.yaml` (see Adjusted prices). Open: confirm the 0050 split independently.
*   **S9. Era boundaries and cross-checks. Partly resolved.** `MI_INDEX` has the same per-stock field list on seven 2015 dates and ten 2016 to 2025 dates. TPEx `otc` has three eras: 15 fields until 2020-04-29, 17 fields with `(千股)` from 2020-04-30, and 17 fields with `(張數)` from 2025-01-10. Open: whether FinMind prices carry two decimals and agree with the exchange (needs the token).
*   **S10. Publication timing.** Poll `MI_INDEX`, `otc` and `MI_QFIIS` at fixed clock times (15:00, 16:30, 18:00, 19:30) on a few trading days to test the 18:00 assumption.
*   **S5 and S6 (owner agents C and A):** the FinMind monthly revenue unit against the official `t187ap05_L` (agent C, before `monthly_revenue`), and the meaning of `TaiwanStockInfo.date` and the `TaiwanStockDelisting` row-count difference, 690 now against 726 earlier (agent A, before `stock_info` and `delistings`).

**Accepted gaps (recorded, with the effect).**

*   TWSE full-delivery status has no source. QA reports how many member-months might be affected.
*   TPEx suspension history before 2026 uses the per-day `chtm` report as a proxy.
*   The trading calendar's second source (dates on which `MI_INDEX` and `otc` return rows) is derived, not official, because no official calendar history was found.

**Author decisions pending.**

*   Where `data/raw/` and, separately, `data/raw/snapshots/` are backed up (the second path matters more, since snapshot history cannot be refetched). The author chose to decide later. QA reports `backup_dir` as unset at each phase gate.

## Technical Plan (Architecture)

### Decisions made

| # | Decision | Choice | Decided by | Basis |
|---|---|---|---|---|
| D1 | Source for the universe pass | Official TWSE/TPEx daily files | Author, confirmed 2026-11-13 | Survivorship-free, shares issued, official fields. The original request-count reason did not hold |
| D2 | `available_at` for date-only sources | Next trading day 08:30 | Author | One rule for flow and status sources that is easy to test |
| D3 | Adjusted prices | Raw prices plus an event table, adjusted as of a time | Lead, from the review | One stored `available_at` per row cannot be point-in-time |
| D4 | Clean writes | Append-only runs, with views for first-reported and latest-corrected rows | Lead, from the review | Fits restatement handling and the no-overwrite gate |
| D5 | TWSE shares issued | `MI_QFIIS`; FinMind is the cross-check | Lead, from the research | FinMind lacks the delisted TPEx stock probed |
| D6 | Listing status and last trading day | Derived from daily files, checked against `STOCK_DAY`/`tradingStock` | Lead, from the research | The last trade was 1 to 13 days before the listed delisting date in six sampled stocks, and codes are reused |
| D7 | Failure behaviour | Stop and report | Author | Fewer moving parts for an attended run |
| D8 | Phase 2 scope | All agent C, D, E datasets | Author | Plan section 6.6 |
| D9 | Snapshot job | About 12 latest-only sources, run by hand daily with catch-up | Author | History cannot be recovered once missed |

Decisions marked Lead are open to the author's override.

### Data flow

```text
  Official TWSE / TPEx            FinMind API (600 req/h)
  daily files (all stocks)        per-stock, per-dataset range calls
          |                                  |
          v                                  v
  +---------------------------------------------------------------+
  | clients/: per-host limiter (file lock), response classifier,  |
  | raw cache writer                                              |
  +---------------------------------------------------------------+
          | every response, unparsed, with sha256
          v
  data/raw/<source>/<dataset>/  (+ data/raw/qa/ for agent F fetches)
          | parse (ROC dates, numbers, signs), schema-era check
          v
  ingest/*.py --> data/clean/<dataset>/v<N>/year=YYYY/run-*.parquet   (append-only)
          |                    |
          |                    +--> DuckDB views: as_first_seen, as_latest_corrected,
          |                         revisions, listing_status, adjusted_as_of(t)
          v
  universe/ --> data/reference/universe_membership, collection_set
          |
          v
  validate/ (agent F) --> docs/COVERAGE_REPORT.md, docs/QA_FINDINGS.md

  data/state/: completed key ranges per dataset, manifests, host lock files
```

### Source policy

| Data | Primary | Cross-check |
|---|---|---|
| Raw daily OHLCV, volume, turnover | TWSE `MI_INDEX`, TPEx `otc` (one request per date) | FinMind `TaiwanStockPrice` over the whole collection set (check 1), 500 sampled closes (check 4) |
| Shares issued | TWSE `MI_QFIIS`, TPEx `otc` (`發行股數`), with the ISIN from `MI_QFIIS` | FinMind `TaiwanStockShareholding` (collection set) |
| Limit prices | TWSE `TWT84U` (limits for the row date), TPEx `otc` next-day limit columns (stored on the next trading day with a file; the `9999.95`/`0.01` sentinel becomes null) | Computed from the prior close |
| Ex-rights, ex-dividend, capital reductions | TWSE `TWT49U`, `TWTAUU`; TPEx `exDailyQ`, `revivt` | FinMind `TaiwanStockDividend`, `TaiwanStockDividendResult` |
| Disposition, attention, changed trading | TWSE `punish`, `notice`; TPEx `disposal`, `attention`, `chtm` | None |
| Trading calendar | FinMind `TaiwanStockTradingDate` | Dates on which `MI_INDEX` and `otc` return rows (diffed at the Phase 0 gate) |
| Stock info, delistings | FinMind (`TaiwanStockInfo`, `TaiwanStockDelisting`), TWSE delisting list, TPEx `deListed` | Daily files (D6) |
| Benchmark index series | TWSE `MI_INDEX` total return table (`TAIEX_TR`, `TAIWAN50_TR`); FinMind `TaiwanStockTotalReturnIndex` for `TPEX_TR` | FinMind `TAIEX` for `TAIEX_TR`. `TAIWAN50_TR` and `TPEX_TR` have no cross-check |
| 0050 (the benchmark of record) | An ordinary stock row in `prices_raw`, adjusted through `corporate_actions` like any stock. It is a collection-set member flagged `is_benchmark` and excluded from the ranked universe | FinMind `TaiwanStockPrice` |
| The 14 per-stock FinMind datasets | FinMind, one request per stock for the whole range: `TaiwanStockPrice`, `TaiwanStockMonthRevenue`, `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`, `TaiwanStockCashFlowsStatement`, `TaiwanStockInstitutionalInvestorsBuySell`, `TaiwanStockShareholding`, `TaiwanStockMarginPurchaseShortSale`, `TaiwanStockSecuritiesLending`, `TaiwanDailyShortSaleBalances`, `TaiwanStockDayTrading`, `TaiwanStockPER`, `TaiwanStockDividend`, `TaiwanStockDividendResult` | TWSE `t187ap05_L`, `BWIBBU_d` (sample dates), `t187ap06_L_*`, `t187ap07_L_*` |
| US prices, FX, rates, futures | FinMind (`USStockPrice` with `^VIX`, `TaiwanExchangeRate`, `InterestRate`, `GovernmentBondsYield`, `TaiwanFuturesDaily`, `TaiwanFuturesInstitutionalInvestors`) | None |
| Latest-only snapshots | TWSE `TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap04_L`, `t187ap09_L`, `t187ap12_L`, `t187ap24_L` to `t187ap27_L`; TPEx `warning`, `sprc` | None |

`MI_INDEX` had one field list across ten sampled years (2016 to 2025). TPEx `otc` has three field-list eras: 15 fields until 2020-04-29, 17 fields from 2020-04-30, and the same 17 fields from 2025-01-10 with two bid and ask volume columns relabelled from `(千股)` to `(張數)`. The values did not change (inferred from medians). Seven 2015 dates (2015-03 to 2015-12) were sampled and match the 2016 layout.

### Request budget

About 2,843 trading days from 2015-03-02 to 2026-11 (about 11.7 years of about 243 days).

| Source | Requests | Wall-clock at 5 s spacing |
|---|---|---|
| TWSE: `MI_INDEX`, `MI_QFIIS`, `TWT84U`, one request per date each (3 x 2,843) | 8,529 | 11.8 h |
| TPEx: `otc`, `chtm`, one request per date each (2 x 2,843) | 5,686 | 7.9 h |
| Official event and list endpoints, snapshots on start (year-long ranges) | under 200 | under 20 min |
| FinMind: 14 per-stock datasets x about 450 collection-set stocks | 6,300 | 10.5 h at 600 per hour |

The hosts run concurrently. The **critical path is about 18 to 19 hours**: the universe pass (TWSE `MI_INDEX` and `MI_QFIIS`, TPEx `otc`, about 8 hours) must finish before the collection set exists, then FinMind collection (about 10.5 hours) runs while `TWT84U` and `chtm` finish in the background. This is one unattended run, resumable from the cache, and it is staged: one year first, then evaluated, then the full backfill. Retries, the 500-close sample and other FinMind calls add under 5%. The 5 s spacing is a chosen default, not an observed limit (the research made fewer than 100 requests per host).

### Common table columns

Every joinable clean table has `event_date` (date), `available_at` (timestamp, Asia/Taipei, or null when pending) and `fetched_at` (UTC, when the response was received). Provenance (source, endpoint, parameters, raw files, sha256) is recorded once per partition in `data/state/manifest/`. Units: prices in NT$, volume in shares (not lots), turnover in NT$, revenue in NT$ thousands (unit to be confirmed in S5).

### Table schemas of record

| Table | Columns (besides common) | Primary key |
|---|---|---|
| `prices_raw` | `market`, `stock_id`, `open`, `high`, `low`, `close`, `volume_shares`, `turnover_ntd`, `trades`, `limit_up`, `limit_down` | `market`, `stock_id`, `event_date` |
| `shares_issued` | `market`, `stock_id`, `isin`, `shares_issued` | `market`, `stock_id`, `event_date` |
| `market_cap` (derived) | `stock_id`, `close`, `shares_issued`, `market_cap_ntd` | `stock_id`, `event_date` |
| `corporate_actions` | `market`, `stock_id`, `action_type` (`ex_dividend`, `ex_rights`, `capital_reduction`, `split` and `par_value_change`, from the manual file only), `prev_close`, `reference_price`, `halt_close`, `cash_dividend`, `stock_dividend_per_1000`, `reduction_reason`. For a capital reduction `halt_close` holds the last close before the halt and `reference_price` the resumption reference price | `market`, `stock_id`, `event_date`, `action_type` |
| `status_events` | `market`, `stock_id`, `status_type` (`disposition`, `attention`, `changed_trading`), `announce_date`, `start_date`, `end_date`, `detail`. `event_date` is `start_date`. A `chtm` per-day state becomes an event on the first day it is seen, with `announce_date` null | `market`, `stock_id`, `status_type`, `start_date` |
| `benchmark_index` | `index_id` (`TAIEX_TR`, `TAIWAN50_TR`, `TPEX_TR`), `value` | `index_id`, `event_date` |
| `monthly_revenue` | `stock_id`, `revenue_month`, `revenue_ntd_thousand`, `create_time` (as given, a load date, not used) | `stock_id`, `revenue_month` |
| `financials` | `stock_id`, `statement`, `item`, `value` (`event_date` is the period end) | `stock_id`, `event_date`, `statement`, `item` |
| `dividend_announcements` | `stock_id`, `announcement_date`, `announcement_time`, `cash_dividend`, `stock_dividend`, `ex_dividend_date` (whose announcement it records is unverified) | `stock_id`, `announcement_date`, `ex_dividend_date` |
| `flows_institutional` | `stock_id`, `investor_type`, `buy`, `sell`, `net` | `stock_id`, `event_date`, `investor_type` |
| `shareholding`, `valuation_ratios`, `margin`, `day_trading`, `short_sale_balances` | the source columns | `stock_id`, `event_date` |
| `securities_lending` | the source columns including `transaction_type` | `stock_id`, `event_date`, `transaction_type` |
| `us_prices` | `ticker`, `open`, `high`, `low`, `close`, `adj_close`, `volume` | `ticker`, `event_date` |
| `fx`, `rates`, `futures` | series id (`currency`; `country` or `name`; `futures_id` and `contract_date`), values | series id, `event_date` |
| `snapshot_<source>` (one table per snapshot source) | `snapshot_date` (from the response body if it has one, otherwise local date), `first_seen_at`, the source columns | source key, `snapshot_date` |
| `stock_info` (reference) | `stock_id`, `stock_name`, `industry_category`, `market_type` (rows carry `event_date` from the source `date`, meaning unverified, S6) | `stock_id`, `event_date` |
| `delistings`, `trading_calendar` (reference) | `stock_id` and a date; `event_date` and `is_trading` | `stock_id`, `event_date`; `event_date` |
| `universe_membership` | `month_end`, `stock_id`, `isin`, `market`, `rank` (null for watchlist extras), `market_cap_ntd`, `median_turnover_60d`, `is_watchlist`, `is_benchmark` | `month_end`, `stock_id` |
| `collection_set` | `stock_id`, `first_month_end`, `last_month_end`, `ever_watchlist`, `is_benchmark` | `stock_id`, `first_month_end` |

Tables whose date key is not `event_date` store `event_date` as an equal column (`revenue_month` first day, `month_end`). Joins use `stock_id` with a date, never `stock_id` alone across years, since codes are reused. Tables whose columns are "the source columns" get exact columns in the Phase 0 spec. The ingest step asserts that the primary key is unique in the as-first-seen view and fails if not, so a missing key column is found at first run. `listing_status` is a view (first date, last date, market, per stock), derived from `prices_raw`.

### `available_at` rules

"Next trading day 08:30" means the first trading day strictly after the source date, at 08:30. When that date is not yet in the calendar, `available_at` is null (pending), and the row is excluded from joins until the calendar covers it. Every rule gives a **conservative upper bound** on when a trader could first know a value, not the true first-known time. Decision D2 covers the flow and status rows. The table uses four timings because the sources differ.

| Dataset | `available_at` |
|---|---|
| `prices_raw`, `shares_issued`, `benchmark_index` | Trading date 18:00. Design assumption, tested in S10 |
| `flows_institutional`, `margin`, `securities_lending`, `short_sale_balances`, `day_trading`, `valuation_ratios`, `shareholding` | Next trading day 08:30 |
| `monthly_revenue` | The 10th of the following month at 18:00 if it is a trading day, otherwise the next trading day at 18:00. FinMind `create_time` is a load date and is not used |
| `financials` | Statutory deadline (Q1 15 May, Q2 14 Aug, Q3 14 Nov, annual 31 Mar), then next trading day 08:30. MOPS filing dates are not collected in Phase 1. Restated figures are a known lookahead risk |
| `dividend_announcements` | `announcement_date` plus `announcement_time` when present, otherwise next trading day 08:30 |
| `corporate_actions` | Next trading day 08:30 after the ex-date or resumption date |
| `status_events` | Next trading day 08:30 after `announce_date`, or after `start_date` when `announce_date` is null |
| `us_prices` | The next Taiwan calendar day after the US trading date, at 08:30. FinMind updates this data at 08:00 Taiwan time (documented). Raw `close` is the joinable column. `adj_close` may restate and is not for joins |
| `fx`, `rates`, `futures` | Next trading day 08:30 |
| `snapshot_<source>` | `first_seen_at` |
| `market_cap`, `universe_membership`, `collection_set` | The latest `available_at` of their inputs |
| Reference tables | Exempt, joined on `event_date` |

Two uses of the same row differ. **Features** join on `available_at`. **Tradability masks** (whether a stock was restricted on a date) join on the exchange's own `start_date` and `end_date` window, because `available_at` can fall after the first restricted session. Labels (the future by construction) may use the fully adjusted series. A check confirms that mask consumers use the effective window.

The ex-date lag has a side effect. On an ex-date, between its open and the next trading day 08:30, an as-of adjusted series shows a drop equal to the dividend (for example -5%). That is an artefact of the conservative rule, recorded in the data dictionary. It is not leakage.

### Adjusted prices

`prices_raw` and `corporate_actions` carry their own `available_at`. The factor for an ex-dividend or ex-rights event is `reference_price / prev_close`, and for a capital reduction `reference_price / halt_close`. The adjusted close at date t as of time T is `close(t)` times the product of all factors with `event_date` after t and `available_at` on or before T. Two actions on one date multiply. The result is adjusted for dividends and capital changes, which approximates total return. Worked example: close 100 on day 1, an ex-dividend event on day 2 with `prev_close` 100 and `reference_price` 95. The event's `available_at` is day 3 08:30. Adjusted close for day 1 is 100 as of any time before day 3 08:30 and 95 from then on. A stored fully adjusted table is not kept. Official feeds carry no stock splits or par-value changes (S8), so those are entered by hand in `config/manual_corporate_actions.yaml`. Each entry has the stock, date, ratio and a source, and enters `corporate_actions` as a `split` or `par_value_change` row with the same `available_at` rule. The first entry to confirm is 0050's apparent 2025 split. Check 3(b) lists any large move with no event, so a missing entry shows up. Agent B may produce a returns table labelled "validation only, not a feature input" for check 3.

### Failure handling

*   **Stop and report (D7).** Any drift, block, auth error or exhausted retry stops the whole run and reports. There is no circuit breaker, no lane isolation and no silent fallback to another source. Exit categories: stopped on a block or auth error, stopped on schema drift, usage error.
*   **Response classes:** `ok`, `transient`, `drift`. An empty answer is `ok` for range and snapshot endpoints, and for a per-date endpoint on a date that is not a trading day in the calendar. Zero rows on a trading day from a per-date endpoint is `drift`. A TWSE reply to a range query with only `stat` and `total` keys (no data) is `ok` and empty. A TPEx redirect (HTTP 302 to `/errors`) is `drift`. An HTML page with HTTP 200, invalid JSON, a field list outside the registered set for that date, or a `stat` other than OK on a trading day is `drift`. Network errors, 5xx and 429 from TWSE or TPEx are `transient`, retried with backoff (counts and waits live in config) and then a stop. TWSE writes `OK` and TPEx writes `ok`.
*   **Timeouts:** `TWT49U` can take over 60 seconds, so the TWSE client timeout is at least 150 seconds (config).
*   **FinMind:** any 4xx stops the run, including 429 and 402. A burst of failing requests gets the IP banned (403, lifting after about 30 minutes, per FinMind's documentation). The token is read from `FINMIND_TOKEN`, sent as an `Authorization: Bearer` header, and the header is never written to the cache or logs.
*   **Rate limits:** one request in flight per host across all processes, at least 5 seconds apart for TWSE and TPEx. FinMind's rate comes from the user-info endpoint. A file lock plus a last-request timestamp under `data/state/locks/` gives one stream per host across parallel agents. The lock needs a Linux filesystem (not `/mnt/c`).
*   **Schema eras:** accepted field lists are registered per endpoint with date ranges. A new field list is drift, and a human registers it. Value sanity checks run on every parsed row (high not below low, close between low and high, close inside stated limits). A per-call row-count sanity check fails closed above a cap set per dataset (S7).

### Raw cache, state and writes

*   **Raw:** responses are stored as checksummed Parquet shards with a manifest (request key without credentials, URL, parameters, `fetched_at`, status, body, sha256). Raw files are never modified. Shard size is a config value. A crash can lose the responses in the shard being written, which the run refetches. Agent F's cross-check fetches go through the Lead's clients into `data/raw/qa/`, the one exception to F's read-only access.
*   **Backup:** after each phase gate `data/raw/` is copied to a second location, and `data/raw/snapshots/` is copied after each daily run (both open until `backup_dir` is set). `status --verify` reports raw files missing from state and state entries without a file.
*   **State:** `data/state/<dataset>.json` records completed ranges (date ranges or stock ids), the schema era and `updated_at`, written atomically.
*   **Clean writes:** each ingest run appends Parquet files under `data/clean/<dataset>/v<N>/year=YYYY/`. Nothing is rewritten in place. Each dataset has a `restatement_class`. `economic` (monthly revenue, financials, dividends, institutional flows) means a later differing value is a real restatement, and `as_first_seen` keeps the first. `source_error` (prices, shares issued, margin, benchmark, snapshots) means a differing later value is a source correction, and `as_latest_corrected` prefers the latest. Both views exist for every table. The data dictionary states which one each check and consumer uses. A revision row carries an `available_at` no earlier than its `fetched_at`. A parser fix writes `v<N+1>` from raw and a pointer file switches to it. The old version stays until the author approves deleting it. History collected in 2026 is not first-reported before 2026, and the dictionary says so for every table.
*   **Snapshot job (D9):** a command the author runs by hand once per trading day collects the latest-only sources listed in the source policy. Each source has its own `snapshot_<source>` table. Sources with a date parameter catch up on the next run. A missed day for a latest-only source cannot be recovered, and is reported by comparing snapshot dates with the trading calendar. `status` warns when the last snapshot is more than one trading day old. The job starts at the beginning of Phase 1, as soon as `snapshots.py` passes its tests, because each day of delay loses history.

### Universe

Rebuilt on the last trading day of each month from 2015-06-30, following plan section 2. Prices and shares issued are collected from 2015-03-02 so the first 60-day window is complete.

1.  **Listed that day:** every code in the TWSE and TPEx daily files on that date, including later-delisted stocks.
2.  **Common stock only:** a code matching `^[1-9][0-9]{3}$` (four digits, which excludes ETFs `00xx`, preferred shares with a letter suffix, and six-digit warrants and ETNs), whose name (with any trailing `*` removed) does not end in `-DR`. `TaiwanStockInfo` categories are added only if QA's yearly re-test shows leaks. Foreign primary listings (`F-` or `KY` names) are common stocks. 0050 is excluded here and carried separately as the benchmark.
3.  **Not restricted that date:** exclude stocks under disposition, or flagged in the changed-trading report (TPEx `chtm`, and TWSE `status_events` of that type if any), on that date. The TWSE full-delivery gap is accepted.
4.  **Liquidity floor:** 60-trading-day median turnover (`turnover_ntd`) of at least NT$20M, over observed trading days, with at least 40 observed days. Suspended days are missing, not zero. Newer listings under 40 days are ineligible.
5.  **Rank:** by market cap (`close` x `shares_issued` on the month-end), ties broken by higher turnover then lower `stock_id`. Keep the top 200.
6.  **Watchlist:** names in `config/watchlist.yaml` (each with a `start_date`, `reason` and `added_on`) are added as extra rows from their `start_date` onward, with `is_watchlist` true and `rank` null.

A null market cap makes a stock ineligible and is counted and reported per month, so missing data cannot silently drop a delisted stock. Membership churn is defined in check 8.

### Modules and ownership

| Path | Contents | Owner |
|---|---|---|
| `src/twdata/common/` | time rules, parsing, trading calendar, schema registry, paths, config | Lead |
| `src/twdata/clients/` | limiter, raw cache, response classifier, FinMind, TWSE and TPEx clients | Lead |
| `src/twdata/cli.py`, `config/`, `scripts/spikes/`, `docs/specs/`, `docs/spikes/`, `docs/DATA_DICTIONARY.md` (index) | command line, settings, spike scripts and logs, Phase 0 specs, dictionary index | Lead |
| `src/twdata/ingest/` and `src/twdata/universe/`, group A | trading calendar, stock info, delistings, official daily files, market cap, status events, snapshots, classification, monthly universe | Agent A |
| `src/twdata/ingest/`, group B | corporate actions, dividend announcements, adjusted-price view, benchmark, FinMind price pull | Agent B |
| `src/twdata/ingest/`, groups C, D, E | fundamentals; flows and positioning; macro and US | Agents C, D, E |
| `src/twdata/validate/`, `tests/validate/`, `docs/COVERAGE_REPORT.md`, `docs/QA_FINDINGS.md` | acceptance checks and QA output | Agent F only |
| `tests/` (the rest), `docs/data_dictionary/<topic>.md` | tests and each agent's dictionary section | the agent that owns the module |

The exact file names, interfaces and tests for each group are in the Phase 0 specs. No agent edits a path it does not own.

### Dependency order

Lead completes Phase 0. Agent A then runs the all-stock official pass and the universe. B, C, D and E run in parallel after A's gate (B needs A's raw prices, C and D need the collection set, E needs only Phase 0). F runs last.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| IP block from TWSE, TPEx or FinMind | Medium | Run stops for 30 minutes or more | Per-host cross-process limiter, stop on any 4xx or drift, no retries after a stop, a generic client name with no personal details | Lead |
| Undocumented endpoint changes shape | Medium over 18 hours of requests | Run stops, restart by hand | Schema-era registry, value sanity checks, stop and report, no silent fallback, staged first year | Lead |
| Wrong `available_at` guess leaks the future | Medium | Invalid backtests | Conservative rules, as-of adjusted views, check 6, spike S10 timing test, snapshot `first_seen_at` as a late bound | Lead, F |
| Survivorship returns through missing data | Medium | Biased universe | Universe from all-stock daily files, null market caps counted, check 2 against independent last-trade sources | A, F |
| Loss of the raw cache | Medium until `backup_dir` is set | 18 or more hours to refetch, snapshot history lost | Manifest with sha256, a second copy after each phase and after each snapshot run, `status --verify`. Not in effect until the author sets `backup_dir` | Lead |
| Missed daily snapshot | High with a manual daily run | Permanent gap for latest-only sources | Missed-day report, catch-up for sources with a date parameter, `status` warning | A |
| TWSE shares-issued coverage | Low, S1 found no gaps on four dates | Mis-ranked universe | `MI_QFIIS` primary, FinMind cross-check, null market caps counted and reported | A |
| Disk usage grows | Low | Run stops | Measure after the first year (about 3 GB before compression is a one-file-type estimate), report above 70% of free space (config) | Lead |
| Source corrects or restates history | Medium | Values differ from first publication | `restatement_class`, two views, revisions view, dictionary note on the 2026 start | All |
| Free-tier assumption is wrong | Low, 14 datasets probed | Gaps in P1 data | Spikes S7, S8, S9 test the unproven items. The author decides on any tier | Lead |
| Token leakage | Low | Credential exposure | Header never cached or logged, gitignored `.env`, gitleaks at commit, a test asserting the header is absent | Lead |
| Scraping terms of use | Unknown | Source blocks access | Public endpoints, low request rate, a generic client name. Terms of use are not reviewed | Author |

## Alternatives Considered

Each entry uses the same template and the numbering of the decisions table.

**D1. Source for the universe pass.**
*   **Option A, FinMind primary.** Pro: one request per stock per dataset. Con: needs the stock list and shares issued for every stock first, FinMind has no shares-issued rows for 3299, and per-stock calls only on the free tier mean about 2,000 or more requests before any ranking. Verdict: not chosen.
*   **Option B, official files primary (chosen).** Pro: one request per date covers all stocks, files include later-delisted stocks, shares issued and limit prices. Con: about 12 hours on TWSE alone, undocumented endpoints, custom parsing. Request counts are comparable to FinMind's, so the reason is survivorship and the official fields. Verdict: chosen, confirmed by the author 2026-11-13.
*   **Option C, both fully, reconciled.** Pro: conflicts found across all data. Con: about double the storage and an undefined conflict rule. Verdict: not chosen. The FinMind price pull in check 1 gives most of the benefit.

**D2. `available_at` for date-only sources.**
*   **Chosen:** next trading day 08:30. **Not chosen:** per-dataset time rules (each time is an unverified guess that leaks the future if wrong) and real retrieval time going forward (two timing regimes in one table). The rule can be later than reality, and spike S10 and `first_seen_at` measure by how much.

**D3. Adjusted price storage.**
*   **A stored adjusted table:** a 2016 value depends on every action to 2026, so one `available_at` per row cannot be right. Not chosen.
*   **Chosen:** raw prices plus actions, adjusted as of a time. Cost: a view and a computed test.

**D4. Clean writes.**
*   **Upsert by rewriting year partitions:** overwrites collected data. Not chosen.
*   **Chosen:** append-only runs with two views. A lighter alternative is disposable clean tables rebuilt from immutable raw, appending only for restatement-class tables. Not chosen here, and can be revisited in the Phase 0 specs.

**D5. Shares issued for TWSE.** `MI_QFIIS` (chosen, official, dated, includes later-delisted stocks) against FinMind `TaiwanStockShareholding` (no row for 3299, continues 19 months past 2475's last trade). FinMind is the cross-check.

**D6. Listing status.** Derived from the daily files (chosen) against the delisting lists (codes reused, dates 1 to 13 days after the last trade, TPEx list may omit transfers to TWSE).

**D7. Failure behaviour.** Stop and report (chosen, author). Not chosen: independent lanes per (host, dataset) with a dead-letter ledger, which keeps healthy datasets running at the cost of more code and parked-lane coverage gaps.

**D8. Phase 2 scope.** All C, D, E datasets (chosen, author, plan 6.6). Not chosen: seed-hypothesis datasets first.

**D9. Snapshot job.** All about 12 sources, run by hand (chosen, author). Not chosen: only sources with a named consumer, and a cron or systemd timer (a WSL2 machine sleeps).

**Other.** A paid FinMind tier and a database server were rejected earlier by the author (`docs/DECISIONS.md`, plan section 5). Yahoo `Adj Close` was dropped as a cross-check: it has no client, and its Taiwan adjustments are unverified. `requests` with `urllib3.Retry` handles retries. No standard package gives a per-host cross-process spacing lock, so the limiter is small custom code. FinMind is called by REST, not the `FinMind` package, so request headers stay under this project's control. `pandas` is dropped because DuckDB and `pyarrow` cover table work. These library choices are the Lead's, and the Phase 0 specs list the dependencies.

## Non-Functional Requirements

*   **Security and privacy:** `FINMIND_TOKEN` comes from the environment or a gitignored `.env`, never written to the cache or logs. The `Authorization` header is removed before anything is cached. `data/` and `audit/events.jsonl` are gitignored. Gitleaks runs at commit.
*   **Rollout and rollback:** nothing is deployed. Collected data is rebuilt from `data/raw/` into a new version directory. Deleting raw data or an old clean version needs the author's approval.
*   **Footprint:** about 14,400 official responses plus about 6,300 FinMind responses, about 20,700 in all. A TWSE daily file is about 150 KB (one file type measured). The total is an estimate of roughly 3 GB before compression, to be measured after the first year.

## Detailed Implementation Plan

Nothing below is built until the author approves the reviewed design. No modelling, backtesting or trading code is included. This section holds the phases, gates and prerequisites. Interface specs, file lists, test vectors and tooling choices are in the Phase 0 specs.

### Author prerequisites (before Phase 0 can pass)

*   **Agent F's write access.** `.claude/agents/qa-goldfish.md` gives F no write tools, forbids edits under `src/`, and has Bash, which is already a write path. Project-wide deny rules in `.claude/settings.json` cannot allow F while blocking other agents. The mechanism is a `PreToolUse` hook that reads the agent type (the audit hook already records it) and permits writes to `src/twdata/validate/**`, `tests/validate/**`, `docs/COVERAGE_REPORT.md` and `docs/QA_FINDINGS.md` for `qa-goldfish` only, and blocks them for every other agent. The agent definition is updated to match, including its Bash restriction. The hook is tested before Phase 3.
*   **`.claude/agents/ingest-worker.md`.** It tells each worker to write a section of `docs/DATA_DICTIONARY.md`. This design has one file per topic under `docs/data_dictionary/` and the Lead owns the index, so the definition changes.
*   **`.gitignore`.** Add a rule so saved test fixtures are tracked despite the global `*.parquet` and `*.csv` rules.
*   `backup_dir` may stay unset. QA reports it at each gate, and it is not part of any gate.

### Phase 0 (Lead)

Builds the shared code (common, clients, CLI, config), writes the Phase 0 specs under `docs/specs/`, and runs the remaining spikes (S7, S10, and the open parts of S8 and S9). S1 to S4 are resolved. The specs are checked against the zero-decision standard before agents start. Spike logs record outcomes and amend this design where they change it.

Gate (offline): the Lead's tests pass with no network, `ruff` is clean, the calendar diff between FinMind and the derived calendar is recorded, and every spike result is logged. The author prerequisites are done.

### Phase 1 (Agent A)

Builds the snapshot collector first and starts it daily, then the all-stock official pass, the calendar, stock info, delistings, market cap, status events and the universe. A runs S5's counterpart S6 before `stock_info` and `delistings`.

Gate (offline): module tests pass on fixtures. Gate (live, owner Lead): the official pass has run for one year, then for the full range (about 8 hours), and `universe/build.py` asserts 200 ranked members at each month-end (or reports the shortfall), 2330 present. Check 8 itself is F's, run in Phase 3.

### Phase 2 (Agents B, C, D, E in parallel)

B: corporate actions, dividend announcements, adjusted-price view, benchmark, the FinMind price pull for check 1. C: monthly revenue (after S5), financials, valuation ratios. D: institutional flows, shareholding, margin, securities lending, short-sale balances, day trading. E: US prices, FX, rates, futures.

Gate (offline, per agent): module tests pass. Gate (live): a small run over the window 2018-10-01 to 2018-11-30 with stocks 2330, 2317 (TWSE), 6488 (TPEx), 2475 (TWSE, traded until 2019-05-10) and 3299 (TPEx, last traded 2018-11-21, so this window exercises a delisting). Datasets that are not per stock (US prices, FX, rates, futures, benchmark) run over the same window. The run goes into a temporary data directory, is repeated, and shows no duplicate rows in `as_first_seen`. The full collection (critical path 18 to 19 hours) follows.

### Phase 3 (Agent F, then the improve loop)

F writes the validation suite and runs checks 1 to 8, with fresh context and the data dictionary, the acceptance checks and read access to data. Failures go to `docs/QA_FINDINGS.md` tagged by owner and enter the improve loop (at most three rounds, logged in `docs/ITERATION_LOG.md`). Anything still failing goes to the author with the evidence.

Gate: each check meets its own pass condition above.

### Verification

*   Unit tests run offline on saved fixtures, one set per schema era per endpoint, with no token and no personal data.
*   Every parser, every `available_at` rule and every response class has tests, including weekend, holiday and beyond-calendar cases, and the worked example above.
*   Live gates are separate from offline gates and have a named owner and procedure in the Phase 0 specs.
*   All network access goes through `src/twdata/clients/`.

--------------------------------------------------------------------------------

*Drafted with EGM, revised by the Lead after review*
