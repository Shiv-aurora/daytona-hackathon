#!/usr/bin/env python3
"""Pull NYC 311 service requests for Scenario 1 (Queens, Hurricane Ida recovery).

    python data/pull_311.py types     # 1a: complaint-type counts + flood ZIP ranking (prints only)
    python data/pull_311.py extract   # 1b: rows for chosen ZIPs/types + every real address in those ZIPs

Source: NYC Open Data "311 Service Requests from 2010 to Present" (erm2-nwe9).
Set NYC_OPEN_DATA_APP_TOKEN to avoid throttling (optional).
"""
import csv
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

API = "https://data.cityofnewyork.us/resource/erm2-nwe9.json"
START, END = "2021-09-01T00:00:00", "2021-10-13T23:59:59"  # days 0-42
IDA_START, IDA_END = "2021-09-01T18:00:00", "2021-09-04T23:59:59"
PAGE = 50_000

HERE = Path(__file__).parent
RAW = HERE / "raw"
ROWS_CSV = RAW / "311_queens_ida.csv"
ADDRESSES_CSV = RAW / "311_queens_addresses.csv"
CONFIG = HERE / "config" / "complaint_types.json"

# Spec ZIPs (Flushing, Corona, Jackson Heights, Elmhurst, Woodside) plus the top Ida flood ZIPs from 1a
# (Sewer/Storm/Water System/WATER LEAK, Sep 1 18:00 - Sep 4): East Elmhurst, Forest Hills, Flushing N, Jamaica.
ZIPS = ["11354", "11355", "11368", "11372", "11373", "11377",
        "11369", "11370", "11375", "11358", "11432"]

# Recovery-relevant complaint types (picked from 1a), grouped by category in config/complaint_types.json.
CATEGORIES = json.loads(CONFIG.read_text())["categories"]
COMPLAINT_TYPES = [t for types in CATEGORIES.values() for t in types]

FIELDS = [
    "unique_key", "created_date", "closed_date", "agency", "complaint_type", "descriptor",
    "location_type", "incident_zip", "street_name", "incident_address", "status",
    "resolution_description", "borough", "latitude", "longitude", "bbl", "city",
]


def quoted(values):
    return ", ".join("'" + v.replace("'", "''") + "'" for v in values)


def query(params, retries=4):
    url = API + "?" + urllib.parse.urlencode(params)
    headers = {"Accept": "application/json"}
    if token := os.environ.get("NYC_OPEN_DATA_APP_TOKEN"):
        headers["X-App-Token"] = token
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=120) as r:
                return json.load(r)
        except Exception as e:  # network / throttling: back off and retry
            if attempt == retries - 1:
                raise
            print(f"  retry {attempt + 1} after error: {e}", file=sys.stderr)
            time.sleep(2 ** attempt)


def paged(params, order):
    offset = 0
    while True:
        rows = query({**params, "$order": order, "$limit": PAGE, "$offset": offset})
        yield from rows
        print(f"  fetched {offset + len(rows)} rows", file=sys.stderr)
        if len(rows) < PAGE:
            return
        offset += PAGE


def cmd_types():
    window = f"created_date between '{START}' and '{END}' AND borough='QUEENS'"
    print(f"== 1a: Queens complaint types, {START[:10]} .. {END[:10]}")
    for r in query({"$select": "complaint_type, count(*) as n", "$where": window,
                    "$group": "complaint_type", "$order": "n DESC", "$limit": 500}):
        mark = "*" if r["complaint_type"] in COMPLAINT_TYPES else " "
        print(f"{mark} {int(r['n']):>7}  {r['complaint_type']}")

    flood = f"created_date between '{IDA_START}' and '{IDA_END}' AND borough='QUEENS' " \
            "AND complaint_type in ('Sewer','Storm','Water System','WATER LEAK')"
    print(f"\n== Queens ZIPs by Ida flood complaints ({IDA_START} .. {IDA_END})")
    for r in query({"$select": "incident_zip, min(city) as city, count(*) as n", "$where": flood,
                    "$group": "incident_zip", "$order": "n DESC", "$limit": 30}):
        mark = "*" if r.get("incident_zip") in ZIPS else " "
        print(f"{mark} {int(r['n']):>5}  {r.get('incident_zip')}  {r.get('city')}")


def cmd_extract():
    RAW.mkdir(parents=True, exist_ok=True)
    zips = f"incident_zip in ({quoted(ZIPS)})"
    window = f"created_date between '{START}' and '{END}'"

    print(f"== 1b: rows for {len(ZIPS)} ZIPs x {len(COMPLAINT_TYPES)} complaint types -> {ROWS_CSV}")
    params = {"$select": ", ".join(FIELDS),
              "$where": f"{window} AND {zips} AND complaint_type in ({quoted(COMPLAINT_TYPES)})"}
    n = 0
    with ROWS_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader()
        for row in paged(params, order="unique_key"):
            w.writerow(row)
            n += 1
    print(f"  wrote {n} rows")

    # Every real address in these ZIPs (all complaint types) feeds the synthetic-household blocklist.
    print(f"== real addresses in {len(ZIPS)} ZIPs (all complaint types) -> {ADDRESSES_CSV}")
    params = {"$select": "incident_zip, incident_address, count(*) as n",
              "$where": f"{window} AND {zips} AND incident_address IS NOT NULL",
              "$group": "incident_zip, incident_address"}
    n = 0
    with ADDRESSES_CSV.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["incident_zip", "incident_address", "n"])
        w.writeheader()
        for row in paged(params, order="incident_zip, incident_address"):
            w.writerow(row)
            n += 1
    print(f"  wrote {n} addresses")


if __name__ == "__main__":
    commands = {"types": cmd_types, "extract": cmd_extract}
    if len(sys.argv) != 2 or sys.argv[1] not in commands:
        sys.exit(__doc__)
    commands[sys.argv[1]]()
