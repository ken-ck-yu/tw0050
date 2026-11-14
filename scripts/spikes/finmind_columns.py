"""Spike S12 helper: list the columns, types and key behaviour of each FinMind dataset.

Reads FINMIND_TOKEN from the environment, never prints it or any header. Prints only
dataset names, column names, python type names, row counts and distinct-value counts.
About 24 requests, 6 seconds apart. Stops on the first non-200 response.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

TOKEN = os.environ.get("FINMIND_TOKEN", "")
if not TOKEN:
    sys.exit("FINMIND_TOKEN not set. Nothing sent.")
HEAD = {"Authorization": f"Bearer {TOKEN}", "User-Agent": "research-probe"}
URL = "https://api.finmindtrade.com/api/v4/data"
JOBS = [
    ("TaiwanStockPrice", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockMonthRevenue", "2330", "2025-01-01", "2025-06-30"),
    ("TaiwanStockFinancialStatements", "2330", "2025-01-01", "2025-06-30"),
    ("TaiwanStockBalanceSheet", "2330", "2025-01-01", "2025-06-30"),
    ("TaiwanStockCashFlowsStatement", "2330", "2025-01-01", "2025-06-30"),
    ("TaiwanStockInstitutionalInvestorsBuySell", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockShareholding", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockMarginPurchaseShortSale", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockSecuritiesLending", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanDailyShortSaleBalances", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockDayTrading", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockPER", "2330", "2025-06-02", "2025-06-06"),
    ("TaiwanStockDividend", "2330", "2024-01-01", "2025-12-31"),
    ("TaiwanStockDividendResult", "2330", "2024-01-01", "2025-12-31"),
    ("TaiwanStockInfo", None, None, None),
    ("TaiwanStockDelisting", None, "2018-01-01", "2019-12-31"),
    ("TaiwanStockTradingDate", None, "2025-06-01", "2025-06-10"),
    ("USStockPrice", "AAPL", "2025-06-02", "2025-06-06"),
    ("TaiwanExchangeRate", "USD", "2025-06-02", "2025-06-06"),
    ("InterestRate", "FED", "2025-01-01", "2025-12-31"),
    ("GovernmentBondsYield", "United States 10-Year", "2025-06-02", "2025-06-06"),
    ("TaiwanFuturesDaily", "TX", "2025-06-02", "2025-06-03"),
    ("TaiwanFuturesInstitutionalInvestors", "TX", "2025-06-02", "2025-06-06"),
    ("TaiwanStockTotalReturnIndex", "TAIEX", "2025-06-02", "2025-06-06"),
]
for name, data_id, start, end in JOBS:
    p = {"dataset": name}
    if data_id:
        p["data_id"] = data_id
    if start:
        p["start_date"] = start
    if end:
        p["end_date"] = end
    req = urllib.request.Request(URL + "?" + urllib.parse.urlencode(p), headers=HEAD)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"STOP: HTTP {e.code} on {name}")
    except Exception as e:
        sys.exit(f"STOP: {type(e).__name__} on {name}")
    time.sleep(6)
    if body.get("status") not in (None, 200):
        sys.exit(f"STOP: status {body.get('status')} on {name}: {str(body.get('msg'))[:60]}")
    rows = body.get("data") or []
    print(f"== {name} rows={len(rows)}")
    if not rows:
        continue
    cols = list(rows[0].keys())
    print("  columns:", ", ".join(f"{c}:{type(rows[0][c]).__name__}" for c in cols))
    distinct = {c: len({json.dumps(r.get(c), sort_keys=True) for r in rows}) for c in cols}
    print("  distinct per column:", distinct)
    # smallest single or pair keys that make rows unique in the sample
    keys = []
    for c in cols:
        if distinct[c] == len(rows):
            keys.append((c,))
    if not keys:
        for i, a in enumerate(cols):
            for b in cols[i + 1 :]:
                if len({(json.dumps(r.get(a)), json.dumps(r.get(b))) for r in rows}) == len(rows):
                    keys.append((a, b))
    print("  unique in sample by:", keys[:4])
print("DONE")
