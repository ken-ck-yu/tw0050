# Agent A-1 data dictionary: official daily files, shares issued, market cap, snapshots

Code: `src/twdata/ingest/{daily_official,market_cap,snapshots,trading_calendar_derived}.py`.
Timestamps are stored as UTC; rules are computed in Asia/Taipei. History collected in 2026 is not
first-reported before 2026 (the `fetched_at` column says when each row was actually fetched).

## prices_raw (joinable, source_error, default view `as_latest_corrected`)
Key `market, stock_id, event_date`. One row per stock per trading day for every row the endpoints
list (ETFs, receipts and special classes included; classification is the universe step's job).

| Column | Type | Source |
|---|---|---|
| `market` | VARCHAR | `TWSE` or `TPEx` |
| `stock_id`, `stock_name` | VARCHAR | TWSE `證券代號`, `證券名稱`; TPEx `代號`, `名稱`. Name via `clean_name` (trim, one trailing `*` removed) |
| `open, high, low, close` | DOUBLE? | TWSE `開盤價/最高價/最低價/收盤價`; TPEx `開盤/最高/最低/收盤`. NTD per share, raw (unadjusted). Null for `--` (TWSE) or `----` (TPEx) |
| `volume_shares` | BIGINT | `成交股數`, shares |
| `turnover_ntd` | BIGINT | TWSE `成交金額`, TPEx `成交金額(元)`, NTD |
| `trades` | BIGINT | `成交筆數` |
| `event_date` | DATE | the trading day |
| `available_at` | TIMESTAMPTZ | 18:00 Taipei on `event_date` |
| `fetched_at` | TIMESTAMPTZ | raw response time |

Sources: TWSE `afterTrading/MI_INDEX` (table titled 每日收盤行情, `type=ALLBUT0999`), TPEx
`afterTrading/otc` (`type=EW`). Field lists are checked against three TPEx eras (15 fields to
2020-04-29, 17 fields with `(千股)` to 2025-01-09, 17 fields with `(張數)` from 2025-01-10) and one
TWSE era; anything else is `drift`. Eras are registered by `daily_official.ensure_eras()` when
`schema.py` has none.
Caveats: a no-trade row (all four prices null) has zero volume, turnover and trades unless the
source shows a trade (a few TWSE rows have `--` prices with a non-zero volume; those values are
kept). The TPEx change cell (`漲跌`, including ex-dates `除息`) is not stored. TWSE and TPEx do not
adjust for dividends or splits here. `sanity.check_price_row` runs on every row. A day where both
markets return no rows although the calendar says trading is recorded in
`data/state/calendar_discrepancy.jsonl`, treated as non-trading and marked done; nothing is written.

## shares_issued (joinable, source_error)
Key `market, stock_id, event_date`. `isin` VARCHAR? (TWSE `國際證券編碼`, null for TPEx),
`shares_issued` BIGINT (TWSE `MI_QFIIS` `發行股數`, TPEx `otc` `發行股數`), shares.
`available_at` 18:00 Taipei on `event_date`. Caveats: `MI_QFIIS` (`ALLBUT0999`) does not list every
stock in `MI_INDEX`; a stock with no shares row has no market cap that day. A row whose share
count is empty is skipped. TPEx counts come from the same file as the prices.

## market_cap (derived, none, default view latest-corrected)
Key `stock_id, event_date`. `close` DOUBLE, `shares_issued` BIGINT, `market_cap_ntd` DOUBLE =
`close * shares_issued` (NTD, raw close). Built from `default_prices_raw` joined to
`default_shares_issued` on market, stock_id and event_date, where close is not null. No
carry-forward. `available_at` = later of the two inputs' `available_at`; `fetched_at` = build time.
Rebuilding is idempotent (identical rows skipped); a corrected input writes a new row. A stock id on
two markets on one date raises `KeyUniquenessError`.

## View listing_status
`market, stock_id, first_date, last_date`: first and last `event_date` in `default_prices_raw`.
Gaps in listing are not visible in it (it is a bound, not a list of days).

## snapshot_<name> (15 tables, joinable, source_error)
Names: `twse_TWT85U, twse_TWT96U, twse_BFI84U, twse_TWTB4U, twse_t187ap04_L, twse_t187ap09_L,
twse_t187ap12_L, twse_t187ap24_L, twse_t187ap25_L, twse_t187ap26_L, twse_t187ap27_L,
tpex_spendi_today, tpex_spendi_history, tpex_trading_warning_information,
tpex_trading_warning_note` (OpenAPI paths in `snapshots.SNAPSHOTS`). Key `payload_sha256,
snapshot_date, row_seq`. Columns: `snapshot_date` DATE (Taipei date of the fetch, not the date in
the body: deliberate), `first_seen_at` TIMESTAMPTZ (= fetch time), `payload_sha256` (of the
response bytes), `row_seq` BIGINT (0-based position in the payload), `row_json` VARCHAR (the row,
`ensure_ascii=False, sort_keys=True`), `event_date` = `snapshot_date`, `available_at` =
`first_seen_at`. A payload that is not a JSON list of objects raises `DriftError` and writes
nothing; an empty list writes nothing and is recorded in state `snapshot_<name>`.
Stopgap import: files from `scripts/snapshot_capture.py` (`data/raw/snapshots/manifest.jsonl`)
are imported with the file stamp (Taipei time) as `fetched_at`; their sha256 is checked against the
manifest; imported files are listed in state `snapshots_stopgap`. Caveat: a latest-only source
missed on a day cannot be recovered; first_seen_at is a late bound on publication, not the true
publication time. The same payload fetched twice on one day gives one set of rows.

## calendar_diff (state file, not a table)
`data/state/calendar_diff.json`, written by `trading_calendar_derived.diff(ctx, start, end)`:
`finmind_only` (calendar trading days with no `prices_raw` row) and `derived_only` (dates with
prices that the calendar lacks), ISO date strings. The file also carries the state-document keys
(`dataset`, `key_type="diff"`, `completed=[]`) so that `status` can list it.
