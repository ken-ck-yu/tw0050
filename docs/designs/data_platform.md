# Taiwan Data Platform (Phase 1: data collection)

*   **Author:** ken-ck-yu
*   **Status:** Draft, revision 2 (revised after the first review and the source research). Not yet re-reviewed or approved.
*   **Date:** 2026-11-13

--------------------------------------------------------------------------------

## Overview

This design covers the local data layer for a research project that tests whether a machine-learning strategy, holding Taiwan stocks for roughly 2 to 10 trading days, earns an edge after costs. Phase 1 collects and validates data only. It contains no modelling, backtesting, broker or trading code.

The platform collects prices, corporate actions, fundamentals, investor flows and macro series for stocks listed on TWSE (the Taiwan Stock Exchange) and TPEx (the Taipei Exchange, the over-the-counter market) from 2015-06-01. It stores them as Parquet files on local disk, queried with DuckDB. Every table records when a value could first have been known to a trader, so later research can join on that time and avoid using the future.

Sources are the free TWSE and TPEx official endpoints and FinMind (free tier, 600 requests per hour). The official files build the universe, because they list every stock on every date including stocks later delisted. FinMind supplies the per-stock datasets for the collection set.

### References and terms

*   [`DATA_COLLECTION_PLAN.md`](../../DATA_COLLECTION_PLAN.md): the project plan. This document builds on its sections 2 (universe rule), 4 (point-in-time rules), 6.6 (agent split) and 7 (acceptance checks).
*   [`docs/FINMIND_DATASETS.md`](../FINMIND_DATASETS.md): FinMind dataset names, tiers and the 2026-11-13 live probe results.
*   [`docs/OFFICIAL_SOURCES.md`](../OFFICIAL_SOURCES.md): verified TWSE and TPEx endpoints and their gotchas. Evidence is in [`docs/research/`](../research/).
*   [`docs/DECISIONS.md`](../DECISIONS.md): decisions by the author and by the Lead, with reasons.
*   **Author / Ken:** ken-ck-yu, the human who approves the design and any paid tier or data deletion.
*   **Lead:** the main Claude Code session. It owns shared code and coordinates, and writes no dataset ingestion code.
*   **Agents A to F:** subagents spawned by the Lead. A to E are `ingest-worker` agents, each owning disjoint files (section "Modules and ownership"). F is the `qa-goldfish` agent. It starts with fresh context and writes only the validation suite and QA reports.
*   **MOPS:** the Market Observation Post System, where listed companies file reports. **ROC dates:** the Republic of China calendar used in TWSE and TPEx files (104/06/01 is 2015-06-01). **PER, PBR:** price to earnings and price to book ratios. **Collection set:** every stock that was ever a universe member.
*   **P0, P1, P2:** the plan's priority tiers for datasets (section 3 of the plan). This design covers P0 and P1 fully and P2 in the schema and `available_at` tables.

## The Problem

A strategy test is only as honest as its data. Four things can make Taiwan backtests look better than reality:

1.  **Lookahead.** Monthly revenue, quarterly financials and exchange-published flows are known only after a delay. A table keyed on the period they describe lets a model use them early.
2.  **Survivorship.** A universe built from today's listed stocks leaves out names that were delisted, and delisted names can have done worse than average.
3.  **Price errors and untradable prices.** Wrongly adjusted prices, and trades at limit-locked or disposition-restricted prices, produce returns nobody could have earned.
4.  **Unreproducible inputs.** Free sources can change or overwrite history without notice, so a result may not be rerunnable.

The free FinMind tier also leaves gaps. It has no adjusted prices, no capital-reduction reference prices, no market cap, no filing dates for quarterly financials, and no shares-issued rows for at least one delisted TPEx stock. Several official lists publish only a latest snapshot, so their history can only be built by collecting daily from now on. TWSE disposition and attention lists do have history back to 2015, and TPEx's go back to 2002 and 2003.

## Goals

*   Every clean table has `event_date` and `available_at` (Asia/Taipei), and no row has `available_at` earlier than `event_date`. Every dataset has a written rule for `available_at`. The share of rows that used a fallback rule is reported per dataset.
*   For every universe member-month, daily prices exist for at least 99% of the trading days on which the stock was listed and not suspended, including stocks later delisted. A stock's first and last listing months count only the days it was listed.
*   `universe_membership` has exactly 200 ranked members at each month-end from 2015-06-30, and 2330 is always among them. Watchlist names are extra rows flagged `watchlist`. If fewer than 200 stocks pass the liquidity floor in a month, all that pass are kept and the shortfall is reported.
*   Adjusted prices are built in-house from raw prices and official ex-rights and capital-reduction events. They are produced as of a given time, using only events whose `available_at` is on or before it. On a stratified sample of 20 stocks they match an independent source within the tolerance in check 3.
*   Ingestion is idempotent and resumable. A rerun fills gaps and creates no duplicate rows. Every response is cached raw before it is parsed.
*   No paid FinMind tier is known to be needed for the P0 and P1 datasets. Open items that could change this are listed under Open Questions.
*   Each source's request rate is kept within its limit. The FinMind limit is read from its user-info endpoint at start-up. A token or permission error stops the run and reports.
*   Nothing in git contains the token or data files.

