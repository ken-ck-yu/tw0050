# Agent C spec (M2, seed data): monthly revenue

Builds on `docs/specs/m0_specs.md` (sections 2, 5, 7, 8, 15 apply). One builder, own git worktree. Owns only: `src/twdata/ingest/monthly_revenue.py`, `tests/agent_c/**`, `tests/fixtures/agent_c/**`, `docs/data_dictionary/c_monthly_revenue.md`, `audit/runs/2026-11-14_agent_c_1.md` (include what in the instructions was missing, ambiguous or wrong). No network access: tests use `tests/fixtures/lead/finmind/TaiwanStockMonthRevenue_2330_trimmed.json` and a fake transport. Same conventions as Agent A's spec.

**`monthly_revenue.py`** (`DATASETS = {"monthly_revenue": run}`): stock list = distinct `stock_id` of the clean table `collection_set` (read through DuckDB, `views.register_views`, Arrow; when the table does not exist, raise a clear error). Skip stocks already in state (`state.mark_stocks`). For each stock call `ctx.finmind.dataset("TaiwanStockMonthRevenue", start, end, data_id=stock_id)` once for the whole range, then write rows and `state.mark_stocks(..., [stock_id])` and `ctx.cache.flush()` per stock. Row mapping (FinMind columns `date, stock_id, country, revenue, revenue_month, revenue_year, create_time`):
*   `event_date = date(revenue_year, revenue_month, 1)` (the source `date` is the first day of the following month: the fixture row dated `2025-01-01` has `revenue_month = 12`, `revenue_year = 2024` and its `event_date` is `2024-12-01`);
*   columns `stock_id`, `country`, `revenue_year`, `revenue_month` (BIGINT, source names), `revenue` (BIGINT, the source unit, confirmed by spike S5 below), `create_time` (None when the source value is an empty string);
*   `available_at = avail_revenue(event_date, ctx.calendar)` (the 10th of the following month at 18:00 or the next trading day; null when past the calendar end);
*   `fetched_at` = the time the call returned (UTC).
A response with no rows for a stock (ETFs, new listings) writes nothing and the stock is marked done. A row-cap breach or a column set that differs from the fixture's is `DriftError` (fail closed).

**Spike S5 (unit), as a function `check_unit(ctx, stock_id, month)`** compares the FinMind `revenue` for one stock-month with the official TWSE OpenAPI `/opendata/t187ap05_L` value (`ctx.twse.openapi`, units NT$ thousands) and returns the ratio; the Lead runs it live. The value `278163107000` for 2330 December 2024 suggests the FinMind unit is NT$ (ratio 1000 to the thousands feed).

## Tests (offline, `tests/agent_c/`)
The `event_date` mapping (the March row dated 04-01 gets `event_date` 03-01, December rows cross the year), `available_at` for a Saturday and a Tuesday 10th and a month past the calendar end, an empty `create_time`, a rerun writes nothing, an empty response, the drift cases, state resume after a stock failure.
