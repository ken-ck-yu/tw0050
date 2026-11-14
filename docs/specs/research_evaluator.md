# Research evaluator spec (early lane, frozen)

Implements `docs/amendments/early_lane.md`. The evaluator is written once, before any strategy, by an evaluator agent that is separate from every strategy agent. After merge it is frozen: nobody edits `src/twdata/research/evaluator/**` except by the author's approval. Standard library, `duckdb` and `pyarrow` only (no new dependencies). Offline tests with synthetic data.

## Files and owners
*   Evaluator agent owns: `src/twdata/research/__init__.py`, `src/twdata/research/evaluator/{__init__,constants,data,costs,engine,metrics,log}.py`, `tests/research/evaluator/**`, `docs/data_dictionary/research_evaluator.md`, `research/EVALUATOR_SHA256`, `audit/runs/2026-11-14_evaluator_1.md`.
*   Strategy agents own: `src/twdata/research/strategies/**`, `tests/research/strategies/**`, `research/cards/**`, `research/runs/**`. They may import the evaluator, never edit it.
*   Lead owns: `scripts/make_research_data.py`, `config/ownership.yaml`, `config/settings.yaml` (key `research`).

## Development data only (sealed holdout)
`scripts/make_research_data.py` (Lead) writes `data/research/` with Parquet copies of the needed tables (`universe_membership`, `prices_raw`, `adjusted_prices`, `price_limits`, `status_events`, `monthly_revenue`, `benchmark_index`, `trading_calendar`) **filtered to `event_date <= dev_end` (2024-06-30; `month_end <= dev_end` for universe_membership)**. The evaluator's loader reads only `data/research/` and refuses any date range that ends after `dev_end` (`HoldoutError`). The evaluator contains no path to `data/clean/`. (Limit stated honestly: an agent with shell access could still read `data/clean/`; that is covered by the instruction in the amendment and by the ownership audit, not by a technical barrier.) Dates: train 2015-06-01 to 2021-12-31, validation 2022-01-01 to 2024-06-30.

## Interface
```
Weights = dict[str, float]                      # stock_id -> target weight, long only
@dataclass TargetBook: decision_date: date; weights: Weights
load_dev_data(settings, start, end) -> DevData  # raises HoldoutError if end > dev_end
run_backtest(data, books: list[TargetBook], *, card_id: str, params: dict, window: str)
    -> RunRecord                                # also appends to research/experiment_log.jsonl
```
A strategy produces `TargetBook`s using only rows whose `available_at <= 18:00 Taipei on decision_date` (the strategy loader `DevData.as_of(decision_date)` enforces it: it returns only rows with `available_at` on or before that time). The evaluator executes each book at the **next trading day's open**.

## Execution and accounting rules (all constants in `constants.py`)
*   `COMMISSION = 0.001425` per side (full list price, no discount). `SELL_TAX_STOCK = 0.003`, `SELL_TAX_ETF = 0.001` (ETF = code not matching `^[1-9][0-9]{3}$`). `SLIPPAGE = 0.001` per side. Buy cost per unit notional `COMMISSION + SLIPPAGE`, sell cost `COMMISSION + SLIPPAGE + tax`. `ANNUALIZATION = 244`. `MAX_WEIGHT = 0.10`, gross weight at most 1.0 (a book violating either raises `BookError`, it is not clipped).
*   Tradeable on the execution date `E`: the stock is in `universe_membership` for the latest `month_end` whose `available_at <= 18:00 on decision_date`; it has a `prices_raw` row on `E` with a non-null open; it is not covered by a `disposition` or `changed_trading` event window (`start_date <= E <= end_date`). A target weight for a non-tradeable name is dropped to cash and recorded.
*   Fills at `E`'s raw open. **Limit lock:** a buy does not fill when `open >= limit_up` (from `price_limits` for `E`, null limits mean no lock); the weight stays in cash for that interval. A sell does not fill when `open <= limit_down`; the position is held and the sell is retried at each following trading day's open, at most 5 days, then forced at the 5th open. An unfilled sell keeps earning that stock's return.
*   Return of a held name from entry open `E` to exit open `X` uses adjusted prices: `adj_open(d) = open(d) * adjusted_close(d) / close(d)` with `adjusted_close` fully adjusted (dividends, capital reductions, splits). The evaluator does not compute adjustments: it reads the table `adjusted_prices` in `data/research/` (columns `market, stock_id, event_date, open, close, adjusted_close`), which the Lead's `scripts/make_research_data.py` builds from Agent B's `adjusted_series(con, as_of=None)` and filters to `event_date <= dev_end`. The evaluator's own tests build small synthetic `adjusted_prices` tables. Interval return = `adj_open(X) / adj_open(E) - 1`. Costs are charged on trade notional at the interval boundaries. Cash earns zero.
*   Daily mark-to-market for drawdown and volatility: positions are marked at each day's `adjusted_close`. Daily portfolio return is the weighted sum of constituents' adjusted close-to-close returns, with the entry day starting from the open fill and the exit day ending at the open fill (the open-to-close and close-to-open split is applied the day of each fill). Costs are deducted on the fill day.
*   Benchmark: 0050 buy and hold, adjusted open-to-open, over the same window, no costs after the initial buy (sell tax at the end is applied like a strategy exit so the comparison is fair).

## Metrics (`RunRecord`)
Window dates, number of books and fills, `net_total_return`, `net_annual_return`, `net_annual_vol`, `net_sharpe` (mean daily net return over standard deviation times sqrt(244), zero risk-free), `gross_sharpe`, `max_drawdown`, `annual_turnover` (sum of one-way traded notional per year), `annual_cost_drag`, `benchmark_*` (same metrics for 0050), `excess_annual_return`, `hit_rate_monthly` (share of months with net return above the benchmark), `unfilled_buys`, `blocked_sells`, `dropped_non_tradeable`, `n_trials` (number of rows in `research/experiment_log.jsonl` including this one), `deflated_sharpe` (Bailey and Lopez de Prado: probability that the true Sharpe is positive after N trials, using `statistics.NormalDist`, the log's trial Sharpe variance when N >= 3 and 0.5 times the observed Sharpe otherwise, skewness and kurtosis of this run's daily returns), `evaluator_sha256`, `card_id`, `params_hash`, `window`, `run_id` (UUID), `created_at`.

## Experiment log and freeze
Every run appends one JSON line to `research/experiment_log.jsonl` (failures too: an exception inside `run_backtest` appends a line with `status: "error"` and the message, then re-raises). The budget is 10 runs per cycle: the 11th run in a cycle (field `cycle` in `config/settings.yaml: research.cycle`) raises `BudgetError`. `research/EVALUATOR_SHA256` holds the SHA-256 of the concatenated bytes of the evaluator files in sorted order. A test in `tests/research/evaluator/test_frozen.py` fails when the files and the hash differ (so any change needs the hash file updated, which the ownership audit shows as an evaluator-path edit needing the author).

## Tests (offline, synthetic)
Cost arithmetic for a buy and a sell (stock and ETF), the next-open execution timing, the limit-lock buy and sell paths (including the forced sell on the 5th day), the tradeable mask (membership, disposition window, missing open), max-weight and gross rejection, the adjusted return through a 4-for-1 split (continuous), the benchmark, the Sharpe, drawdown and turnover on a hand-computed two-asset example, the holdout refusal (`HoldoutError` for an end after `dev_end`), the budget error on the 11th run, the log lines (including an error line), deflated Sharpe on known inputs, the frozen-hash test.