## Non-Goals

*   Feature engineering, modelling, backtesting, broker or order code (plan section 8).
*   News, forums, broker-branch data, and tick or intraday data.
*   A database server, cloud storage, or any storage other than local Parquet and DuckDB.
*   Paying for a data tier. That needs the author's approval.
*   Live or near-real-time collection. Phase 1 is daily batch.
*   Recovering historical values for sources that publish only a latest snapshot. Their daily collection starts at the beginning of Phase 1 and has no earlier history.
*   A TWSE full-delivery stock list (accepted gap, recorded in `docs/DECISIONS.md`).
*   Employer account-dealing rules, an open item for the later live-trading phase.

## Acceptance checks (agent F)

These are the plan's section 7 checks, written here with the thresholds this design proposes. Thresholds live in `config/settings.yaml`, and the author can change them after the first sample.

1.  **Coverage:** each universe member-month has daily prices for at least 99% of the stock's listed, non-suspended trading days. All gaps are listed.
2.  **Survivorship:** the collection set contains delisted names, and at least three known delistings (2475, 3474, 3299) have prices up to their last trading day, found from the daily files. The universe contains at least one stock in the months before it delisted.
3.  **Adjusted prices:** on a sample of 20 stocks, stratified to include capital reductions, large stock dividends and delisted names (seeded), the as-of adjusted daily return matches the return implied by raw prices and the official reference price within 0.1% (parameter `adj_return_tolerance`). Yahoo `Adj Close` is a secondary comparison, reported and not a pass condition, because its Taiwan adjustments are not trusted.
4.  **Cross-source:** 500 random (stock, date) closes from universe member-days (seeded) compare the official daily files with FinMind `TaiwanStockPrice`. Both report two decimals. Pass if at least 99.9% match exactly, and every mismatch is listed with a reason. This detects errors in FinMind or in ingestion. FinMind prices derive from exchange data, so it cannot detect an error that is in the exchange's own files.
5.  **Price limits:** no raw daily move beyond the limit stated in `limit_up` and `limit_down`, except on ex-dates, a first listing day or a documented exception list. A second computed check confirms the parsed up/down sign matches close minus previous close on every TWSE row.
6.  **Point-in-time:** no row has `available_at` before `event_date`. For monthly revenue, `available_at` is after the first day of the following month. The share of rows that used a fallback rule is reported. Going forward, `fetched_at` of snapshot sources is compared with the rule table.
7.  **Duplicates and types:** primary keys are unique in the as-of views. No mixed units (volume in shares, revenue in NT$ thousands). A stock code is listed on at most one market on any date.
8.  **Universe sanity:** exactly 200 ranked members per month-end, shortfall months reported, monthly turnover in membership between 2% and 40% (parameter, proposed) and explained when outside, 2330 always present.

## Open Questions

**Gating spikes (owner Lead, before any ingest module is built).** Each has an exit criterion and a stated fallback.

*   **S1. `MI_QFIIS` coverage.** `MI_QFIIS` had 915 rows against 951 `MI_INDEX` rows on comparable dates. Exit: for one date per year, list which common stocks have no shares-issued row. Fallback: FinMind `TaiwanStockShareholding`, then carry-forward from the last known value (up to 10 trading days), then ineligible with a reported count.
*   **S2. `TWT84U` date meaning.** Whether the limit prices on a row date apply to that date or the next trading day. Exit: compare with the TPEx next-day limit columns and with raw closes.
*   **S3. Endpoint ranges.** `TWTAWU` back to 2015, TPEx `revivt` for 2016 to 2021, and the maximum date range per TWSE call.
*   **S4. Common-stock classification.** Test the proposed rule (see Universe) against `TaiwanStockInfo` for one date per year. Exit: a list of excluded categories and codes, with the unmatched remainder reviewed by the author.
*   **S5. Revenue unit.** Confirm FinMind monthly revenue units against the official `t187ap05_L`, which states NT$ thousands.
*   **S6. FinMind reference tables.** Why `TaiwanStockDelisting` returned 690 rows now and 726 earlier, and whether `TaiwanStockInfo` `date` is the change date or a snapshot date.

**Accepted gaps (recorded, with the effect).**

*   TWSE full-delivery status has no source. QA reports how many member-months might be affected.
*   TPEx suspension history before 2026 uses the per-day `chtm` report as a proxy.
*   TWSE `TWT85U`, `TWT96U` and the holiday schedule have no found history. They are collected as daily snapshots from the start of Phase 1.

**Author decisions pending.**

*   How the daily snapshot job runs on this machine (the machine can sleep, and a missed day cannot be recovered).
*   Where `data/raw/` is backed up.

## Technical Plan (Architecture)

### Decisions made

