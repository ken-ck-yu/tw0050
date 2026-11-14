# Agent A (part 2): status events, stock info, delistings, universe

Sources: TWSE `punish`, TPEx `disposal` and `chtm` (official), FinMind `TaiwanStockInfo` and `TaiwanStockDelisting`. Code: `ingest/status_events.py`, `ingest/stock_info.py`, `ingest/delistings.py`, `universe/classify.py`, `universe/build.py`. All timestamps are stored in UTC; rules compute in Asia/Taipei. Default views: `source_error` and `none` tables use `default_<t>` = latest-corrected.

## status_events (joinable, source_error)

Key `market, stock_id, status_type, start_date`. Columns: `market` (TWSE/TPEx), `stock_id`, `status_type` (`disposition`, `changed_trading`), `announce_date` DATE?, `start_date` DATE, `end_date` DATE?, `detail` VARCHAR?, plus `event_date`, `available_at`, `fetched_at`. Every code is stored (ETFs, warrants, receipts included); the universe filters.

*   **disposition**: TWSE `punish` (公布日期 -> `announce_date`; 處置起迄時間 `104/09/25～104/10/12`, full-width tilde -> `start_date`, `end_date`; 處置措施 -> `detail`) and TPEx `disposal` (處置起訖時間 `104/06/30~104/07/13`; 處置原因 -> `detail`). `event_date = announce_date`, `available_at` = next trading day 08:30 after `announce_date` (null while the calendar does not reach it). Rows with an empty code are skipped (TPEx pads results with blank rows). A coded row with a missing or malformed range is `ParseError`. A repeated key inside one batch keeps the first row in response order. One request per calendar year per host; a rerun is served from the raw cache, so a still-running year is not refreshed unless the range changes.
*   **changed_trading**: TPEx `chtm`, one request per trading day. A stock is flagged on a day when any of 變更交易, 分盤交易, 屬管理股票 is non-empty. Runs of consecutive trading days per stock become one event: `start_date` first day seen, `end_date` last day seen, `announce_date` null, `detail` null, `event_date = start_date`, `available_at` = next trading day 08:30 after `start_date`. Limits: a state already present on the first day of a requested range has that day as `start_date` unless a stored event ends on the previous trading day, which is then extended (resume reads `default_status_events`). `end_date` of a run still open at the end of the requested range is hindsight (last day seen so far); extending it later writes a revision of the same key. Use `[start_date, end_date]` only as a coverage mask, never `end_date` as a feature. A null `end_date` means "covers all later dates" in the universe. Processing is chunked per calendar year. The TPEx `停止交易` column is ignored (`halt` is not in the status_type registry; it would need a Lead request).
*   TWSE full-delivery status has no source (accepted gap). TPEx `chtm` may fold full delivery into the same flag (inferred, S12).

## stock_info (reference, none)

Key `stock_id, event_date`. Columns `stock_name`, `industry_category` ('' when null), `type` (source `type`: `twse`, `tpex`, emerging), `event_date` = source `date` (meaning unverified, S6), `fetched_at`. No `available_at`: never a feature join. The whole table is requested with `start=2000-01-01`, no end, whatever the run range. Rows with a null or unparseable `date` are skipped and counted (`stock_info.SKIPPED`). A duplicate key stops the run (`KeyUniquenessError`) after writing the keys to `data/state/stock_info_duplicates.json`. Columns outside the five source columns are drift.

## delistings (reference, none)

Key `stock_id, event_date`; `stock_name`; `event_date` is the delisting date. Fetched with `start=2000-01-01`. Same skip, duplicate and drift rules. FinMind row counts differed between probes (690 vs 726); the TPEx part was backfilled by FinMind on 2026-09-01. The last trade is typically 1 to 13 days before the delisting date: use `listing_status` from daily files for the last trading day.

## universe_membership (derived, none; part `month_end`)

Key `month_end, stock_id`. Columns: `month_end`, `stock_id`, `isin` (from `shares_issued` that day, TWSE only), `market`, `rank` BIGINT? (1-based, null for watchlist extras and the benchmark), `market_cap_ntd`, `median_turnover_60d`, `is_watchlist`, `is_benchmark`, `available_at`, `fetched_at`.

Rule per month-end (the last trading day of each month from 2015-06, within the requested range; the calendar's final month is skipped when the calendar stops before the month's last calendar day):
1.  Listed: `prices_raw` rows on the date, common stocks only (`is_common_stock`: `^[1-9][0-9]{3}$` and the name, after `clean_name`, not ending `-DR`; 0050, ETFs, letter suffixes and six-digit codes are out).
2.  Excluded when a `disposition` or `changed_trading` event of the same market and code covers the date (`start_date <= d <= end_date`, null end open).
3.  Median `turnover_ntd` over the last 60 calendar trading days up to the date, counting only days with `turnover_ntd > 0`; at least `min_observed_days` observed days and median `>= liquidity_floor_ntd`. Stocks are matched by `stock_id` across markets in this window.
4.  Market cap from `default_market_cap` on the date; a missing one makes the stock ineligible and is counted.
5.  Rank by `market_cap_ntd` desc, `median_turnover_60d` desc, `stock_id` asc; top `universe_size`.
6.  Watchlist (`config/watchlist.yaml`): applies from the first month-end on or after `start_date`; `is_watchlist` true; a ranked stock keeps its rank. A name with no `prices_raw` row that day gets no row.
7.  Benchmark 0050: a row every month-end with `is_benchmark` true, `rank` null.
Values without an input (benchmark or watchlist name lacking market cap or turnover) are 0.0, a sentinel for "unavailable". `available_at` = max(month-end 18:00 Taipei, latest `available_at` of the status events covering the date); null if one of those is pending. Restatement class `none`; a later rebuild that would drop a stored row raises `UniverseConflict` (append-only store), so rebuild over the full range with `new_version=True`, which writes `v<N+1>` of both tables and switches `CURRENT` (old versions stay).

`data/state/universe_shortfall.json`: `{"YYYY-MM-DD": {"members": n, "shortfall": universe_size - n, "null_market_cap": k}}` for every month-end built. `assert_universe(rows)` (M1 gate) checks `universe_size` ranked members (or a recorded shortfall) and 2330 present each month.

## collection_set (reference, none; part `first_month_end`)

Key `stock_id, first_month_end`: first and last month-end in `universe_membership`, `ever_watchlist`, `is_benchmark`. Computed from all membership rows (stored months outside the rebuilt range plus the new ones). A list used to choose stocks to fetch, not a feature input.

Caveats: ranks depend on `market_cap` (A-1) and on the clean `status_events`; the first window needs prices from 2015-03-02. A code reused by another company inside the 60-day window is not separated.
