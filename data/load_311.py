#!/usr/bin/env python3
"""Turn the raw 311 pull into Scenario 1 inputs (run after `pull_311.py extract`).

    python data/load_311.py

Real records are never edited: filtered and time-shifted only.
Time mapping: ts = (created_date - 2021-09-01T20:00) in days; keep 0 <= ts < 43 (days 0-42).

Writes to data/derived/:
  events_311.jsonl        real 311 opens/closes as events (ts + ts_real), spec event shape + helper fields
  street_intensity.json   per street: flood intensity, recovery load, daily counts by category; per-ZIP daily curves
  latencies.json          created->closed hours by complaint type / descriptor / agency; flood p50 by week
  address_blocklist.json  every real address in the scenario ZIPs (synthetic households must avoid these)
"""
import csv
import json
import math
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

from addresses import BLOCKLIST_JSON, normalize_address, normalize_street
from pull_311 import ADDRESSES_CSV, CATEGORIES, ROWS_CSV

DERIVED = Path(__file__).parent / "derived"
T0 = datetime(2021, 9, 1, 20, 0)  # noqa: DTZ001 - storm start, NY wall clock like the 311 timestamps
DAYS = 43                         # days 0-42
EARLY_DAYS = 3                    # days 0-3 = the flood itself
CATEGORY_OF = {t: c for c, types in CATEGORIES.items() for t in types}


def sim_day(ts: str) -> float | None:
    return (datetime.fromisoformat(ts) - T0).total_seconds() / 86400 if ts else None


def street_of(row) -> str:
    street = row["street_name"] or re.sub(r"^[\d\-]+[A-Z]?\s+", "", row["incident_address"] or "")
    return normalize_street(street) if street else ""


def pct(sorted_vals, p):
    return round(sorted_vals[min(len(sorted_vals) - 1, max(0, math.ceil(p / 100 * len(sorted_vals)) - 1))], 1)


def latency_stats(latencies, n_total):
    s = sorted(latencies)
    out = {"n": n_total, "closed": len(s), "open_frac": round(1 - len(s) / n_total, 3) if n_total else None}
    if s:
        out.update({f"p{p}_h": pct(s, p) for p in (10, 25, 50, 75, 90)})
    return out


def event(row, kind, ts):
    ctype, desc = row["complaint_type"], row["descriptor"]
    place = f"{row['incident_address'] or street_of(row)}, {(row['city'] or '').title()} {row['incident_zip']}"
    text = (f"311 {ctype}: {desc}. {place}." if kind == "open"
            else f"311 closed ({row['agency']}) {ctype}: {row['resolution_description']} {place}.")
    return {
        # spec event fields (event_id / scenario_id assigned by the generator)
        "tmp_id": f"311-{row['unique_key']}-{kind}",
        "ts": round(ts, 5),
        "ts_real": row["created_date"] if kind == "open" else row["closed_date"],
        "source": "311",
        "text": text,
        "address_raw": row["incident_address"] or None,
        "geo": {"lat": float(row["latitude"]), "lng": float(row["longitude"])} if row["latitude"] else None,
        "household_ref_raw": None,
        "channel_meta": {"author": "311" if kind == "open" else row["agency"], "language": "en"},
        "real_311_key": row["unique_key"],
        "origin": "real",
        # helper fields for the generator (stripped before writing scenario events)
        "_kind": kind, "_day": int(ts), "_zip": row["incident_zip"], "_street": street_of(row),
        "_address_norm": normalize_address(row["incident_address"]) if row["incident_address"] else None,
        "_category": CATEGORY_OF.get(ctype, "other"),
    }