| Decision | Choice | Decided by | Basis |
|---|---|---|---|
| Source for the universe pass | Official TWSE/TPEx daily files | Author (to be confirmed, see Alternatives) | Survivorship-free, shares issued, official fields. The author's original reason (request count) did not hold |
| `available_at` for date-only sources | Next trading day 08:30 | Author | One conservative rule that is easy to test |
| Adjusted prices | Raw prices plus an event table, adjusted as of a time | Lead, from the review | One stored `available_at` per row cannot be point-in-time |
| Idempotent writes | Append-only clean files, first-reported row chosen by a view | Lead, from the review | Fits first-reported rule and the no-overwrite gate |
| Who collects all-stock prices and shares issued | Agent A | Lead, from plan section 2 | Removes the A, B, D dependency cycle |
| Shares issued for TWSE market cap | `MI_QFIIS`; FinMind is the cross-check | Lead, from the research | FinMind lacks delisted TPEx names |
| Last trading day and listing status | Derived from the daily files | Lead, from the research | Last trade is 3 to 13 days before the listed delisting date, and codes are reused |

Decisions marked Lead are open to the author's override.

### Data flow

```text
  Official TWSE / TPEx            FinMind API (600 req/h)
  daily files (all stocks)        per-stock, per-dataset range calls
          |                                  |
          v                                  v
  +---------------------------------------------------------------+
  | clients/: per-host limiter (file lock), response classifier,  |
  | circuit breaker, raw cache writer                             |
  +---------------------------------------------------------------+
          | every response, unparsed, with sha256
          v
  data/raw/<source>/<dataset>/shard-*.parquet  + manifest
          | parse (ROC dates, numbers, signs), schema-era check
          v
  ingest/*.py --> data/clean/<dataset>/v<N>/year=YYYY/run-*.parquet   (append-only)
          |                    |
          |                    +--> DuckDB views: first-reported row per key,
          |                         revisions, adjusted_as_of(t)
          v
  universe/ --> data/reference/universe_membership, collection_set
          |
          v
  validate/ (agent F, read-only on data) --> docs/COVERAGE_REPORT.md, docs/QA_FINDINGS.md

  data/state/: completed key ranges per dataset, manifests, host lock files
```

### Source policy

| Data | Primary | Cross-check |
|---|---|---|
| Raw daily OHLCV, volume, turnover, TAIEX and Taiwan 50 total return | TWSE `MI_INDEX`, TPEx `otc` (one request per date) | FinMind `TaiwanStockPrice` (500 closes, and the per-stock collection set) |
| Shares issued | TWSE `MI_QFIIS`, TPEx `otc` `發行股數` | FinMind `TaiwanStockShareholding` (collection set) |
| Limit prices | TWSE `TWT84U`, TPEx `otc` next-day limit columns | Computed from the prior close |
| Ex-rights, ex-dividend, capital reductions | TWSE `TWT49U`, `TWTAUU`; TPEx `exDailyQ`, `revivt` | FinMind `TaiwanStockDividend`, `TaiwanStockDividendResult` |
| Disposition, attention, changed trading | TWSE `punish`, `notice`; TPEx `disposal`, `attention`, `chtm` | None |
| Trading calendar, stock info, delisting list | FinMind (calendar, info), TWSE and TPEx lists | Official holiday schedule where it has history |
| Monthly revenue, flows, margin, lending, day trading, PER, financials, US prices, FX, rates, futures | FinMind (one request per stock per dataset for the whole range) | TWSE `t187ap05_L`, `BWIBBU_d` (sample dates), `t187ap06_L_*`, `t187ap07_L_*` |
| Benchmark index | TWSE `MI_INDEX` total return table (TAIEX, Taiwan 50) | FinMind `TaiwanStockTotalReturnIndex` `data_id` `TAIEX`, `TPEx` |

`MI_INDEX` has one field list across ten sampled years (2016 to 2025). TPEx `otc` has three field-list eras (before 2020, 2020 to 2025-01-09, from 2025-01-10). The 2025 change relabels two bid and ask volume columns from `(千股)` to `(張數)`. The values did not change (median bid volume 3, ask volume 2 on both sides), so the change is a label correction, which was inferred from medians.

### Request budget

Trading days from 2015-03 (the turnover window starts three months before the first universe date) to 2026-11: about 2,843.

| Source | Requests | Wall-clock at 5 s spacing |
|---|---|---|
| TWSE: `MI_INDEX`, `MI_QFIIS`, `TWT84U`, one request per date each | 8,529 | 11.9 h (host-serial) |
| TPEx: `otc`, `chtm`, one request per date each | about 5,760 | 8.0 h |
| Official event and list endpoints (year-long ranges, about 12 calls each) | under 200 | under 20 min |
| FinMind: 14 per-stock datasets x about 450 collection-set stocks | 6,300 | 10.5 h at 600 per hour |

The hosts run concurrently, so the unattended wall-clock is about 12 hours. The universe pass needs only `MI_INDEX`, `MI_QFIIS` and `otc`, about 8 hours. FinMind datasets for the collection set start after the universe exists. `BWIBBU_d` is fetched for sample dates only. All runs resume from the cache.

### Common table columns

