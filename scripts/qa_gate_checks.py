"""Read-only early-lane gate checks over data/clean (M1 tables + monthly_revenue).

Usage: python -I scripts/qa_gate_checks.py DATA_DIR [DEV_END]
Prints one line per check: PASS / FAIL / NOTE with numbers. Reads Parquet only: no network,
no token, no writes. The QA agent must read this script and judge whether each check matches
the plan and the acceptance checks; it is a convenience, not the definition of the gate."""

import sys
from pathlib import Path

import duckdb

DATA = Path(sys.argv[1])
DEV_END = sys.argv[2] if len(sys.argv) > 2 else "2025-12-31"
con = duckdb.connect()


def src(table: str) -> str:
    return f"read_parquet('{DATA}/clean/{table}/v1/*/*.parquet', union_by_name=true)"


def one(sql: str):
    return con.execute(sql).fetchall()


def say(status: str, name: str, detail: str) -> None:
    print(f"{status:5} {name}: {detail}")


# 1. key uniqueness
KEYS = {
    "trading_calendar": "event_date",
    "prices_raw": "stock_id, event_date",
    "shares_issued": "stock_id, event_date",
    "market_cap": "stock_id, event_date",
    "universe_membership": "stock_id, month_end",
    "delistings": "stock_id, event_date",
    "monthly_revenue": "stock_id, event_date",
    "stock_info": "stock_id, event_date, industry_category",
}
for t, k in KEYS.items():
    try:
        n = one(f"select count(*) from (select {k} from {src(t)} group by {k} having count(*)>1)")[0][0]
        say("PASS" if n == 0 else "FAIL", f"unique key {t} ({k})", f"{n} duplicate keys")
    except Exception as e:  # report, keep going
        say("NOTE", f"unique key {t}", f"could not run: {str(e)[:120]}")

# 2. available_at not before event_date (Asia/Taipei)
for t in ["prices_raw", "shares_issued", "market_cap", "status_events", "monthly_revenue"]:
    try:
        r = one(
            f"select count(*) filter (where available_at < cast(event_date as timestamp)),"
            f" count(*) filter (where available_at is null) from {src(t)}"
        )[0]
        say("PASS" if r == (0, 0) else "FAIL", f"available_at {t}", f"before_event={r[0]} null={r[1]}")
    except Exception as e:
        say("NOTE", f"available_at {t}", f"could not run: {str(e)[:120]}")

# 3. end dates against the dev window
for t, c in [
    ("prices_raw", "event_date"),
    ("shares_issued", "event_date"),
    ("market_cap", "event_date"),
    ("status_events", "event_date"),
    ("universe_membership", "month_end"),
    ("monthly_revenue", "event_date"),
]:
    try:
        mx = one(f"select max({c}) from {src(t)}")[0][0]
        say("NOTE", f"end date {t}", f"{mx} (dev_end {DEV_END}; revenue ends one month earlier by design)")
    except Exception as e:
        say("NOTE", f"end date {t}", f"could not run: {str(e)[:120]}")

# 4. universe: 200 ranked non-benchmark per month-end, 2330 present
r = one(
    "select count(*), min(n), max(n), min(has) from (select month_end,"
    " count(*) filter (where stock_id<>'0050') n, max((stock_id='2330')::int) has"
    f" from {src('universe_membership')} group by 1)"
)[0]
say("PASS" if r[1] == r[2] == 200 and r[3] == 1 else "FAIL", "universe 200 + 2330", f"month_ends={r[0]} min={r[1]} max={r[2]} has2330={r[3]}")

# 5. price coverage per member-month (all calendar trading days in the month up to month-end)
cov = one(
    f"""
with cal as (select event_date d from {src('trading_calendar')} where is_trading),
mm as (select distinct stock_id, month_end from {src('universe_membership')} where stock_id<>'0050'),
days as (select m.stock_id, m.month_end, count(*) n_cal
         from mm m join cal c on date_trunc('month', c.d) = date_trunc('month', m.month_end) and c.d <= m.month_end
         group by 1,2),
have as (select stock_id, date_trunc('month', event_date) mo, count(distinct event_date) n_px
         from {src('prices_raw')} group by 1,2)
select d.stock_id, d.month_end, d.n_cal, coalesce(h.n_px,0) n_px
from days d left join have h on h.stock_id=d.stock_id and h.mo=date_trunc('month', d.month_end)
where coalesce(h.n_px,0) < 0.99*d.n_cal order by n_px*1.0/n_cal"""
)
total = one(f"select count(*) from (select distinct stock_id, month_end from {src('universe_membership')} where stock_id<>'0050')")[0][0]
say("PASS" if not cov else "FAIL", "price coverage >=99%", f"{len(cov)} of {total} member-months below")
for row in cov:
    print("      below99", row)

# 6. delisted names present and with prices
r = one(
    f"select count(*), count(*) filter (where stock_id in (select stock_id from {src('prices_raw')})) from {src('delistings')}"
)[0]
say("NOTE", "delistings with prices", f"{r[1]} of {r[0]} delistings have price rows")

# 7. collection set completeness
for t in ["prices_raw", "shares_issued", "market_cap", "monthly_revenue"]:
    n = one(
        f"select count(*) from {src('collection_set')} where stock_id<>'0050' and stock_id not in (select stock_id from {src(t)})"
    )[0][0]
    say("NOTE", f"collection_set missing from {t}", f"{n} stocks")

# 8. revenue: interior gaps and non-positive values
for row in one(
    f"""with b as (select stock_id, min(event_date) a, max(event_date) z, count(distinct event_date) n
from {src('monthly_revenue')} group by 1)
select stock_id, a, z, n, (date_diff('month', a, z)+1)-n missing from b
where (date_diff('month', a, z)+1)-n > 0 order by missing desc"""
):
    print("      revenue_gap", row)
nonpos = one(f"select count(*) from {src('monthly_revenue')} where revenue <= 0")[0][0]
say("NOTE", "revenue <= 0", f"{nonpos} rows")
r = one(f"select min(revenue), max(revenue) from {src('monthly_revenue')} where stock_id='2330' and event_date='2024-04-01'")[0]
say("NOTE", "revenue unit 2330 2024-04", f"{r} (TSMC published 236.02B NT$)")

# 9. market_cap = close x shares_issued
try:
    n = one(
        f"""select count(*) from {src('market_cap')} m join {src('prices_raw')} p using (stock_id, event_date)
join {src('shares_issued')} s using (stock_id, event_date)
where abs(m.market_cap_ntd - p.close * s.shares_issued) > 1"""
    )[0][0]
    say("PASS" if n == 0 else "FAIL", "market_cap = close x shares", f"{n} rows differ by more than 1")
except Exception as e:
    say("NOTE", "market_cap = close x shares", f"could not run: {str(e)[:160]}")
