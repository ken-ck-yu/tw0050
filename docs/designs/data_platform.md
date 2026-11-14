# Taiwan Data Platform (Phase 1: data collection)

*   **Author:** ken-ck-yu
*   **Status:** Draft, revision 4 (after review round 3 and the author's answers). Not yet re-reviewed or approved.
*   **Date:** 2026-11-13

--------------------------------------------------------------------------------

## Overview

This design covers the local data layer for a research project that tests whether a machine-learning strategy, holding Taiwan stocks for roughly 2 to 10 trading days, earns an edge after costs. Phase 1 collects and validates data only. It contains no modelling, backtesting, broker or trading code.

The platform collects prices, corporate actions, fundamentals, investor flows and macro series for stocks listed on TWSE (the Taiwan Stock Exchange) and TPEx (the Taipei Exchange, the over-the-counter market) from 2015-06-01. It stores them as Parquet files on local disk, queried with DuckDB. Prices and shares issued are collected from 2015-03-02, three months before the first universe date, so the first 60-day window is complete. The project runs on Linux under WSL2. Every joinable table records the time a value is assumed to be known, so later research can join on that time and avoid using the future.

Sources are the free TWSE and TPEx official files and FinMind (free tier, 600 requests per hour). The official files build the universe, because they list every stock on every date including stocks later delisted. FinMind supplies the per-stock datasets for the collection set.

This is an **approval document**. It fixes the decisions, table schemas of record, ownership, phase gates and acceptance criteria. Interface specs, file-level lists, test vectors, tooling and parameter defaults are written by the Lead in the M0 specs (`docs/specs/`) and checked there against the zero-decision standard before any agent builds from them.

### References and terms

*   [`DATA_COLLECTION_PLAN.md`](../../DATA_COLLECTION_PLAN.md): the project plan. This design builds on its sections 2 (universe rule), 4 (point-in-time rules), 6 (agent framework, including the improve loop in 6.2 step 5 and the agent split in 6.6) and 7 (acceptance checks).
*   [`docs/FINMIND_DATASETS.md`](../FINMIND_DATASETS.md): FinMind dataset names, tiers and the live probe results. [`docs/OFFICIAL_SOURCES.md`](../OFFICIAL_SOURCES.md): verified TWSE and TPEx endpoints. Endpoint names used below (`MI_INDEX`, `MI_QFIIS`, `TWT84U`, `chtm` and others) are explained there, with evidence in [`docs/research/`](../research/).
*   [`docs/DECISIONS.md`](../DECISIONS.md): every author and Lead decision, with reasons. The decision numbers (D1 to D9) below match the Alternatives section.
*   **Author:** ken-ck-yu, who approves the design and any paid tier or data deletion.
*   **Lead:** the main Claude Code session. It owns shared code and coordinates, and writes no dataset ingestion code.
*   **Agents A to F:** subagents spawned by the Lead. A to E are `ingest-worker` agents (definition in `.claude/agents/ingest-worker.md`), each owning disjoint files. F is the `qa-goldfish` agent (`.claude/agents/qa-goldfish.md`), with fresh context.
*   **Improve loop:** plan section 6.2 step 5. F lists failures tagged by owning agent in `docs/QA_FINDINGS.md`, the Lead re-spawns each owner with its findings, the owner fixes, and F re-runs all checks. At most three rounds, logged in `docs/ITERATION_LOG.md`.
*   **Zero-decision standard:** a spec meets it when an implementer has no choice left that affects data, `available_at` or file ownership (the readiness standard of the EGM review tool, stage 9).
*   **Collection set:** every stock that was ever a universe member. **P0, P1, P2:** the plan's dataset priority tiers (plan section 3).
*   **MOPS:** the Market Observation Post System where listed companies file reports. **ROC date:** the Republic of China calendar in TWSE and TPEx files (add 1911 to the year: 104/06/01 is 2015-06-01). **PER, PBR:** price to earnings and price to book ratios. **ISIN:** the international securities identification number, which is stable when a stock code is reused.
*   **Lot:** 1,000 shares. **`F-` and `KY` names:** prefixes for foreign companies listed in Taiwan, which are common stocks. **Disposition:** a short-term trading restriction on a stock (matching only every few minutes, for example). **Attention:** a warning list for unusual trading. **Changed trading, full delivery:** restrictions under which a stock trades by call auction or with cash paid in full. TPEx appears to report both in one `chtm` column (inferred, not verified, S12).

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
*   Recovering history for sources that publish only a latest snapshot. Their capture began on 2026-11-14 and has no earlier history.
*   A TWSE full-delivery stock list (accepted gap in `docs/DECISIONS.md`).
*   Employer account-dealing rules, an open item for the later live-trading phase.

## Acceptance checks (agent F)

These are plan section 7's checks, with this design's thresholds. They live in `config/settings.yaml` and the author can change them after the first sample. Each check has one pass condition, the one stated here. Failures and exceptions go to `docs/QA_FINDINGS.md` and the improve loop. The Goals above point to these checks and do not restate their thresholds.

1.  **Coverage:** each universe member-month has daily prices on at least 99% of the stock's listed, non-suspended trading days. The listed-day reference is the FinMind `TaiwanStockPrice` pull over the whole collection set, compared as per-stock-month day counts, excluding FinMind's documented 2022-11-28 to 2023-03-27 zero-volume backfill window. A missing row inside a stock's listing span shows up as a count mismatch.
2.  **Survivorship:** the collection set contains delisted names, and at least three known delistings (2475, 3474, 3299) have prices up to their last trading day, checked against `STOCK_DAY`/`tradingStock` or FinMind and not only the daily files. Each is in the collection candidate set, and in the universe in the months where it ranked.
3.  **Adjusted prices:** (a) on a stratified sample of 20 stocks (capital reductions, large stock dividends, delisted names, seeded), the as-of adjusted daily return on event days agrees with FinMind `TaiwanStockDividendResult` reference prices, and on other days with FinMind `TaiwanStockPrice` day-over-day returns (which are raw), within a tick-aware tolerance (the larger of 0.1% and one tick of the prior close). (b) Completeness: every raw close-to-prior-close move beyond 8% with no limit-lock explanation and no event is listed, and yearly event counts are reconciled across `TWT49U`/`TWTAUU`, `exDailyQ`/`revivt` and `DividendResult`. A missing event is the failure this check exists to find. The check detects missing or inconsistent events. It does not prove the official reference prices themselves are right.
4.  **Cross-source:** 500 seeded (stock, date) closes from universe member-days compare the official daily files with FinMind `TaiwanStockPrice`. It assumes FinMind prices derive from exchange data, which no FinMind page states. Two decimals and exact agreement held in 20 of 20 pairs (S9). Pass if no more than 1 in 500 mismatches, excluding FinMind's documented 2022-11-28 to 2023-03-27 backfill window, and every mismatch is listed with a reason. The check finds errors in FinMind or in ingestion. It cannot find an error present in the exchange's own files.
5.  **Price limits:** no raw daily move beyond the stated `limit_up`/`limit_down`, except on ex-dates, first listing days, capital-reduction resumption days, suspension gaps, or a documented exception list. A second computed check confirms the parsed up/down sign matches close minus previous close on every TWSE row.
6.  **Point-in-time:** no joinable row has `available_at` before `event_date`. Monthly revenue `available_at` is never earlier than the 10th of the following month at 18:00 (or the next trading day), which guards against a coding regression. The share of rows using a fallback is reported per dataset. Snapshot `first_seen_at` is compared with the rule table as a late bound on publication time.
7.  **Duplicates and types:** primary keys are unique in the first-reported view. No mixed units (volume in shares, revenue in NT$ thousands). A stock code is listed on at most one market on any date, and a code that changes company is caught by ISIN.
8.  **Universe sanity:** 200 ranked members per month-end, or all that pass the floor with the shortfall listed. Membership churn (the share of members that changed since the prior month-end) between 2% and 40%, with months outside that range explained. 2330 present every month.

## Open Questions

Resolved spikes S1 to S4 and S7 to S9 are recorded in [`docs/spikes/resolved.md`](../spikes/resolved.md). Each open item below names an owner and what it gates. Spike scripts live under `scripts/spikes/`, never under `src/`, and results go to `docs/spikes/S<n>.md`.

*   **S10. Publication timing (owner Lead, gates `available_at` for `prices_raw`, `price_limits`, `shares_issued`, `benchmark_index`).** Poll `MI_INDEX`, `otc` and `MI_QFIIS` at 15:00, 16:30, 18:00 and 19:30 Taipei time on at least three trading days. Decision rule: if any file first appears after 18:00 on any day, the rule becomes the latest observed time plus 30 minutes, and the Lead amends this design and the spike log. Only the 18:00 rule has a planned test. The other `available_at` rules are assumptions.
*   **S11. Corporate-action sources (owner Lead, gates `corporate_actions`).** Probe the two TPEx pages for par-value change reference and reduction notices (`/zh-tw/announce/market/change/reference.html`, `/reduction.html`) and look for a TWSE equivalent. Obtain 0050's 2025 split resumption reference price from the exchange announcement (a manual web step, since it is outside `clients/`), and enter it in `config/manual_corporate_actions.yaml`.
*   **S12. Mappings and keys (owner Lead, gates the listed schemas).** Verify the TPEx `chtm` mapping to full-delivery (inferred, not verified). Find the discriminating column for `securities_lending` (17,960 rows over 2,795 days is about 6.4 rows per day, so the three-column key is wrong). Test long-range calls for the three financial statement datasets and `TaiwanStockDividend`. Give `TaiwanFuturesInstitutionalInvestors` its own table. Find a TPEx ISIN source or accept null.
*   **S5 (owner agent C, gates `monthly_revenue`) and S6 (owner agent A, gates `stock_info` and `delistings`).** S5: the FinMind monthly revenue unit against the official `t187ap05_L`. S6: the meaning of `TaiwanStockInfo.date` and the `TaiwanStockDelisting` row-count difference (690 now against 726 earlier).

**Accepted gaps (recorded, with the effect).**

*   TWSE full-delivery status has no source. QA reports how many member-months might be affected. TPEx's `chtm` may fold it into the changed-trading flag (inferred, S12).
*   TPEx suspension history before 2026 uses the per-day `chtm` report as a proxy. The 2026 history (365 records) was captured once on 2026-11-14 because the source keeps only the current ROC year.
*   The trading calendar's second source (dates on which `MI_INDEX` and `otc` return rows) is derived, not official. It can only find FinMind days the exchanges lack if every weekday is requested, which is done for the 2015-03 to 2015-05 stub and in the staged first year.

**Author decisions pending.**

*   Where `data/raw/` and, separately, `data/raw/snapshots/` are backed up. The author chose to decide later. QA reports `backup_dir` as unset at each gate.
*   Terms of use for scraping the public TWSE and TPEx endpoints are not reviewed. The author owns this, ahead of about 14,000 requests.

## Technical Plan (Architecture)

### Decisions made

| # | Decision | Choice | Decided by | Basis |
|---|---|---|---|---|
| D1 | Source for the universe pass | Official TWSE/TPEx daily files | Author, confirmed 2026-11-13 | Survivorship-free, shares issued, official fields. The original request-count reason did not hold |
| D2 | `available_at` for date-only sources | Next trading day 08:30 | Author | One rule for flow and status sources that is easy to test |
| D3 | Adjusted prices | Raw prices plus an event table, adjusted as of a time | Lead, from the review | One stored `available_at` per row cannot be point-in-time |
| D4 | Clean writes | Append-only runs, with views for first-reported and latest-corrected rows | Lead, from the review | Fits restatement handling and the no-overwrite gate |
| D5 | TWSE shares issued | `MI_QFIIS`; FinMind is the cross-check | Lead, from the research | `MI_QFIIS` had no gaps on four dates, and FinMind shares rows continue 19 months past 2475's last trade |
| D6 | Listing status and last trading day | Derived from daily files, checked against `STOCK_DAY`/`tradingStock` | Lead, from the research | The last trade was 1 to 13 days before the listed delisting date in six sampled stocks, and codes are reused |
| D7 | Failure behaviour | Stop and report | Author | Fewer moving parts for an attended run |
| D8 | M2 scope | All agent C, D, E datasets | Author | Plan section 6.6 |
| D9 | Snapshot job | 15 latest-only endpoints (11 TWSE, 4 TPEx), run by hand daily with catch-up | Author | History cannot be recovered once missed |

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
| Trading calendar | FinMind `TaiwanStockTradingDate` | Dates on which `MI_INDEX` and `otc` return rows (diffed at the M1 live gate) |
| Stock info, delistings | FinMind (`TaiwanStockInfo`, `TaiwanStockDelisting`), TWSE delisting list, TPEx `deListed` | Daily files (D6) |
| Benchmark index series | TWSE `MI_INDEX` total return table (`TAIEX_TR`, `TAIWAN50_TR`); FinMind `TaiwanStockTotalReturnIndex` for `TPEX_TR` | FinMind `TAIEX` for `TAIEX_TR`. `TAIWAN50_TR` and `TPEX_TR` have no cross-check |
| 0050 (the benchmark of record) | An ordinary stock row in `prices_raw`, adjusted through `corporate_actions` like any stock. It is a collection-set member flagged `is_benchmark` and excluded from the ranked universe | FinMind `TaiwanStockPrice` |
| The 14 per-stock FinMind datasets | FinMind, one request per stock for the whole range: `TaiwanStockPrice`, `TaiwanStockMonthRevenue`, `TaiwanStockFinancialStatements`, `TaiwanStockBalanceSheet`, `TaiwanStockCashFlowsStatement`, `TaiwanStockInstitutionalInvestorsBuySell`, `TaiwanStockShareholding`, `TaiwanStockMarginPurchaseShortSale`, `TaiwanStockSecuritiesLending`, `TaiwanDailyShortSaleBalances`, `TaiwanStockDayTrading`, `TaiwanStockPER`, `TaiwanStockDividend`, `TaiwanStockDividendResult` | TWSE `t187ap05_L`, `BWIBBU_d` (sample dates), `t187ap06_L_*`, `t187ap07_L_*` |
| US prices, FX, rates, futures | FinMind (`USStockPrice` with `^VIX`, `TaiwanExchangeRate`, `InterestRate`, `GovernmentBondsYield`, `TaiwanFuturesDaily`, `TaiwanFuturesInstitutionalInvestors`) | None |
| Latest-only snapshots (15 OpenAPI endpoints) | TWSE `TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap04_L`, `t187ap09_L`, `t187ap12_L`, `t187ap24_L`, `t187ap25_L`, `t187ap26_L`, `t187ap27_L`; TPEx `tpex_spendi_today`, `tpex_spendi_history`, `tpex_trading_warning_information`, `tpex_trading_warning_note` | None |

`MI_INDEX` had one field list across ten sampled years (2016 to 2025). TPEx `otc` has three field-list eras: 15 fields until 2020-04-29, 17 fields from 2020-04-30, and the same 17 fields from 2025-01-10 with two bid and ask volume columns relabelled from `(千股)` to `(張數)`. The values did not change (inferred from medians). Seven 2015 dates (2015-03 to 2015-12) were sampled and match the 2016 layout.

### Request budget

About 2,843 trading days from 2015-03-02 to 2026-11 (about 11.7 years of about 243 days).

| Source | Requests | Wall-clock at 5 s spacing |
|---|---|---|
| TWSE: `MI_INDEX`, `MI_QFIIS`, `TWT84U`, one request per date each (3 x 2,843) | 8,529 | 11.8 h |
| TPEx: `otc`, `chtm`, one request per date each (2 x 2,843) | 5,686 | 7.9 h |
| Official event and list endpoints, snapshots on start (year-long ranges) | under 200 | under 20 min |
| FinMind: 14 per-stock datasets x about 450 collection-set stocks | 6,300 | 12.4 h at 85% of 600 per hour |

The hosts run concurrently. The universe pass is TWSE `MI_INDEX` and `MI_QFIIS` (about 7.9 hours) and TPEx `otc` and `chtm` (7.9 hours), so it takes about 8 hours with both hosts running. It must finish before the collection set exists. FinMind collection (about 12.4 hours at 85% of the quota) then runs while `TWT84U` finishes in the background. The **critical path is about 20 hours** (8 plus 12.4), split across milestones M1 and M2. The collection set is the plan's estimate of 350 to 450 names. It is recomputed after the staged first year, and each extra 100 stocks adds 1,400 requests (about 2.7 hours at 85% of the quota). The run is staged (one year first, then evaluated, then the full backfill), resumable from the cache, and run in sessions you start and watch, not left to sleep through. Retries and the other FinMind calls add a few percent. The 5 s spacing is a chosen default, not an observed limit (the research made fewer than 100 requests per host).

### Common table columns

Every joinable clean table has `event_date` (date), `available_at` (timestamp, Asia/Taipei, or null when pending) and `fetched_at` (UTC, when the response was received). Provenance (source, endpoint, parameters, raw files, sha256) is recorded once per partition in `data/state/manifest/`. Units: prices in NT$, volume in shares (not lots), turnover in NT$, revenue in NT$ thousands (unit to be confirmed in S5).

### Table schemas of record

| Table | Columns (besides common) | Primary key |
|---|---|---|
| `prices_raw` | `market`, `stock_id`, `open`, `high`, `low`, `close`, `volume_shares`, `turnover_ntd`, `trades` (a `--` no-trade row is stored with null prices and zero volume) | `market`, `stock_id`, `event_date` |
| `price_limits` | `market`, `stock_id`, `limit_up`, `limit_down` (null for the no-limit sentinel), from `TWT84U` and the TPEx next-day columns | `market`, `stock_id`, `event_date` |
| `shares_issued` | `market`, `stock_id`, `isin` (from `MI_QFIIS`, so null for TPEx), `shares_issued` | `market`, `stock_id`, `event_date` |
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

**Table classes.** Joinable: every table with `available_at` in the rule table below. Their `event_date` is the trading date, except `corporate_actions` (ex-date or resumption date), `status_events` (`start_date`), `dividend_announcements` (`announcement_date`), `financials` (period end), `monthly_revenue` (first day of `revenue_month`), `universe_membership` (`month_end`) and `snapshot_<source>` (`snapshot_date`, clamped to be no later than the date of `first_seen_at` in Asia/Taipei). Reference: `trading_calendar`, `stock_info`, `delistings`, and `collection_set`, which is only a list used to choose which stocks to fetch and is not a feature input. Derived: `market_cap` and `universe_membership`, with the latest `available_at` of their inputs.

Tables whose date key is not `event_date` store `event_date` as an equal column (`revenue_month` first day, `month_end`). Joins use `stock_id` with a date, never `stock_id` alone across years, since codes are reused. Tables whose columns are "the source columns" get exact columns in the M0 spec. The ingest step asserts that the primary key is unique in the as-first-seen view and fails if not, so a missing key column is found at first run. `listing_status` is a view (first date, last date, market, per stock), derived from `prices_raw`.

### `available_at` rules

"Next trading day 08:30" means the first trading day strictly after the source date, at 08:30. When that date is not yet in the calendar, `available_at` is null (pending), and the row is excluded from joins until the calendar covers it. Each rule is meant as a conservative upper bound on when a trader could first know a value, not the true first-known time. Only the 18:00 rule has a planned test (S10), the others are assumptions, and statutory deadlines bound only on-time filers. Decision D2 covers the flow and status rows. The table has several timings because the sources differ.

| Dataset | `available_at` |
|---|---|
| `prices_raw`, `price_limits`, `shares_issued`, `benchmark_index` | Trading date 18:00. Design assumption, tested in S10 |
| `flows_institutional`, `margin`, `securities_lending`, `short_sale_balances`, `day_trading`, `valuation_ratios`, `shareholding` | Next trading day 08:30 |
| `monthly_revenue` | The 10th of the following month at 18:00 if it is a trading day, otherwise the next trading day at 18:00. FinMind `create_time` is a load date and is not used |
| `financials` | Statutory deadline (Q1 15 May, Q2 14 Aug, Q3 14 Nov, annual 31 Mar), then next trading day 08:30. MOPS filing dates are not collected. Restated figures are a known lookahead risk |
| `dividend_announcements` | `announcement_date` plus `announcement_time` when present, otherwise next trading day 08:30 |
| `corporate_actions` | Next trading day 08:30 after the ex-date or resumption date |
| `status_events` | Next trading day 08:30 after `announce_date`, or after `start_date` when `announce_date` is null |
| `us_prices` | The next Taiwan calendar day after the US trading date, at 08:30. FinMind updates this data at 08:00 Taiwan time (documented). Raw `close` is the joinable column. `adj_close` may restate and is not for joins |
| `fx`, `rates`, `futures` | Next trading day 08:30 |
| `snapshot_<source>` | `first_seen_at` |
| `market_cap`, `universe_membership`, `collection_set` | The latest `available_at` of their inputs |
| Reference tables | Exempt, joined on `event_date` |

Two uses of the same row differ. **Features** join on `available_at`. **Tradability masks** (whether a stock was restricted on a date) join on the exchange's own `start_date` and `end_date` window, because `available_at` can fall after the first restricted session. Labels (the future by construction) may use the fully adjusted series. A check confirms that mask consumers use the effective window.

The ex-date lag has a side effect. On an ex-date, between its open and the next trading day 08:30, an as-of adjusted series shows a drop equal to the dividend (for example -5%). That is an artefact of the conservative rule, recorded in the data dictionary. It is not leakage. The adjusted-price view carries an `is_ex_date_window` flag so the feature layer can mask those rows.

### Adjusted prices

`prices_raw` and `corporate_actions` carry their own `available_at`. The factor for an ex-dividend or ex-rights event is `reference_price / prev_close`, and for a capital reduction `reference_price / halt_close`. The adjusted close at date t as of time T is `close(t)` times the product of all factors with `event_date` after t and `available_at` on or before T. Two actions on one date multiply. The result is adjusted for dividends and capital changes, which approximates total return. Worked example: close 100 on day 1, an ex-dividend event on day 2 with `prev_close` 100 and `reference_price` 95. The event's `available_at` is day 3 08:30. Adjusted close for day 1 is 100 as of any time before day 3 08:30 and 95 from then on. A stored fully adjusted table is not kept. None of the four official feeds checked carries stock splits or par-value changes (S8), so those are entered by hand in `config/manual_corporate_actions.yaml`. Each entry has the stock, date, ratio and a source, and enters `corporate_actions` as a `split` or `par_value_change` row with the same `available_at` rule. The first entry is 0050's 4-for-1 split, resumed on 2025-06-18 after a halt from 2025-06-11 to 2025-06-17 (price evidence from FinMind), with its official reference price still to be taken from the exchange announcement. Check 3(b) lists any large move with no event, so a missing entry shows up. Agent B may produce a returns table labelled "validation only, not a feature input" for check 3.

### Failure handling

*   **Stop and report (D7).** Any drift, block, auth error or exhausted retry stops the whole run and reports. There is no circuit breaker, no lane isolation and no silent fallback to another source. Exit categories: stopped on a block or auth error, stopped on schema drift, usage error.
*   **Response classes:** `ok`, `transient`, `drift`. An empty answer is `ok` for range and snapshot endpoints, and for a per-date endpoint on a date that is not a trading day in the calendar. Zero rows on a trading day from a per-date endpoint is `drift`, with one exception chosen by the author on 2026-11-14: if both TWSE and TPEx return no rows on a day the FinMind calendar calls a trading day, the date is recorded as a calendar discrepancy and the run continues. The list is reviewed at the gate. A TWSE reply to a range query with only `stat` and `total` keys (no data) is `ok` and empty. A TPEx redirect (HTTP 302 to `/errors`) is `drift`. An HTML page with HTTP 200, invalid JSON, a field list outside the registered set for that date, or a `stat` other than OK on a trading day is `drift`. Network errors, 5xx and 429 from TWSE or TPEx are `transient`, retried with backoff (counts and waits live in config) and then a stop. TWSE writes `OK` and TPEx writes `ok` in the `stat` field.
*   **Timeouts:** `TWT49U` can take over 60 seconds, so the TWSE client timeout is at least 150 seconds (config).
*   **FinMind:** any 4xx stops the run, including 429 and 402. A burst of failing requests gets the IP banned (403, lifting after about 30 minutes, per FinMind's documentation). The token is read from `FINMIND_TOKEN`, sent as an `Authorization: Bearer` header, and the header is never written to the cache or logs.
*   **Rate limits:** one request in flight per host across all processes, at least 5 seconds apart for TWSE and TPEx. FinMind's rate comes from the user-info endpoint. The limiter targets 85% of that limit (config), re-reads `user_count` periodically, and waits for the hour to roll over near the limit so a 402 is not sent. A file lock plus a last-request timestamp under `data/state/locks/` gives one stream per host across parallel agents. The lock needs a Linux filesystem (not `/mnt/c`).
*   **Schema eras:** accepted field lists are registered per endpoint with date ranges. A new field list is drift, and a human registers it. Value sanity checks run on every parsed row (high not below low, close between low and high, close inside stated limits). A per-call row-count sanity check fails closed above a cap set per dataset (S7).

### Raw cache, state and writes

*   **Raw:** responses are stored as checksummed Parquet shards with a manifest (request key without credentials, URL, parameters, `fetched_at`, status, body, sha256). Raw files are never modified. Shard size is a config value. A crash can lose the responses in the shard being written, which the run refetches. Agent F's cross-check fetches go through the Lead's clients into `data/raw/qa/`, the one exception to F's read-only access.
*   **Backup:** after each phase gate `data/raw/` is copied to a second location, and `data/raw/snapshots/` is copied after each daily run (both open until `backup_dir` is set). `status --verify` reports raw files missing from state and state entries without a file.
*   **State:** `data/state/<dataset>.json` records completed ranges (date ranges or stock ids), the schema era and `updated_at`, written atomically.
*   **Clean writes:** each ingest run appends Parquet files under `data/clean/<dataset>/v<N>/year=YYYY/`. Nothing is rewritten in place. Each dataset has a `restatement_class`. `economic` (monthly revenue, financials, dividends, institutional flows) means a later differing value is a real restatement, and `as_first_seen` keeps the first. `source_error` (prices, shares issued, margin, benchmark, snapshots) means a differing later value is a source correction, and `as_latest_corrected` prefers the latest. Both views exist for every table. The data dictionary states which one each check and consumer uses. A revision row carries an `available_at` no earlier than its `fetched_at`. A parser fix writes `v<N+1>` from raw and a pointer file switches to it. The old version stays until the author approves deleting it. History collected in 2026 is not first-reported before 2026, and the dictionary says so for every table.
*   **Snapshot job (D9):** a command the author runs by hand once per trading day collects the latest-only sources listed in the source policy. Each source has its own `snapshot_<source>` table. Sources that also have a history endpoint (for example `tpex_spendi_history`, which keeps only the current ROC year) catch up on the next run. A missed day for a latest-only source cannot be recovered, and is reported by comparing snapshot dates with the trading calendar. `status` warns when the last snapshot is more than one trading day old. A stopgap script, `scripts/snapshot_capture.py`, began raw capture of all 15 endpoints on 2026-11-14 with the author's approval, and the M1 job replaces it and imports its files. The stopgap bypasses `clients/` and is a known migration step.

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

The exact file names, interfaces and tests for each group are in the M0 specs. No agent edits a path it does not own, and the Lead checks `git diff --name-only` against each agent's allowed paths after every run.

### Dependency order

Lead completes M0. Agent A then runs the all-stock official pass and the universe (M1). B, C, D and E run in parallel after A's gate (B needs A's raw prices, C and D need the collection set, E needs only M0). F runs last.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| IP block from TWSE, TPEx or FinMind | Medium | Run stops for 30 minutes or more | Per-host cross-process limiter, stop on any 4xx or drift, no retries after a stop, a generic client name with no personal details | Lead |
| Undocumented endpoint changes shape | Medium over about 20 hours of requests | Run stops, restart by hand | Schema-era registry, value sanity checks, stop and report, no silent fallback, staged first year | Lead |
| Wrong `available_at` guess leaks the future | Medium | Invalid backtests | Conservative rules, as-of adjusted views, check 6, spike S10 timing test, snapshot `first_seen_at` as a late bound | Lead, F |
| Survivorship returns through missing data | Medium | Biased universe | Universe from all-stock daily files, null market caps counted, check 2 against independent last-trade sources | A, F |
| Loss of the raw cache | Medium until `backup_dir` is set | 20 or more hours to refetch, snapshot history lost | Manifest with sha256, a second copy after each phase and after each snapshot run, `status --verify`. Not in effect until the author sets `backup_dir` | Lead |
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

**D8. M2 scope.** All C, D, E datasets (chosen, author, plan 6.6). Not chosen: seed-hypothesis datasets first.

**D9. Snapshot job.** All 15 endpoints, run by hand (chosen, author). Not chosen: only sources with a named consumer, and a cron or systemd timer (a WSL2 machine sleeps).

**Other.** A paid FinMind tier and a database server were rejected earlier by the author (`docs/DECISIONS.md`, plan section 5). Yahoo `Adj Close` was dropped as a cross-check: it has no client, and its Taiwan adjustments are unverified. `requests` with `urllib3.Retry` handles retries. No standard package gives a per-host cross-process spacing lock, so the limiter is small custom code. FinMind is called by REST, not the `FinMind` package, so request headers stay under this project's control. `pandas` is dropped because DuckDB and `pyarrow` cover table work. These library choices are the Lead's, and the Phase 0 specs list the dependencies.

## Non-Functional Requirements

*   **Security and privacy:** `FINMIND_TOKEN` comes from the environment or a gitignored `.env`, never written to the cache or logs. The `Authorization` header is removed before anything is cached. `data/` and `audit/events.jsonl` are gitignored. Gitleaks runs at commit.
*   **Rollout and rollback:** nothing is deployed. Collected data is rebuilt from `data/raw/` into a new version directory. Deleting raw data or an old clean version needs the author's approval.
*   **Footprint:** about 14,400 official responses plus about 6,300 FinMind responses, about 20,700 in all. A TWSE daily file is about 150 KB (one file type measured). The total is an estimate of roughly 3 GB before compression, to be measured after the first year.

## Detailed Implementation Plan

Nothing below is built until the author approves the reviewed design. Milestones are named M0 to M3 so they are not confused with the project's own Phase 1 or the plan's research Phase 2 (plan section 10). This section holds milestones, gates, owners and prerequisites. Interface specs, file lists, test vectors and tooling are in the M0 specs.

### Author prerequisites (before M0 can pass)

1.  **`.claude/agents/qa-goldfish.md`.** Add `Write` and `Edit` to its tools. Instruct it to write only to `src/twdata/validate/**`, `tests/validate/**`, `data/raw/qa/`, `docs/COVERAGE_REPORT.md`, `docs/QA_FINDINGS.md` and its run report. Change its inputs to the data dictionary index, `docs/specs/acceptance_checks.md` (extracted by the Lead from this design) and read access to data.
2.  **Enforcement is a post-hoc check, not a hook.** After each agent run the Lead compares `git diff --name-only` with that agent's allowed paths from the M0 spec, and any other path fails the gate. Agents A to E share one agent type, so a hook keyed on agent type cannot separate them, and a hook cannot confine Bash writes. The check reads the repository, so it covers Bash.
3.  **`.claude/agents/ingest-worker.md`.** It tells each worker to write a section of `docs/DATA_DICTIONARY.md`. Change it to write `docs/data_dictionary/<topic>.md` and a run report `audit/runs/<date>_<agent>.md`, and add `audit/runs/` to each worker's allowed paths.
4.  **`.gitignore`.** The project file ignores `*.parquet`, `*.csv` and `data/`. Add a negation limited to `tests/fixtures/`. Fixtures are the one exception to "no data in git".
5.  **Daily snapshot run.** Until the M1 job replaces it, the author runs `python3 -I scripts/snapshot_capture.py` once per trading day. It started 2026-11-14 with the author's approval.
6.  `backup_dir` may stay unset. QA reports it at each gate. Backing up `data/raw/snapshots/` before M1 is recommended.

### M0 (Lead)

Builds the shared code (common, clients, CLI, config). Writes the M0 specs under `docs/specs/`, including `acceptance_checks.md`. Captures test fixtures (one set per schema era per endpoint, no token). Loads the FinMind calendar and fixes the calendar source for 2015-03-02 to 2015-05-29: one request per weekday to both exchanges, where an empty reply from both marks a holiday (about 64 weekdays, 128 requests). Runs spikes S10, S11 and S12.

Gate, offline: the Lead's tests pass with no network, lint passes, fixtures exist for every endpoint era, and the author prerequisites are done. The `docs/specs/` set passes a fresh-reviewer review against the zero-decision standard (at most two rounds). Defaults that change data or `available_at` are recorded in `docs/DECISIONS.md`. The author sees a one-page summary and approves before agents build.

Gate, live (owner Lead): S11 is logged, and `config/manual_corporate_actions.yaml` holds 0050's split with a sourced reference price, with an offline test that the adjusted close is continuous across 2025-06-18. S10 is logged, or the author defers it to M1.

### M1 (Agent A)

Builds the snapshot module (replacing the stopgap script), the official daily-file pass, the derived second calendar, stock info, delistings, market cap, status events (including the `chtm`, `punish` and `disposal` ranges the universe needs), common-stock classification and the monthly universe. S6 is resolved before `stock_info` and `delistings`.

Gate, offline: module tests pass on fixtures.

Gate, live (owner Lead): the official pass (`MI_INDEX`, `MI_QFIIS`, `otc`, `chtm`) runs for the first year (2015-03-02 to 2016-03-31) and is evaluated, then for the full range (about 8 hours). `TWT84U` finishes in the background. Pass criteria: no `drift` stop other than recorded calendar discrepancies, per-date row counts agree with the calendar, disk per year is within twice the estimate, the FinMind and derived calendars are diffed with every one-sided day listed, `universe/build.py` asserts 200 ranked members at each month-end (or lists the shortfall) with 2330 present, and snapshot capture has no missed trading day since 2026-11-14 (or the gaps are listed). Check 8 itself is F's, run in M3.

### M2 (Agents B, C, D, E in parallel)

B: corporate actions, dividend announcements, `price_limits`, the adjusted-price view, benchmark, and the FinMind price pull for check 1. C: monthly revenue (after S5), financials, valuation ratios. D: institutional flows, shareholding, margin, securities lending, short-sale balances, day trading. E: US prices, FX, rates, futures. Fixtures for each module are the Lead's M0 deliverable.

Gate, offline (per agent): module tests pass, the agent's `docs/data_dictionary/<topic>.md` and run report exist, and its work is one commit.

Gate, live (per agent, owner Lead): two small runs into a temporary data directory. Window 1 is 2018-10-01 to 2018-11-30 with stocks 2330, 2317 (TWSE), 6488 (TPEx), 2475 (TWSE, traded until 2019-05-10) and 3299 (TPEx, last traded 2018-11-21, which exercises a delisting). Window 2 is 2025-06-01 to 2025-06-30 with the same stocks plus 0050 (split resumed 2025-06-18), so corporate-action logic runs on real events. Datasets that are not per stock (US prices, FX, rates, futures, benchmark) run over both windows. Pass assertions: per-dataset row counts equal the calendar times the stocks, or a documented expected-empty case (for example no FinMind shares rows for 3299), a rerun writes no new files, the 0050 adjusted close is continuous across 2025-06-18, and the delisting is handled. Then the full collection: the remaining FinMind queue (about 12 hours at 85% of the quota) ends with every `data/state/<dataset>.json` complete and every dictionary section and run report present.

### M3 (Agent F, then the improve loop)

F writes the validation suite and fetches its cross-check data through the Lead's clients into `data/raw/qa/`. It includes fault-injection fixtures in `tests/validate/` that prove each check can fail. At the end it runs the plan's drift check of code against this design (plan section 6.2 step 6).

Improve loop: failures in Lead-owned code are fixed by the Lead, and a fix that needs a refetch of more than one hour needs the author's approval. A round is one fix pass plus one full re-run of F's checks, at most three rounds, logged in `docs/ITERATION_LOG.md`. After three rounds, remaining failures go to the author, who records any accepted failure in `docs/DECISIONS.md`.

Gate: every check meets its pass condition, or the author has accepted the remaining failures in the decision log.

### Verification

*   Unit tests run offline on saved fixtures, with no token and no personal data.
*   Every parser, every `available_at` rule and every response class has tests, including weekend, holiday and beyond-calendar cases, and the worked example in "Adjusted prices".
*   A test fails if a module outside `src/twdata/clients/` imports an HTTP library.
*   Live gates are separate from offline gates and each has a named owner.

--------------------------------------------------------------------------------

*Drafted with EGM, revised by the Lead after review*
