#!/usr/bin/env python3
"""Re-check that every name in config/fictional_streets.json is absent from NYC's street data.

    python data/verify_fictional_streets.py     # network; exits 1 if any name matches a real street

Checks the name without its suffix ("HOLLOW OAK") citywide against NYC Street Centerline (CSCL, inkn-q76z)
and every 311 service request since 2010 (erm2-nwe9).
"""
import json
import sys
import urllib.parse
import urllib.request
from pathlib import Path

CONFIG = Path(__file__).parent / "config" / "fictional_streets.json"
SOURCES = {
    "cscl": ("https://data.cityofnewyork.us/resource/inkn-q76z.json", ("full_street_name", "stname_label", "street_name")),
    "nyc311": ("https://data.cityofnewyork.us/resource/erm2-nwe9.json", ("street_name", "incident_address")),
}
SUFFIXES = ("Lane", "Street", "Avenue", "Road", "Court", "Place", "Way", "Row", "Terrace")


def core(name):
    words = name.split()
    return " ".join(words[:-1] if words[-1] in SUFFIXES else words).upper()


def hits(url, columns, text):
    where = " OR ".join(f"upper({c}) like '%{text}%'" for c in columns)
    query = urllib.parse.urlencode({"$select": "count(*) as n", "$where": where})
    with urllib.request.urlopen(f"{url}?{query}", timeout=120) as r:
        return int(json.load(r)[0]["n"])


def main():
    bad = 0
    for name in json.loads(CONFIG.read_text())["names"]:
        counts = {k: hits(url, cols, core(name).replace("'", "''")) for k, (url, cols) in SOURCES.items()}
        bad += any(counts.values())
        print(f"{'REAL' if any(counts.values()) else 'ok  '}  {name:<24} {counts}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