def main():
    DERIVED.mkdir(exist_ok=True)
    rows = list(csv.DictReader(ROWS_CSV.open()))

    events = []
    streets = defaultdict(lambda: {"daily": [0] * DAYS, "by_category": Counter(), "addresses": set(),
                                   "flood_early": 0, "recovery_load": 0})
    zip_daily = defaultdict(lambda: defaultdict(lambda: [0] * DAYS))
    lat_by = {"complaint_type": defaultdict(list), "descriptor": defaultdict(list), "agency": defaultdict(list)}
    n_by = {k: Counter() for k in lat_by}
    flood_week = defaultdict(list)

    for row in rows:
        opened = sim_day(row["created_date"])
        if opened is None or not 0 <= opened < DAYS:
            continue
        day, cat = int(opened), CATEGORY_OF.get(row["complaint_type"], "other")
        events.append(event(row, "open", opened))

        closed = sim_day(row["closed_date"])
        latency_h = (closed - opened) * 24 if closed is not None and closed >= opened else None
        if latency_h is not None and closed < DAYS:
            events.append(event(row, "closed", closed))

        keys = {"complaint_type": row["complaint_type"],
                "descriptor": f"{row['complaint_type']} | {row['descriptor']}",
                "agency": row["agency"]}
        for dim, key in keys.items():
            n_by[dim][key] += 1
            if latency_h is not None:
                lat_by[dim][key].append(latency_h)
        if cat == "flood" and latency_h is not None:
            flood_week[day // 7].append(latency_h)

        zip_daily[row["incident_zip"]][cat][day] += 1
        if street := street_of(row):
            st = streets[(row["incident_zip"], street)]
            st["daily"][day] += 1
            st["by_category"][cat] += 1
            if row["incident_address"]:
                st["addresses"].add(normalize_address(row["incident_address"]))
            if cat == "flood" and day <= EARLY_DAYS:
                st["flood_early"] += 1
            elif day > EARLY_DAYS:
                st["recovery_load"] += 1

    events.sort(key=lambda e: (e["ts"], e["tmp_id"]))
    with (DERIVED / "events_311.jsonl").open("w") as f:
        for e in events:
            f.write(json.dumps(e) + "\n")

    max_flood = max((s["flood_early"] for s in streets.values()), default=0) or 1
    max_load = max((s["recovery_load"] for s in streets.values()), default=0) or 1
    street_list = sorted(
        ({"zip": z, "street": name,
          "flood_intensity": round(s["flood_early"] / max_flood, 3),
          "recovery_load": round(s["recovery_load"] / max_load, 3),
          "flood_early": s["flood_early"], "total": sum(s["daily"]),
          "distinct_addresses": len(s["addresses"]),
          "by_category": dict(s["by_category"]), "daily": s["daily"]}
         for (z, name), s in streets.items()),
        key=lambda s: (-s["flood_intensity"], -s["total"], s["zip"], s["street"]))
    (DERIVED / "street_intensity.json").write_text(json.dumps({
        "t0": T0.isoformat(), "days": DAYS, "early_days": EARLY_DAYS,
        "zip_daily": {z: dict(c) for z, c in sorted(zip_daily.items())},
        "streets": street_list,
    }, indent=1))

    min_n = 20
    (DERIVED / "latencies.json").write_text(json.dumps({
        "unit": "hours created->closed; open_frac = never closed in the data",
        **{dim: {k: latency_stats(lat_by[dim][k], n) for k, n in n_by[dim].most_common() if n >= min_n}
           for dim in lat_by},
        "flood_p50_by_week": {f"week_{w}": latency_stats(v, len(v)) for w, v in sorted(flood_week.items())},
    }, indent=1))

    blocked = sorted({normalize_address(r["incident_address"])
                      for r in csv.DictReader(ADDRESSES_CSV.open()) if r["incident_address"]}
                     | {e["_address_norm"] for e in events if e["_address_norm"]})
    BLOCKLIST_JSON.write_text(json.dumps({"count": len(blocked), "addresses": blocked}))

    per_day = Counter(e["_day"] for e in events if e["_kind"] == "open")
    print(f"events_311.jsonl: {len(events)} events ({sum(per_day.values())} opens), days "
          f"{min(per_day)}-{max(per_day)}")
    print("opens per day:", " ".join(f"{d}:{per_day[d]}" for d in range(DAYS)))
    print(f"street_intensity.json: {len(street_list)} streets; top 5:")
    for s in street_list[:5]:
        print(f"  {s['zip']} {s['street']:<28} flood_early={s['flood_early']:<4} total={s['total']}")
    print(f"latencies.json: {len(lat_by['complaint_type'])} complaint types")
    print(f"address_blocklist.json: {len(blocked)} real addresses")


if __name__ == "__main__":
    main()