Every clean table has `event_date` (date), `available_at` (timestamp, Asia/Taipei, or null when pending) and `fetched_at` (UTC, when the response was received). Provenance (source, endpoint, parameters, raw shard names, sha256) is recorded once per partition in `data/state/manifest/`, not on every row. Units are fixed per table: prices in NT$, volume in shares (not lots), turnover in NT$, revenue in NT$ thousands.

### Table schemas

| Table | Columns (besides common) | Primary key |
|---|---|---|
| `prices_raw` | `market`, `stock_id`, `open`, `high`, `low`, `close`, `volume_shares`, `turnover_ntd`, `trades`, `limit_up`, `limit_down` | `market`, `stock_id`, `event_date` |
| `shares_issued` | `market`, `stock_id`, `shares_issued` | `market`, `stock_id`, `event_date` |
| `market_cap` (derived) | `stock_id`, `close`, `shares_issued`, `market_cap_ntd` | `stock_id`, `event_date` |
| `corporate_actions` | `market`, `stock_id`, `action_type` (`ex_dividend`, `ex_rights`, `capital_reduction`), `prev_close`, `reference_price`, `cash_dividend`, `stock_dividend_per_1000`, `reduction_reason` | `market`, `stock_id`, `event_date`, `action_type` |
| `status_events` | `market`, `stock_id`, `status_type` (`disposition`, `attention`, `changed_trading`, `split_trading`, `managed`, `halt`, `suspension`), `announce_date`, `start_date`, `end_date`, `detail` | `market`, `stock_id`, `status_type`, `announce_date`, `start_date` |
| `benchmark_index` | `index_id` (`TAIEX_TR`, `TAIWAN50_TR`, `TPEX_TR`), `value` | `index_id`, `event_date` |
| `monthly_revenue` | `stock_id`, `revenue_month`, `revenue_ntd_thousand`, `create_time` (as given) | `stock_id`, `revenue_month` |
| `financials` | `stock_id`, `statement`, `item`, `value` (`event_date` is the period end) | `stock_id`, `event_date`, `statement`, `item` |
| `dividend_announcements` | `stock_id`, `announcement_date`, `announcement_time`, `cash_dividend`, `stock_dividend`, `ex_dividend_date` | `stock_id`, `announcement_date`, `ex_dividend_date` |
| `flows_institutional` | `stock_id`, `investor_type`, `buy`, `sell`, `net` | `stock_id`, `event_date`, `investor_type` |
| `shareholding`, `valuation_ratios`, `margin`, `day_trading` | per source columns | `stock_id`, `event_date` |
| `securities_lending` | per source columns incl. `transaction_type` | `stock_id`, `event_date`, `transaction_type` |
| `us_prices` | `ticker`, `open`, `high`, `low`, `close`, `adj_close`, `volume` | `ticker`, `event_date` |
| `fx`, `rates`, `futures` | series id (`currency`, `country`/`name`, `futures_id` and `contract_date`), values | series id, `event_date` |
| `stock_info` | `stock_id`, `stock_name`, `industry_category`, `market_type` (rows carry `event_date` from the source `date`) | `stock_id`, `event_date` |
| `delistings`, `trading_calendar` | `stock_id`; `is_trading` | `stock_id`; `event_date` |
| `universe_membership` | `month_end`, `stock_id`, `market`, `rank`, `market_cap_ntd`, `median_turnover_60d`, `is_watchlist` | `month_end`, `stock_id` |
| `collection_set` | `stock_id`, `first_month_end`, `last_month_end`, `ever_watchlist` | `stock_id` |

Tables whose date key is not `event_date` (`monthly_revenue`, `universe_membership`) store `event_date` as an equal column: the first day of `revenue_month`, and `month_end`. A stock code is on one market on any date, so downstream joins use `stock_id` and `event_date`. Tables marked "per source columns" (and the series tables) get exact columns when their module is built. The ingest step asserts the primary key is unique and fails if it is not, so a missing key column is found at first run.

### `available_at` rules

"Next trading day 08:30" means the first trading day strictly after the source date, at 08:30. When that date is not yet in the calendar, `available_at` is null (pending), and the row is excluded from joins until the calendar covers it.

| Dataset | `available_at` |
|---|---|
| `prices_raw`, `shares_issued`, `benchmark_index` | Trading date 18:00. Design assumption. The snapshot job records real first-seen times going forward to test it |
| `flows_institutional`, `margin`, `securities_lending`, `day_trading`, `valuation_ratios`, `shareholding` | Next trading day 08:30 |
| `monthly_revenue` | The 10th of the following month at 18:00 if it is a trading day, otherwise the next trading day at 18:00. FinMind `create_time` is a load date from 2026-04-21 and is not used |
| `financials` | Statutory deadline (Q1 15 May, Q2 14 Aug, Q3 14 Nov, annual 31 Mar), then next trading day 08:30. A filing date from MOPS is not collected in Phase 1 |
| `dividend_announcements` | `announcement_date` plus `announcement_time` when present, otherwise next trading day 08:30 |
| `corporate_actions` | Next trading day 08:30 after the ex-date or resumption date. Adjusted prices are derived as of a time, so this lateness is handled in the view |
| `status_events` | Next trading day 08:30 after `announce_date`. A pending-in-future start date does not change this |
| `us_prices` | The next Taiwan calendar day after the US trading date at 08:30. FinMind updates this data at 08:00 Taiwan time. Raw `close` is the joinable column. `adj_close` may restate and is not for joins |
| `fx`, `rates`, `futures` | Next trading day 08:30 |
| `market_cap`, `universe_membership`, `collection_set` | The latest `available_at` of their inputs |
| `trading_calendar`, `stock_info` | Reference tables, exempt from `available_at` joins. They carry their `event_date` only and are joined on it. `stock_info` history semantics are open (S6) |
| `delistings` | Cross-check only, not for joins |

