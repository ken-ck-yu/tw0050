"""Build data/research/ for the early research lane (Lead). The sealed holdout stays out.

Writes one Parquet file per table the frozen evaluator reads, from the clean store's default
views, keeping only development-window rows (event_date <= research.dev_end; month_end for the
universe) and only stocks in the collection set plus 0050 for the price tables (memory).
`adjusted_prices` comes from Agent B's adjusted_series(as_of=None) joined to the raw open.

    .venv/bin/python scripts/make_research_data.py
"""

import shutil
import sys
from datetime import date

import duckdb
import pyarrow as pa
import pyarrow.parquet as pq

from twdata.common import views
from twdata.common.config import load_settings
from twdata.ingest.adjusted import adjusted_series


def main() -> int:
    s = load_settings()
    dev_end: date = s.research.dev_end
    out = s.data_dir / "research"
    if out.exists():
        shutil.rmtree(out)  # derived copy only; the clean store is untouched
    out.mkdir(parents=True)
    con = duckdb.connect()
    views.register_views(con, s)
    stocks = [
        r[0] for r in con.execute("SELECT DISTINCT stock_id FROM default_collection_set").fetchall()
    ]
    stocks = sorted(set(stocks) | {"0050"})
    con.register("keep_stocks", pa.table({"stock_id": stocks}))
    d = dev_end.isoformat()

    def dump(name: str, sql: str) -> int:
        tbl = con.execute(sql).arrow()
        pq.write_table(tbl, out / f"{name}.parquet")
        print(f"{name}: {tbl.num_rows} rows")
        return tbl.num_rows

    dump(
        "universe_membership",
        f"SELECT * FROM default_universe_membership WHERE month_end <= DATE '{d}'",
    )
    dump(
        "prices_raw",
        f"SELECT * FROM default_prices_raw WHERE event_date <= DATE '{d}' "
        "AND stock_id IN (SELECT stock_id FROM keep_stocks)",
    )
    dump(
        "price_limits",
        f"SELECT * FROM default_price_limits WHERE event_date <= DATE '{d}' "
        "AND stock_id IN (SELECT stock_id FROM keep_stocks)",
    )
    dump("status_events", f"SELECT * FROM default_status_events WHERE event_date <= DATE '{d}'")
    dump(
        "monthly_revenue",
        f"SELECT * FROM default_monthly_revenue WHERE event_date <= DATE '{d}' "
        "AND stock_id IN (SELECT stock_id FROM keep_stocks)",
    )
    dump("benchmark_index", f"SELECT * FROM default_benchmark_index WHERE event_date <= DATE '{d}'")
    dump(
        "trading_calendar", f"SELECT * FROM default_trading_calendar WHERE event_date <= DATE '{d}'"
    )
    adj = adjusted_series(con, as_of=None, stock_ids=stocks)
    con.register("adj", adj)
    dump(
        "adjusted_prices",
        "SELECT a.market, a.stock_id, a.event_date, p.open, a.close, a.adjusted_close "
        "FROM adj a JOIN default_prices_raw p USING (market, stock_id, event_date) "
        f"WHERE a.event_date <= DATE '{d}'",
    )
    n0050 = con.execute(
        "SELECT count(*) FROM read_parquet('%s') WHERE stock_id = '0050'"
        % (out / "adjusted_prices.parquet")
    ).fetchone()[0]
    if n0050 == 0:
        print("ERROR: 0050 missing from adjusted_prices (the evaluator needs the benchmark)")
        return 1
    print("research data written to", out, "dev_end", dev_end, "stocks", len(stocks))
    return 0


if __name__ == "__main__":
    sys.exit(main())
