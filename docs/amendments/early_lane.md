# Amendment: early research lane (approved by the author on 2026-11-14)

Proposed and approved 2026-11-14. Rule 3 in `CLAUDE.md` points here. The split dates in point 4 stand as written.

## Why

The author wants a fast signal on whether the strategy can make money. `CLAUDE.md` rule 3 and plan section 10 start research only after all of Phase 1 data has passed QA, which is roughly 20 hours of requests plus improve rounds.

## Replacement for rule 3

> 3. **No modelling, backtesting, broker or trading code in Phase 1, except the early lane in `docs/amendments/early_lane.md`.** Broker, order and live-trading code stay forbidden everywhere.

## The early lane

1. **When it opens.** Only after milestone M1 (prices and universe) and the `monthly_revenue` dataset have each passed their offline and live gates in the design. Until then no research code exists.
2. **Scope.** One hypothesis at a time, starting with plan section 10.5's first seed: drift after monthly revenue surprises. Cost model and universe come from the design's tables, not from new data sources.
3. **Frozen evaluator.** One module, written before any strategy, with full costs (0.3% sell tax, commission, slippage, limit-lock fills using `price_limits`). It is owned by an evaluator agent that is separate from every strategy agent. Strategy agents cannot edit it. The author approves any change to it.
4. **Data splits (proposed dates, the author sets the final ones).** Development window 2015-06-01 to 2024-06-30, split into train 2015-06 to 2021-12 and validation 2022-01 to 2024-06. **Sealed holdout 2024-07-01 to the latest date.** Agents cannot read the holdout: it is not loaded into the research data directory, and the research code has no path to it. Only the author unlocks it, once, for one shortlisted strategy.
5. **Test budget.** At most 10 backtests per cycle. Every run is logged, including failures, in `research/experiment_log.jsonl` (run id, hypothesis card, parameters, window, result). Results are discounted for the number of attempts (deflated Sharpe ratio or the equivalent chosen in the evaluator spec).
6. **Hypothesis card first.** Each test starts with a committed card (claim, mechanism, data and its `available_at` logic, holding period, predicted effect and what result would falsify it). Plan section 10.3 sets the template.
7. **Provisional results.** Every result is labelled provisional until the full Phase 1 QA has passed. A provisional result may inform the next hypothesis but cannot be used to select a strategy for the holdout.
8. **Validation uses the dates, not hindsight.** Features join only on `available_at`. Labels may use the fully adjusted series.
9. **Unchanged:** the full Phase 1 collection and QA continue in parallel. No broker, order or live-trading code. No secrets or data in git.

## What the author sees after each run

One result record per tested hypothesis: test window, Sharpe after costs, benchmark 0050 over the same window, annual turnover and cost drag, maximum drawdown, attempts so far in the cycle, deflated Sharpe, and whether the card's falsification rule was triggered.

## Risks accepted by choosing the early lane

*   The data has not passed the full QA, so a result can come from a data defect (a missing split, a wrong `available_at`). Provisional labelling and check 3(b) are the guard.
*   Early results tempt strategy selection on the development window. The test budget, the sealed holdout and the rule in point 7 are the guard.
