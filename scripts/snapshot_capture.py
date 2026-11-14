"""Temporary stopgap: capture latest-only TWSE and TPEx lists as raw, unparsed responses.

Authorised by the author on 2026-11-14 so that history is not lost while the real
snapshot job (src/twdata, built after design approval) does not exist. It is replaced
and migrated by that job. It is not part of the data platform design.

Run by hand once per trading day:  python3 -I scripts/snapshot_capture.py

Rules it follows: public endpoints only, no token, one request in flight, at least
5 seconds apart, stop after 3 consecutive failures, never overwrites a file.
Output: data/raw/snapshots/<name>/<YYYY-MM-DDTHHMMSS>.json (Asia/Taipei time) and one
line per file in data/raw/snapshots/manifest.jsonl with its sha256. data/ is gitignored.
"""

import datetime
import hashlib
import json
import os
import time
import urllib.request
import zoneinfo

TWSE = "https://openapi.twse.com.tw/v1"
TPEX = "https://www.tpex.org.tw/openapi/v1"
SOURCES = {
    "twse_TWT85U": f"{TWSE}/exchangeReport/TWT85U",
    "twse_TWT96U": f"{TWSE}/SBL/TWT96U",
    "twse_BFI84U": f"{TWSE}/exchangeReport/BFI84U",
    "twse_TWTB4U": f"{TWSE}/exchangeReport/TWTB4U",
    "twse_t187ap04_L": f"{TWSE}/opendata/t187ap04_L",
    "twse_t187ap09_L": f"{TWSE}/opendata/t187ap09_L",
    "twse_t187ap12_L": f"{TWSE}/opendata/t187ap12_L",
    "twse_t187ap24_L": f"{TWSE}/opendata/t187ap24_L",
    "twse_t187ap25_L": f"{TWSE}/opendata/t187ap25_L",
    "twse_t187ap26_L": f"{TWSE}/opendata/t187ap26_L",
    "twse_t187ap27_L": f"{TWSE}/opendata/t187ap27_L",
    "tpex_spendi_today": f"{TPEX}/tpex_spendi_today",
    "tpex_spendi_history": f"{TPEX}/tpex_spendi_history",
    "tpex_trading_warning_information": f"{TPEX}/tpex_trading_warning_information",
    "tpex_trading_warning_note": f"{TPEX}/tpex_trading_warning_note",
}
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "raw", "snapshots")
TZ = zoneinfo.ZoneInfo("Asia/Taipei")


def main():
    os.makedirs(ROOT, exist_ok=True)
    bad = 0
    saved = 0
    for name, url in SOURCES.items():
        stamp = datetime.datetime.now(TZ).strftime("%Y-%m-%dT%H%M%S")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 research-probe"})
            with urllib.request.urlopen(req, timeout=60) as r:
                body = r.read()
                status = r.status
            json.loads(body)  # must be JSON, otherwise it is an error page
            bad = 0
        except Exception as e:
            bad += 1
            print(f"FAIL {name}: {type(e).__name__}")
            if bad >= 3:
                print("STOP: 3 consecutive failures")
                break
            time.sleep(5)
            continue
        d = os.path.join(ROOT, name)
        os.makedirs(d, exist_ok=True)
        path = os.path.join(d, stamp + ".json")
        if os.path.exists(path):
            print(f"SKIP {name}: file exists")
        else:
            with open(path, "wb") as f:
                f.write(body)
            line = {
                "name": name,
                "file": os.path.relpath(path, ROOT),
                "fetched_at": stamp,
                "status": status,
                "bytes": len(body),
                "sha256": hashlib.sha256(body).hexdigest(),
            }
            with open(os.path.join(ROOT, "manifest.jsonl"), "a") as m:
                m.write(json.dumps(line) + "\n")
            saved += 1
            print(f"OK   {name}: {len(body)} bytes")
        time.sleep(5)
    print(f"saved {saved} of {len(SOURCES)}")


if __name__ == "__main__":
    main()
