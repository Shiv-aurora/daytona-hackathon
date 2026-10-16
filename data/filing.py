"""File households from visible scenario data only: a check that W1/W2's "file a household from its first report"
path has enough to work with.

Walks the events in (ts, _id) order through W2's merged matcher, with the visible registry seeded first. An event
whose hints resolve to nobody and that names a person at a dwelling address files a new household from exactly those
hints. Hidden truth is never read here; callers compare the result with it afterwards. The real write path belongs to
W1/W2; this only proves the committed data makes it possible.
"""
from __future__ import annotations

from db.scope import RunScope
from db.testing import open_test_database
from memory.households import match_household, seed_household

RUN_ID = "w5-filing-check"


def visible_hint(event: dict) -> dict[str, str]:
    """The identity hint a runtime sees: household_ref_raw and a dwelling-level address_raw (not a block range)."""
    address = event.get("address_raw")
    if address and " to " in address:
        address = None
    return {k: v for k, v in (("name", event.get("household_ref_raw")), ("address", address)) if v}


def file_households(events: list[dict], registry: list[dict]) -> tuple[dict[str, str], dict[str, str]]:
    """-> (event_id -> household it resolves to, filed household -> the event that filed it)."""
    resolved: dict[str, str] = {}
    filed: dict[str, str] = {}
    with open_test_database() as db:
        scope = RunScope(db, RUN_ID)
        for entry in registry:
            seed_household(scope, entry["household_id"], name=entry["name"], address=entry["address"])
        for event in sorted(events, key=lambda e: (e["ts"], e["_id"])):
            hint = visible_hint(event)
            if not hint:
                continue
            household = match_household(scope, hint)
            if household is None and {"name", "address"} <= set(hint):
                household = f"filed:{event['_id']}"
                seed_household(scope, household, **hint)
                filed[household] = event["_id"]
            if household is not None:
                resolved[event["_id"]] = household
    return resolved, filed
