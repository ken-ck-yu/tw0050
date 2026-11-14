# Data dictionary: Agent B seed data (corporate actions, adjusted prices, price limits, benchmark)

Code: `src/twdata/ingest/{corporate_actions,adjusted,price_limits,benchmark}.py`. All times are stored as UTC `TIMESTAMPTZ`; rules compute in Asia/Taipei.

## `corporate_actions` (joinable, restatement `source_error`, default view latest-corrected)

Key `market, stock_id, event_date, action_type`. Columns: `market` (`TWSE`/`TPEx`), `stock_id`, `event_date` (the ex-date, or the resumption date for a reduction), `available_at`, `fetched_at`, `action_type` (`ex_dividend`, `ex_rights`, `capital_reduction`, `split`, `par_value_change`), `prev_close` DOUBLE? (NT$), `reference_price` DOUBLE? (NT$), `halt_close` DOUBLE? (reductions and manual rows), `ratio` DOUBLE? (manual rows only), `cash_dividend` DOUBLE? (NT$/share), `stock_dividend_per_1000` DOUBLE? (shares per 1,000 held), `reduction_reason` VARCHAR?.

| Source | Endpoint (windows) | Field mapping |
|---|---|---|
| TWSE TWT49U | `twse.twt49u`, one call for the whole span | `資料日期` (`114年01月02日`) to `event_date`; `股票代號`; `除權息前收盤價` to `prev_close`; `除權息參考價` to `reference_price`; `權/息`: `權` and `權息` to `ex_rights`, `息` to `ex_dividend`. `cash_dividend` and `stock_dividend_per_1000` are null: the feed only has `權值+息值` (the sum). Lists ETFs as well as stocks. |
| TWSE TWTAUU | `twse.twtauu`, one calendar year per call | `恢復買賣日期` to `event_date`; `股票代號`; `停止買賣前收盤價格` to `halt_close` and `prev_close`; `恢復買賣參考價` to `reference_price`; `減資原因` to `reduction_reason`; `capital_reduction`. |
| TPEx exDailyQ | `tpex.ex_daily`, one calendar year per call | `除權息日期`; `代號`; `除權息前收盤價`; `除權息參考價`; `權/息` (`除權`, `除息`, `除權息`; `除權息` is `ex_rights`); `現金股利` to `cash_dividend`; `每仟股無償配股` to `stock_dividend_per_1000`. |
| TPEx revivt | `tpex.revivt`, one calendar year per call | `恢復買賣日期` (7-digit ROC, `1040130`); `股票代號`; `最後交易日之收盤價格` to `halt_close` and `prev_close`; `減資恢復買賣開始日參考價格` to `reference_price`; `減資原因`; `capital_reduction`. |
| Manual file | `config/manual_corporate_actions.yaml` | one row per entry (`market, stock_id, action_type, event_date, halt_close, reference_price, ratio`); `prev_close = prev_close` if given else `halt_close`. `fetched_at` is the file's modification time (UTC). Entries outside `[start, end]` are not written. |

`available_at = avail_next_day_0830(event_date)`: 08:30 Taipei on the next trading day after the event date; null (pending, filled by a later run) when the calendar does not reach it. `fetched_at` is the raw response's `fetched_at`.

Key collisions inside one run (for example `權` and `權息` both mapping to `ex_rights`): the first row in response order is kept; the count is logged (WARNING) and quoted in the run report.

**The ex-date artefact.** The event for an ex-date `d` is only joinable from the next trading day 08:30, but the raw price of `d` is already published at 18:00 on `d`. Between those two times the price of `d` is unadjusted and a feature built from it would see a spurious drop. `adjusted_series` marks those dates with `is_ex_date_window = true` when `as_of` is given and the event is not yet available at `as_of` (or has a null `available_at`). Consumers must drop or hold those rows.

**Manual file.** Splits and par-value changes are in no official feed (S8). One entry at M0: 0050, `split`, 2025-06-18, `ratio` 4, `halt_close` 188.65, `reference_price` null (no exchange document exists; press gives 47.32 and 47.16, so no reference price is entered). Every `split` and `par_value_change` row is adjusted by exactly `1/ratio`, whatever its `reference_price` (informational only).

## Adjusted prices (computed, not stored)

`adjusted_series(con, as_of=None, stock_ids=None, *, only_available_prices=False)` returns a pyarrow table `(market, stock_id, event_date, close, factor, adjusted_close, is_ex_date_window)` over the views `default_prices_raw` and `default_corporate_actions` (the connection needs `views.register_views`). The view `adjusted_close` is the same query with `as_of = infinity` and is labelled **validation and labels only, not a feature input**. Features call `adjusted_series(as_of=T)`.

Factor of one event: `reference_price / prev_close` for `ex_dividend`, `ex_rights` and `capital_reduction` (`prev_close` falls back to `halt_close`), `1 / ratio` for `split` and `par_value_change`. For the first three, a null `reference_price` also falls back to `1/ratio` when a ratio exists. An event whose factor cannot be computed (null `prev_close` or null `reference_price` without a ratio, or a split without a ratio) gets factor 1.0 and is counted in the module counter `adjusted.UNCOMPUTABLE_EVENTS`.

`adjusted_close(t) = close(t) * product of factors of events with event_date > t` and, when `as_of` is given, `available_at <= as_of`. Two events on one date multiply. Price rows are not filtered by their own `available_at` unless `only_available_prices=True`. Worked example: close 100 on day 1, ex-dividend on day 2 (`prev_close` 100, `reference_price` 95, `available_at` day 3 08:30): adjusted close of day 1 is 100 as of any earlier time and 95 from day 3 08:30.

## `price_limits` (joinable, `source_error`)

Key `market, stock_id, event_date`. `limit_up`, `limit_down` DOUBLE? (NT$). TWSE: `twse.twt84u(d)` gives the limits for `d` (`漲停價`, `跌停價`; the duplicate field `開盤競價基準` arrives as `開盤競價基準` and `開盤競價基準#2` and is not stored). TPEx: the `otc` file of trading day `p` carries `次日漲停價`/`次日跌停價`; they are stored on `next_trading_day(p)`, read cache-first through `ctx.tpex.otc`. The first window day has no TPEx limit row of its own (it would come from the file before the window). The sentinels 9999.95 (up) and 0.01 (down) and `--` cells are null. `available_at` is 18:00 Taipei on the event date. A `limit_down` above `limit_up` raises `SanityError`.

## `benchmark_index` (joinable, `source_error`)

Key `index_id, event_date`; `value` DOUBLE (index points). `TAIEX_TR` is row `發行量加權股價報酬指數` and `TAIWAN50_TR` row `臺灣50報酬指數` of the `報酬指數` table of `MI_INDEX` (`收盤指數`); a missing row is drift. `TPEX_TR` is FinMind `TaiwanStockTotalReturnIndex` with `data_id = TPEx` (column `price`), skipped with a warning without a FinMind client; its `fetched_at` is the time the call returned. `available_at` is 18:00 Taipei on the event date.

## Caveats

* The 18:00 same-day rule is untested until spike S10.
* `cash_dividend` and `stock_dividend_per_1000` are null for TWSE rows.
* Early 2015 `MI_INDEX` may lack the `報酬指數` table; the run would stop with drift.
* The adjustment approximates total return; it does not prove the official reference prices right (check 3).