Daylight saving is not needed in these rules: the US rule is anchored on the Taiwan calendar and FinMind's Taiwan update time. First-reported values are kept (see Idempotence), but FinMind and the official files return current values, so history collected in 2026 is not first-reported before 2026. The data dictionary states this for every table.

### Adjusted prices

`prices_raw` and `corporate_actions` are stored with their own `available_at`. The factor for an ex-dividend or ex-rights event is `reference_price / prev_close`, and for a capital reduction `resumption_reference_price / halt_close`. The adjusted close at date t as of time T is `close(t)` times the product of all factors with `event_date` after t and `available_at` on or before T. Two actions on one date multiply. The result is dividend- and capital-change-adjusted, which approximates total return. Worked example: close 100 on day 1, ex-dividend on day 2 with prev_close 100 and reference price 95 gives factor 0.95, so adjusted close on day 1 as of any time after day 2 08:30 is 95 and day 2's raw close is unchanged. A stored fully adjusted table is not kept, because it cannot carry one `available_at`. A materialised returns table labelled "validation only, not a feature input" may be produced by agent B for check 3.

### Rate limiting and failure handling

*   **FinMind:** the hourly limit comes from the user-info endpoint at start-up and sets the limiter. A token or permission error stops the run and reports. The token is read from `FINMIND_TOKEN`, sent as an `Authorization: Bearer` header, and the header is never written to the cache or logs. A burst of failing requests gets the IP banned (403, lifting after about 30 minutes), so any 4xx stops the run.
*   **TWSE and TPEx:** one request in flight per host across all processes, at least 5 seconds apart (a chosen default, not an observed limit). The limiter is a file lock plus a last-request timestamp under `data/state/locks/`, so parallel agents share one stream per host.
*   **Response classes:** `ok`; `valid_empty` (valid body, no rows, and the date is not a trading day in the calendar); `transient` (network error, 5xx, 429, retried up to 5 times with 5, 10, 20, 40 and 80 second waits); `drift` (HTTP 200 HTML page, invalid JSON, a field list outside the accepted set for that date, or no rows on a trading day). TWSE reports `stat` as `OK` and TPEx as `ok`.
*   **Circuit breaker:** 3 consecutive `drift` responses open it for a host. It half-opens after 15 minutes with one probe. A failed probe stops the run and reports. A dataset that hits drift is marked stale, and the response is quarantined under `data/raw/quarantine/`. There is no silent fallback to another source.
*   **Schema eras:** accepted field lists are registered per endpoint with date ranges (for example three for TPEx `otc`). A new field list is drift, and a human decides whether to register it. Value sanity checks run on every parsed row (high not below low, close between low and high, close inside the stated limits).

### Raw cache, state and writes

*   **Raw:** responses are stored in Parquet shards of up to 500 responses or 64 MB, each response a row with request key (hash of method, URL and sorted parameters, no credentials), URL, parameters, `fetched_at`, HTTP status, body text and body sha256. A shard is written to a temporary file and renamed. A manifest lists each shard and its sha256. Raw files are never modified.
*   **Backup:** after each phase gate, `data/raw/` is copied to a second location (open decision). `status --verify` reports raw files missing from state and state entries without a file.
*   **State:** `data/state/<dataset>.json` records completed ranges (date ranges or stock ids), the schema era and `updated_at`, written atomically.
*   **Clean writes:** each ingest run appends new Parquet files (`run-<timestamp>.parquet`) under `data/clean/<dataset>/v<N>/year=YYYY/`. Nothing is rewritten in place. DuckDB views give (a) the first-reported row per primary key (earliest `fetched_at`), (b) a revisions view of later rows with differing values. A parser fix writes a new version directory `v<N+1>` from raw, and a pointer file switches to it. The old version stays until the author approves deleting it, so no collected data is overwritten.
*   **Snapshot job:** a stateless daily command fetches the snapshot-only sources (TWSE `TWT85U`, `TWT96U`, `BFI84U`, `TWTB4U`, `t187ap04_L`, `t187ap09_L`, `t187ap12_L`, `t187ap24_L` to `t187ap27_L`; TPEx `warning`, `sprc`), writing them through the same client and cache. Each snapshot table carries `snapshot_date` and `first_seen_at`. The run schedule is an open author decision. A missed day is reported by comparing snapshot dates against the trading calendar.

### Universe

Rebuilt on the last trading day of each month from 2015-06-30, following plan section 2. Daily prices and shares issued are collected from 2015-03-02 so the first 60-day window is complete.

