"""Address normalization + the real-address blocklist.

Synthetic households must never sit at an address that appears in real 311 data:
it keeps real people out of the simulation and keeps identity matching honest
(a real 311 row must not fuzzy-join to a made-up household).
"""
import json
import re
from functools import lru_cache
from pathlib import Path

BLOCKLIST_JSON = Path(__file__).parent / "derived" / "address_blocklist.json"

SUFFIXES = {
    "AVENUE": "AVE", "AV": "AVE", "STREET": "ST", "ROAD": "RD", "PLACE": "PL",
    "BOULEVARD": "BLVD", "DRIVE": "DR", "LANE": "LN", "PARKWAY": "PKWY", "COURT": "CT",
    "TERRACE": "TER", "EXPRESSWAY": "EXPY", "HIGHWAY": "HWY", "TURNPIKE": "TPKE",
    "CRESCENT": "CRES", "NORTH": "N", "SOUTH": "S", "EAST": "E", "WEST": "W",
}


def normalize_address(address: str) -> str:
    """'41-22 41st Avenue' and '41-22 41 AVE' both -> '41-22 41 AVE'."""
    s = re.sub(r"[.,#]", " ", address.upper())
    s = re.sub(r"\b(\d+)(ST|ND|RD|TH)\b", r"\1", s)
    return " ".join(SUFFIXES.get(t, t) for t in s.split())


def normalize_street(street: str) -> str:
    return normalize_address(street)


@lru_cache(maxsize=1)
def _blocked() -> frozenset:
    return frozenset(json.loads(BLOCKLIST_JSON.read_text())["addresses"])


def is_real_address(address: str) -> bool:
    """True if this address (any ZIP) appears in real 311 data for the scenario ZIPs."""
    return normalize_address(address) in _blocked()
