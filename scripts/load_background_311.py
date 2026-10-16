"""Load the real NYC 311 (Hurricane Ida, Queens, 2021) rows from the frozen scenario into SurrealDB.

    python scripts/load_background_311.py [--db ws://...]   # uses SURREAL_* from .env

Read-only background context: no households, no contact fields. Idempotent (record id = 311 key).
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from db.remote import open_db, surreal_env

SOURCE = Path(__file__).resolve().parents[1] / "data/scenarios/s1/events.jsonl"
TABLE = "relay_background_311"


def rows():
    for line in SOURCE.read_text().splitlines():
        e = json.loads(line)
        if e.get("origin") != "real" or not e.get("real_311_key"):
            continue
        zip_ = re.search(r"\b(1[01]\d{3})\b", e["text"])
        yield {
            "key": str(e["real_311_key"]),
            "reported_at": e["ts_real"],
            "agency": (e.get("channel_meta") or {}).get("author"),
            "text": e["text"],
            "street": e.get("address_raw"),
            "zip": zip_.group(1) if zip_ else None,
            "lat": (e.get("geo") or {}).get("lat"),
            "lng": (e.get("geo") or {}).get("lng"),
        }


def main() -> int:
    env = surreal_env()
    url = env.get("SURREAL_URL", "").strip()
    if not url:
        print("SURREAL_URL is blank: embedded stores are single-process; start a server and set SURREAL_URL")
        return 1
    db = open_db(url, env.get("SURREAL_NAMESPACE") or "relay", env.get("SURREAL_DATABASE") or "relay",
                 env.get("SURREAL_USERNAME") or None, env.get("SURREAL_PASSWORD") or None, remote=True)
    db.query(f"DEFINE TABLE IF NOT EXISTS {TABLE} SCHEMALESS; DEFINE INDEX IF NOT EXISTS {TABLE}_key ON {TABLE} FIELDS key UNIQUE;")
    data = list(rows())
    for i in range(0, len(data), 200):
        db.query(f"FOR $r IN $rows {{ UPSERT type::record('{TABLE}', $r.key) CONTENT $r; }};", {"rows": data[i:i + 200]})
    count = db.query(f"SELECT count() FROM {TABLE} GROUP ALL")
    print(f"loaded {len(data)} real 311 rows; table now holds {count[0]['count'] if count else 0}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