1.  **Listed that day:** every code in the TWSE and TPEx daily files on that date. This includes later-delisted stocks.
2.  **Common stock only:** a code matching `^[1-9][0-9]{3}$` (four digits, so ETFs `00xx`, preferred shares with a letter suffix, and six-digit warrants and ETNs are excluded), whose `TaiwanStockInfo` industry category is not an ETF, ETN, index or depositary-receipt category, and whose name does not end in `-DR`. This rule is a proposal and is tested in spike S4. Foreign primary listings (`F-` or `KY` names) are common stocks.
3.  **Not restricted that date:** exclude stocks under disposition, or flagged in the TPEx changed-trading report, on that date. TWSE full-delivery is a documented gap.
4.  **Liquidity floor:** 60-trading-day median turnover of at least NT$20M, over observed trading days, with at least 40 observed days (parameters). Suspended days are missing, not zero. Newer listings with fewer than 40 days are ineligible.
5.  **Rank:** by market cap (`close` x `shares_issued` on the month-end), ties broken by turnover then `stock_id`. Keep the top 200.
6.  **Watchlist:** add `config/watchlist.yaml` names as extra rows with `is_watchlist` true.

A null market cap makes a stock ineligible and is counted and reported per month, so missing data cannot silently drop a delisted stock.

### Modules and ownership

| Path | Contents | Owner |
|---|---|---|
| `src/twdata/common/` | time rules, parsing, calendar, schema registry, paths, config | Lead |
| `src/twdata/clients/` | limiter, raw cache, classifier, three source clients | Lead |
| `src/twdata/ingest/` (A modules) | stock info, delistings, official daily files, market cap, status events, snapshots | Agent A |
| `src/twdata/universe/` | classification and monthly build | Agent A |
| `src/twdata/ingest/` (B modules) | corporate actions, as-of adjusted view, benchmark, price cross-check | Agent B |
| `src/twdata/ingest/` (C, D, E modules) | fundamentals; flows and positioning; macro and US | Agents C, D, E |
| `src/twdata/validate/`, `tests/validate/` | acceptance checks 1 to 8 | Agent F only |
| `src/twdata/cli.py`, `config/` | command line and settings | Lead |

### Dependency order

Lead completes Phase 0. Agent A then runs the all-stock official pass and the universe. B, C, D and E run in parallel after A's gate (B needs A's raw prices, C and D need the collection set, E needs only Phase 0). F runs last.

## Risks and Mitigations

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| IP block from TWSE, TPEx or FinMind | Medium | Run stops for 30 minutes or more | Per-host cross-process limiter, stop on any 4xx, a generic client name with no personal details, no retries on `drift` | Lead |
| Undocumented endpoint changes shape | Medium over 12 hours of requests | Dataset stale | Schema-era registry, quarantine, stop and report, no silent fallback | Lead |
| Wrong `available_at` guess leaks the future | Medium | Invalid backtests | One conservative rule, as-of adjusted views, check 6, snapshot first-seen times compared with the rule table | Lead, F |
| Survivorship returns through missing data | Medium | Biased universe | Universe built from all-stock daily files, null market caps counted, check 2 | A, F |
| Loss of the raw cache | Low | 12 or more hours to refetch, snapshot history lost | Manifest with sha256, second copy after each phase, verify command | Lead |
| Missed daily snapshot | High on a machine that sleeps | Permanent history gap | Missed-day report, run schedule (author decision), catch-up on next run for sources with a date parameter | A |
| Single source for TWSE shares issued | Medium | Mis-ranked universe | `MI_QFIIS` primary, FinMind cross-check, carry-forward limit, coverage spike S1 | A |
| Disk usage grows | Low | Run stops | Measure after the first year, report when over 70% of free space (parameter) | Lead |
| Source returns restated or corrected history | Medium | Values differ from first publication | First-reported view, revisions view, dictionary note on the 2026 start | All |
| Free-tier assumptions are wrong (paid tier needed) | Low | Gaps in P1 data | Open Questions list the unproven items, the author decides on any tier | Lead |

## Alternatives Considered

### Decision 1: source for the universe pass and prices

*   **Option A, FinMind primary.** Pro: typed API, one request per stock per dataset for the whole range. Con: the stock list and shares issued are needed for every stock first, FinMind has no shares-issued rows for at least one delisted TPEx stock (3299), and the free tier only supports per-stock calls, so the universe pass costs about 2,000 or more requests before any ranking is possible. Not chosen. The author chose B when the comparison put FinMind at about 7.5 hours against about 8 for the official route, and that FinMind figure was not derived. The research shows request counts are comparable, so the choice now rests on the survivorship and shares-issued reasons above. The author is asked to confirm B on those grounds.
*   **Option B, official primary (chosen).** Pro: one request per date covers all stocks, files include later-delisted stocks, and include shares issued and limit prices. Con: about 12 hours of unattended requests on TWSE, undocumented endpoints, custom parsing. Request counts are comparable to FinMind, so the reason for the choice is independence and the official fields, not speed.
*   **Option C, ingest both and reconcile.** Pro: conflicts found automatically across all data. Con: about double the storage and work and an undefined conflict rule. Rejected by author. The FinMind per-stock price cross-check for the collection set achieves most of the benefit.

