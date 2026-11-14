# Data dictionary (agent C): `monthly_revenue`

Source: FinMind `TaiwanStockMonthRevenue`, one request per stock for the whole range (`data_id` = stock). Module: `src/twdata/ingest/monthly_revenue.py`, dataset name `monthly_revenue`. Clean table `data/clean/monthly_revenue/`, class `joinable`, restatement `economic` (default view is `as_first_seen`). Key: `stock_id, event_date`. Partition: year of `event_date`.

| Column | Type | Meaning |
|---|---|---|
| `event_date` | DATE | First day of the revenue month, `date(revenue_year, revenue_month, 1)`. Not the source `date`. |
| `available_at` | TIMESTAMPTZ? (UTC) | Rule below. Null when the 10th of the following month is past the calendar end (pending; a later run fills it). |
| `fetched_at` | TIMESTAMPTZ (UTC) | Time the FinMind call returned. |
| `stock_id` | VARCHAR | Source `stock_id`. |
| `country` | VARCHAR | Source `country` (observed `Taiwan`). |
| `revenue_year` | BIGINT | Source `revenue_year`. |
| `revenue_month` | BIGINT | Source `revenue_month` (1 to 12). The section 7 name `revenue_month_num` was not used; `schema.py` uses `revenue_month`. |
| `revenue` | BIGINT | Source `revenue`, stored unchanged. Unit is NT$ (not thousands) per the 2330 December 2024 value 278,163,107,000; confirmed live by spike S5 (`check_unit`, expected ratio 1000 against `t187ap05_L`, which is in NT$ thousands). Until the Lead runs S5 the unit is a strong inference, not a verified fact. |
| `create_time` | VARCHAR? | Source `create_time`; null when the source value is an empty string (every row in the fixture). |

## `event_date` and `available_at`

The FinMind `date` is the first day of the following month (a row dated 2025-04-01 has `revenue_month = 3`), so `event_date` is rebuilt from `revenue_year` and `revenue_month` (row dated 2025-04-01 gives `event_date` 2025-03-01; December rows cross the year: `date` 2025-01-01 gives 2024-12-01).

`available_at = avail_revenue(event_date, calendar)`: the 10th of the following month at 18:00 Taipei if that day is a trading day, otherwise the next trading day at 18:00. This is the statutory filing deadline, not an observed publication time. Companies often file earlier, so this is conservative (late), never early. Null when that date is past the calendar end.

## Caveats

*   Revenue can be restated (amended filings). The writer stores a changed value as a new row; `as_first_seen` is the default and keeps the first value; `revisions_monthly_revenue` and `as_latest_corrected` give the later value with `available_at = max(available_at, fetched_at)`.
*   FinMind does not date its history: a first fetch of old months records `fetched_at` of today, while `available_at` is the statutory date. The `as_first_seen` value therefore may already include a restatement made before the first fetch.
*   Stocks with no rows (ETFs such as 0050, new listings) write nothing and are marked done in state (`data/state/monthly_revenue.json`, `key_type` stock), so they are not requested again on a rerun.
*   The stock list is the distinct `stock_id` of the clean table `collection_set` (via `default_collection_set`). The module fails with `MissingCollectionSet` if that table or the trading calendar is missing.
*   The source `date` is not checked against `revenue_year`/`revenue_month`; a mismatch is not flagged.
*   Fail closed (`DriftError`): a row whose column set differs from `date, stock_id, country, revenue, revenue_month, revenue_year, create_time`, a non-integer `revenue`, `revenue_year` or `revenue_month`, `revenue_month` outside 1 to 12, or a response above the row cap (`row_caps.datasets` or `finmind_default`).
*   Resume: state is marked per stock after its rows are written; a failure at one stock leaves earlier stocks done. A stock is NOT marked done when any of its rows has a null `available_at` (a month whose deadline is past the calendar end), so a later run, after the calendar is extended, refetches it and the writer fills the pending value.
*   Refresh: dataset `monthly_revenue_refresh` (`refresh_recent(ctx, months=3)`) re-fetches the last 3 calendar months for every stock in `collection_set`, ignoring state. Identical rows are skipped, new months are appended, restated values become new rows, pending `available_at` is filled. Through the CLI the window ends at `--end` (`--start` is ignored); the FinMind start date is the first day of the month 3 months before the end month.
*   The column-set drift check compares the keys of every row to the seven source columns.
