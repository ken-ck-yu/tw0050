# Research evaluator (early lane, frozen)

Code: `src/twdata/research/evaluator/`. Spec: `docs/specs/research_evaluator.md`. Rules: `docs/amendments/early_lane.md`. Every result is provisional until the full Phase 1 QA has passed.

## Inputs
Parquet files `<data_dir>/research/<table>.parquet` for `universe_membership, prices_raw, adjusted_prices, price_limits, status_events, monthly_revenue, benchmark_index, trading_calendar` (columns as in `src/twdata/common/schema.py`; `adjusted_prices` has `market, stock_id, event_date, open, close, adjusted_close`). Timestamps are UTC TIMESTAMPTZ. `load_dev_data(settings, start, end)` raises `HoldoutError` when `end > settings.research.dev_end`, and keeps only rows with `event_date <= end` (`month_end` for the universe) and `available_at <= 18:00 Taipei on end`. History before `start` is kept for `monthly_revenue`, `status_events`, `universe_membership` and `trading_calendar`. `benchmark_index` is loaded but not used (the benchmark is 0050 from `adjusted_prices`).

`DevData.as_of(d).table(name)` returns rows with `available_at <= 18:00 Asia/Taipei on d` (rows with null `available_at` are never returned; `trading_calendar` has no `available_at` and is filtered on `event_date <= d`). `adjusted_prices` is refused (`DataError`): it embeds later corporate actions, so features must use `prices_raw`.

## Constants (`constants.py`)
`COMMISSION 0.001425`, `SELL_TAX_STOCK 0.003`, `SELL_TAX_ETF 0.001` (ETF = code not matching `^[1-9][0-9]{3}$`), `SLIPPAGE 0.001`, `ANNUALIZATION 244`, `MAX_WEIGHT 0.10`, gross at most 1.0, `MAX_SELL_DEFER_DAYS 5`, benchmark `0050`. Windows: `train` 2015-06-01..train_end, `validation` train_end+1..dev_end, `dev` 2015-06-01..dev_end.

## Rules as implemented
*   **Book checks** (raise `BookError`, never clipped): weights finite, non-negative, each at most 0.10, gross at most 1.0 (tolerance 1e-9); one book per decision date and per execution date; decision date inside the window; execution day exists, inside the window and the loaded data.
*   **Execution.** A book decided on date D executes at the open of the next trading day E (trading_calendar days with `is_trading`). Targets are fractions of NAV at E's open (after the overnight move). A book is a full target: names absent from it go to 0. Positions are rebalanced to target on book days only (no drift rebalancing in between).
*   **Tradeable mask** on E, in this order of reason: not in `universe_membership` for the latest `month_end` whose `available_at` is at or before D 18:00 (any row of that month, watchlist rows included); no `prices_raw` row with non-null open on E; no `adjusted_prices` open on E (extra, conservative); inside a `disposition` or `changed_trading` window (`start_date <= E <= end_date`, null end means open-ended; rows count when `available_at` is null or at or before D 18:00; `attention` does not block). A dropped target is held as cash and listed in `dropped_detail` (`[decision_date, stock_id, reason]`, first 200 in the log line; the count is exact). The mask gates buys. A held name that is not re-targeted is sold regardless (a sell needs only an open).
*   **Fills** at E's raw open. Buy: not filled when `open >= limit_up` (null limit = no lock); counts in `unfilled_buys`. Sell: not filled when `open <= limit_down`; held, retried at the next trading open, the 5th attempt open is forced (`blocked_sells` counts blocked attempts, `forced_sells` the forced fills). A day with no print does not consume an attempt. Sells are processed before buys; buys are scaled down together when cash (after sell proceeds and costs) cannot fund them including their cost.
*   **Returns.** `adj_open = open * adjusted_close / close`. Positions are carried on the adjusted scale: close(d-1) to open(d) uses `adj_open(d) / last mark`, open to close uses `adjusted_close / adj_open`. A day with no adjusted price leaves the mark unchanged (flat), and the next price day books the whole gap. Costs are charged on notional on the fill day. Cash earns zero.
*   **End of window.** The portfolio is liquidated at the open of the last trading day `L <= min(data.end, window_end)` (sell cost and tax apply, limit locks do not). The series has one return per trading day from the first execution to `L`.
*   **Benchmark.** 0050 (`adjusted_prices`) bought at the first execution open with buy costs and sold at `L` with the ETF sell cost, same day grid, no limit logic, no mask.

## Outputs (`RunRecord`, one JSON line in `research/experiment_log.jsonl`)
Window dates and `first_execution`, `last_day`, `n_days`, `n_books`, `n_fills` (filled orders). Returns: `net_total_return`, `net_annual_return` (`NAV^(244/n_days) - 1`), `net_annual_vol` (sample std times sqrt(244)), `net_sharpe` (mean over std times sqrt(244), zero risk-free), `gross_sharpe` (daily net return plus the day's costs over previous NAV), `max_drawdown` (a number at most zero, peak starts at 1.0). `annual_turnover` = (sum of buy notional + sum of sell notional, each over NAV at that day's open) per year, **two-sided**; `annual_turnover_one_way` is half. `annual_cost_drag` = sum of costs over NAV at the open, per year. `benchmark_*` the same for 0050. `excess_annual_return`, `hit_rate_monthly` (share of calendar months where the strategy's compounded return beats the benchmark's), counters above, `n_trials` (all log rows including this one, error rows too), `deflated_sharpe`, `evaluator_sha256`, `card_id`, `params_hash` (sha256 of the sorted-key JSON of `params`), `window`, `run_id`, `created_at` (UTC), `cycle`, `params`, `status` (`ok`), `provisional` (always true). The in-memory record also has `daily` = `(date, net_return, benchmark_return)` (not logged).

**Deflated Sharpe** (Bailey and Lopez de Prado), daily units: `Phi((SR - SR0) * sqrt(T-1) / sqrt(1 - g3*SR + (g4-1)/4*SR^2))`, `SR0 = sqrt(V) * ((1-gamma) * Phi^-1(1-1/N) + gamma * Phi^-1(1-1/(N e)))`. `N = n_trials`. `V` is the sample variance of the logged `ok` runs' net Sharpe (daily units, this run included) when `N >= 3`, otherwise `(0.5 * SR)^2`. `N = 1` gives `SR0 = 0`. `g3` and `g4` are the population skewness and raw kurtosis of this run's daily returns. A non-positive variance term gives 0.0.

## Experiment log and budget
Lines are appended under a file lock. Error lines (`status: "error"`, `error_type`, `message`, no metrics) are written for any exception inside the run, then the exception is re-raised. The budget is `settings.research.max_runs_per_cycle` rows (ok and error) whose `cycle` equals `settings.research.cycle`: the next call raises `BudgetError` before doing any work and writes nothing. Corrupt log lines count as runs.

## Freeze
`research/EVALUATOR_SHA256` = SHA-256 of the concatenated bytes of `src/twdata/research/evaluator/*.py` in sorted file-name order (`log.evaluator_sha256()`). `tests/research/evaluator/test_frozen.py` fails when they differ.

## Known limits
*   Suspended names are carried flat (no mark-down); a name with no open at `L` is closed at its last mark.
*   No intraday limit modelling beyond the open test; no volume or capacity limit; fills are always complete at the open price plus 0.1% slippage.
*   Weights drift between books (no rebalance), so a held name can exceed 10% between books.
*   An agent with shell access can read `data/clean/`; the code has no path to it, the rest is the ownership audit.
*   The gross series approximates "no costs" by adding each day's costs back to that day's return; it does not remove the compounding effect of earlier costs.