### Decision 2: `available_at` for date-only sources

*   **Chosen: next trading day 08:30.** Rejected by author: per-dataset time rules (each time is an unverified guess that leaks the future if wrong) and real retrieval time going forward (two timing regimes in one table).
*   The rule is later than reality for events published before the open. For disposition notices it can make a restriction visible after its first session. The effect is accepted and measured through the snapshot job's `first_seen_at`.

### Decision 3: adjusted price storage

*   **A stored adjusted table, rejected by Lead:** a 2016 adjusted value depends on every action to 2026, so one `available_at` per row cannot be right.
*   **Chosen: raw prices plus actions, adjusted as of a time.** Cost: a view and a computed test instead of a stored column.

### Decision 4: idempotent writes

*   **Upsert by rewriting year partitions, rejected by Lead:** it overwrites collected data and conflicts with first-reported values.
*   **Chosen: append-only runs with a first-reported view.** Cost: compaction is a rebuild to a new version directory.

### Decision 5: libraries

*   `requests` with `urllib3.Retry` handles transient retries. No standard package gives a cross-process per-host spacing lock with a persistent timestamp, so `limiter.py` (about 60 lines, `fcntl` lock) is written. FinMind is called through its REST API directly, not the `FinMind` package, so the request headers are under this project's control. `requests-cache` was rejected because responses go to checksummed Parquet shards. `pandas` is dropped, since DuckDB and `pyarrow` cover table work. Rejected by Lead.

### Decision 6: paid tier and storage

*   A paid FinMind tier and a database server were rejected earlier by the author (`docs/DECISIONS.md` and plan section 5). Building adjusted prices in-house replaces `TaiwanStockPriceAdj` and doubles as the validation the plan asks for.

## Non-Functional Requirements

*   **Security and privacy:** `FINMIND_TOKEN` comes from the environment or a gitignored `.env` and is not written to the cache or logs. The `Authorization` header is removed before anything is cached. `data/` and `audit/events.jsonl` are gitignored. Gitleaks runs at commit, and a test asserts the header is absent from cached responses.
*   **Rollout and rollback:** nothing is deployed. Collected data is rebuilt from `data/raw/` into a new version directory. Deleting raw or an old clean version needs the author's approval.
*   **Footprint:** a TWSE daily file is about 150 KB. Raw for about 17,000 daily responses is roughly 2.5 GB before compression. Measure after the first year and report.

## Detailed Implementation Plan

Nothing below is built until the author approves the reviewed design. No modelling, backtesting or trading code is included. Prerequisites that need the author, because they change `.claude/` files or machine setup, are listed first.

### Author prerequisites

*   `.claude/agents/qa-goldfish.md`: add `Write` and `Edit` to Agent F's tools, limited by instruction to `src/twdata/validate/**`, `tests/validate/**`, `docs/COVERAGE_REPORT.md` and `docs/QA_FINDINGS.md`. Today F has no write tools and may not edit `src/`.
*   `.claude/settings.json`: add deny rules so no other agent can edit `src/twdata/validate/**` and `tests/validate/**`.
*   `.gitignore`: add `!tests/fixtures/**` so saved responses are tracked despite the global `*.parquet` and `*.csv` rules.
*   The snapshot schedule and the backup location (open decisions above).

### Phase 0 (Lead)

Create: `pyproject.toml` (setuptools backend, Python 3.11 or newer, entry point `twdata=twdata.cli:main`, ruff line length 100, rules E, F, I, B, UP), `requirements.lock` (made with `pip freeze` in a clean virtual environment, installed with `pip install -r requirements.lock && pip install -e . --no-deps`), `config/settings.yaml` (start date, window start 2015-03-02, liquidity floor, minimum observed days, universe size, per-host spacing 5, breaker threshold 3, cooldown 900, tolerances, seeds, backup directory), `config/watchlist.yaml` (empty), `src/twdata/__init__.py`, `src/twdata/common/{__init__,timeutil,parsing,tradingcal,schema,paths,config}.py`, `src/twdata/clients/{__init__,base,limiter,rawcache,finmind,twse,tpex}.py`, `src/twdata/cli.py`. `tradingcal.py` is named to avoid the standard library module `calendar`.

Gate: `pytest tests/` passes offline, spikes S1 to S6 are recorded in `docs/OFFICIAL_SOURCES.md`, and the author prerequisites are done.

### Phase 1 (Agent A)

Create: `src/twdata/ingest/{__init__,stock_info,delistings,daily_official,market_cap,status_events,snapshots}.py`, `src/twdata/universe/{__init__,classify,build}.py`. `snapshots.py` is built first and the daily snapshot job starts as soon as it passes its tests, before the long official-file run, because each day of delay loses snapshot history for good. `daily_official.py` then collects `prices_raw`, `shares_issued` and limit prices for all stocks of both markets from 2015-03-02.

Gate: check 8 passes on a full run (exactly 200 ranked members each month-end, 2330 present, shortfall months reported), and `status --verify` is clean.

