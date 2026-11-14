"""Capture the full column lists of TaiwanStockDividend and TaiwanDailyShortSaleBalances.

Reads FINMIND_TOKEN from the environment, never prints it. Prints column names and types only.
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
    sys.exit("FINMIND_TOKEN not set")
for name, data_id, start, end in [
    ("TaiwanStockDividend", "2330", "2024-01-01", "2025-12-31"),
    ("TaiwanDailyShortSaleBalances", "2330", "2025-06-02", "2025-06-06"),
]:
    p = {"dataset": name, "data_id": data_id, "start_date": start, "end_date": end}
    req = urllib.request.Request(
        "https://api.finmindtrade.com/api/v4/data?" + urllib.parse.urlencode(p),
        headers={"Authorization": f"Bearer {TOKEN}", "User-Agent": "research-probe"},
    )
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            body = json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"STOP HTTP {e.code}")
    rows = body.get("data") or []
    print(name, "rows", len(rows))
    for k, v in rows[0].items():
        print(
            "  ",
            k,
            type(v).__name__,
            "| sample:",
            repr(v)[:40] if k in ("AnnouncementDate", "AnnouncementTime", "date", "year") else "",
        )
    time.sleep(6)
