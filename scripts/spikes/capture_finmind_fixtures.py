"""Capture trimmed FinMind responses as test fixtures (Lead, token from the environment).

Never prints or stores the token or any header. user_info keeps only four whitelisted fields.
Public market data rows only (at most 5 per dataset). Stops on the first non-200 response.
"""

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

TOKEN = os.environ.get("FINMIND_TOKEN", "")
if not TOKEN:
    sys.exit("FINMIND_TOKEN not set. Nothing sent.")
OUT = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "lead" / "finmind"
OUT.mkdir(parents=True, exist_ok=True)
HEAD = {"Authorization": f"Bearer {TOKEN}", "User-Agent": "research-probe"}
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


def get(url, params=None):
    if params:
        url += "?" + urllib.parse.urlencode(params)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEAD), timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"STOP: HTTP {e.code}")
    except Exception as e:
        sys.exit(f"STOP: {type(e).__name__}")
    finally:
        time.sleep(6)


info = get("https://api.web.finmindtrade.com/v2/user_info")
keep = {k: info[k] for k in ("level", "level_title", "user_count", "api_request_limit") if k in info}
(OUT / "user_info.json").write_text(json.dumps(keep, indent=1), encoding="utf-8")
print("user_info keys saved:", sorted(keep))
for name, data_id, start, end in JOBS:
    p = {"dataset": name}
    if data_id:
        p["data_id"] = data_id
    if start:
        p["start_date"] = start
    if end:
        p["end_date"] = end
    body = get("https://api.finmindtrade.com/api/v4/data", p)
    if body.get("status") not in (None, 200):
        sys.exit(f"STOP: status {body.get('status')} on {name}")
    rows = (body.get("data") or [])[:5]
    doc = {"msg": body.get("msg"), "status": body.get("status"), "data": rows}
    tag = f"{name}_{data_id}" if data_id else name
    (OUT / f"{tag.replace(' ', '_')}_trimmed.json").write_text(
        json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")
    print("saved", tag, len(rows))
print("DONE")