### Phase 2 (Agents B, C, D, E in parallel)

Create: B `ingest/{corporate_actions,adjusted,benchmark,price_crosscheck}.py`; C `ingest/{monthly_revenue,financials,valuation}.py`; D `ingest/{flows_institutional,shareholding,margin,securities_lending,day_trading}.py`; E `ingest/{us_prices,fx,rates,futures}.py`. Each also creates its own data dictionary file: `docs/data_dictionary/{a,b,c,d,e}.md`, and the Lead owns `docs/DATA_DICTIONARY.md` as an index linking them (so no file has two writers).

Gate per agent: unit tests pass, and a one-month, five-stock run (month 2020-06, stocks 2330, 2317, 2454, 6488 and 2475) into a temporary data directory, run twice, produces no duplicate rows in the as-of views.

### Phase 3 (Agent F, then the improve loop)

Create: `src/twdata/validate/{__init__,check_01_coverage,check_02_survivorship,check_03_adjusted,check_04_crosssource,check_05_limits,check_06_pointintime,check_07_keys_units,check_08_universe,report}.py`, `tests/validate/test_check_0{1..8}.py`, `docs/COVERAGE_REPORT.md`, `docs/QA_FINDINGS.md`. F fetches cross-check data (FinMind prices, Yahoo `Adj Close`) through the Lead's clients and a `qa` cache namespace.

Gate: all eight checks pass with zero failing keys, or the failures go to `docs/QA_FINDINGS.md` tagged by owner. At most three rounds, logged in `docs/ITERATION_LOG.md`. Anything still failing goes to the author.

### Command line (Lead)

`python -m twdata fetch --dataset NAME --start DATE --end DATE [--data-dir PATH]`; `status [--dataset NAME] [--verify]`; `snapshot`; `rebuild-universe --from DATE --to DATE`; `limiter-check` (prints the FinMind limit read from user-info, the computed rate and the per-host spacing). Exit codes: 0 success, 2 usage error, 3 stopped on a block or auth error, 4 schema drift. No command deletes data.

### Tests (owners write their own)

Files: `tests/conftest.py`, `tests/test_{parsing,timeutil,tradingcal,limiter,rawcache,clients_twse,clients_tpex,clients_finmind,snapshots,adjusted,universe_classify,universe_build}.py`, `tests/test_ingest_<module>.py` for each ingest module, and `tests/fixtures/**` (saved responses with no token, one per schema era per endpoint, each at most 300 KB).

Cases (inputs and expected outputs):

*   Parsing: `104/06/01` gives 2015-06-01. `113/02/29` gives 2024-02-29. `1,234,567` gives 1234567. `--` and blank give null. The HTML sign snippet `<p style= color:green>-</p>` gives -1, and a red `+` gives +1. A leading tab in a name is stripped.
*   Client classification: an HTML page with HTTP 200 is `drift`. `stat` not OK on a trading day is `drift`. Zero rows on a calendar holiday is `valid_empty`. HTTP 500 is `transient` and retried five times. Three `drift` responses open the breaker. A probe after 900 seconds on a fake clock succeeds or stops the run.
*   Limiter: two requests to one host are at least 5 seconds apart on a fake clock, including from two processes sharing the lock file. The FinMind rate is derived from the user-info value.
*   Security: the cached request record contains no `Authorization` header. A 401, 402 or 403 from FinMind stops the run.
*   Raw cache: a killed write leaves no partial shard. Resume after interruption fetches only missing ranges. A manifest sha256 mismatch is reported.
*   `available_at`: a Friday source date gives Monday 08:30. A source date before the 9-day Lunar New Year break gives the first trading day after it. A revenue month whose 10th is a Saturday gives Monday 18:00, and a Tuesday 10th gives Tuesday 18:00. The Q3 deadline 14 November 2020 (a Saturday) gives Monday 16 November 08:30. A date beyond the loaded calendar gives null.
*   Adjusted view: the worked example in "Adjusted prices" gives 95 on day 1 as of day 2 08:30 and the unadjusted 100 before it. Two same-day actions multiply.
*   Universe: 0050, a six-digit warrant, a preferred share and a `-DR` name are excluded, and 2330 is included. A stock with 39 observed days is ineligible and one with 40 is eligible. A shortfall month keeps all passing stocks and reports the count. Ties break by turnover then `stock_id`.
*   Validation checks: each check has a synthetic dataset with a known gap or error that the check must report.

### Verification Plan

*   **Build:** `pip install -r requirements.lock && pip install -e . --no-deps` succeeds.
*   **Unit tests:** `pytest tests/` passes with no network.
*   **Static analysis:** `ruff check src tests`.
*   **Coverage requirement:** every parser, every `available_at` rule and every response class has at least one test.
*   **Integration, small:** the one-month, five-stock run described under Phase 2, twice, with no duplicates and no network beyond the clients.
*   **Integration, full:** after the full collection (about 12 hours unattended), agent F's eight checks run, and the pass condition is zero failing keys or listed exceptions.

--------------------------------------------------------------------------------

*Drafted with EGM, revised by the Lead after review*
