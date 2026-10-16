"""Household memory: identity for matching, and each event applied to its household exactly once."""

from __future__ import annotations

import difflib
import re
from collections.abc import Mapping

from db.bootstrap import EVENTS, HOUSEHOLDS
from db.events import checked_events, visible_query
from db.scope import RunScope, stable_id
from db.writes import emit

CONTACT_SOURCES = ("visit_note", "call_result")  # someone reached the resident; a 311 report isn't contact
STREET_TYPES = {"street": "st", "st": "st", "avenue": "ave", "ave": "ave", "av": "ave", "road": "rd", "rd": "rd",
                "place": "pl", "pl": "pl", "lane": "ln", "ln": "ln", "boulevard": "blvd", "blvd": "blvd",
                "drive": "dr", "dr": "dr", "court": "ct", "ct": "ct", "terrace": "ter", "ter": "ter",
                "parkway": "pkwy", "pkwy": "pkwy", "way": "way", "circle": "cir", "cir": "cir"}
UNIT_WORDS = frozenset({"apt", "apartment", "unit", "bsmt", "basement", "fl", "floor", "rear", "front", "ste",
                        "suite", "rm", "room", "ph"})
# A hint with one of these words describes someone ("Man in a wheelchair") instead of naming them.
DESCRIBES_SOMEONE = frozenset({
    "man", "men", "woman", "women", "lady", "gentleman", "person", "people", "resident", "residents", "neighbor",
    "neighbour", "neighbors", "tenant", "tenants", "occupant", "family", "household", "caller", "someone",
    "somebody", "elderly", "senior", "kid", "kids", "child", "children", "baby", "owner", "landlord", "super"})
# Words dropped from a name: titles, relations ("Mrs. Chen's son" is still a Chen) and filler.
NOT_A_NAME = frozenset({
    "mr", "mrs", "ms", "miss", "mx", "dr", "sr", "sra", "jr", "senor", "senora", "the", "a", "an", "and", "of", "in",
    "at", "on", "with", "her", "his", "their", "wife", "husband", "son", "daughter", "mother", "father", "mom", "dad",
    "grandmother", "grandfather", "grandson", "granddaughter", "brother", "sister", "aunt", "uncle"})
CLOSE_WORD = 0.75  # difflib ratio: "chenn"~"chen" 0.89 counts; "mae"~"mei" 0.67 and "zed"~"mei" 0.33 don't
AMBIGUITY_RATIO = 1.5  # the best fuzzy hit must outscore the runner-up by this much


def normalize(value: str) -> str:
    """Exact-match key: case, spacing and punctuation don't count."""
    return re.sub(r"[\W_]+", "", value.casefold())


def parse_address(address: str) -> tuple[str | None, str | None, str | None]:
    """(house number, street, unit), with street types abbreviated and units normalized.

    '43-41 QUAILBROOK ST BSMT' and '4341 Quailbrook Street basement' -> ('4341', 'quailbrook st', 'bsmt');
    'Tern Harbor Rd, basement' -> (None, 'tern harbor rd', None); a block range ('41-01 to 41-99') -> all None.
    """
    first, *rest = address.casefold().split(",")
    if re.search(r"\bto\b", first):
        return None, None, None
    words = re.findall(r"#?[\w-]+", first)
    number = words.pop(0).replace("-", "") if words and re.fullmatch(r"\d+(-\d+)?[a-z]?", words[0]) else None
    street: list[str] = []
    while words and not (words[0] in UNIT_WORDS or words[0].startswith("#")):
        word = words.pop(0)
        street.append(STREET_TYPES.get(word, re.sub(r"^(\d+)(st|nd|rd|th)$", r"\1", word)))
        if street[-1] in STREET_TYPES.values():
            break  # what follows the street type is the unit ("1F", "Bsmt")
    unit = _unit(words) or next((_unit(re.findall(r"#?[\w-]+", part)) for part in rest[:1]
                                 if re.search(r"#|\b(apt|unit|bsmt|basement|fl|floor)\b|\b\d+f\b", part)), None)
    return number, " ".join(street) or None, unit


def _unit(words: list[str]) -> str | None:
    """'APT 1F', '#1F', '1f' -> '1f'; 'basement', 'Bsmt' -> 'bsmt'; '3rd floor' -> '3f'."""
    text = " ".join(word.lstrip("#") for word in words if word not in ("apt", "apartment", "unit", "ste", "suite"))
    text = re.sub(r"\bbasement\b", "bsmt", text)
    text = re.sub(r"\b(\d+)(st|nd|rd|th)?\s*(fl|floor)\b|\b(fl|floor)\s*(\d+)\b", lambda m: f"{m[1] or m[5]}f", text)
    return normalize(text) or None


def dwelling_key(address: str) -> str | None:
    """House number, street and unit: one dwelling however it is written. None without a house number."""
    number, street, unit = parse_address(address)
    return " ".join(part for part in (number, street, unit) if part) if number and street else None


def name_words(name: str) -> set[str]:
    """Words that could identify a person: 'Mrs. Chen' -> {'chen'}; 'elderly woman lives alone' -> set()."""
    words = re.findall(r"[^\W\d_]+", name.casefold())
    if DESCRIBES_SOMEONE.intersection(words):
        return set()
    return {word for word in words if len(word) > 1 and word not in NOT_A_NAME}


def seed_household(scope: RunScope, household_id: str, **identity: str) -> bool:
    """Create a run's household with its identity (name, address, language) before events arrive."""
    doc = {"household_id": household_id, **identity, "applied_event_ids": []}
    return scope.insert_once(HOUSEHOLDS, doc, key="household_id")


def seed_registry(scope: RunScope, entries: list[Mapping]) -> int:
    """Seed the run's households from the scenario registry at run start. Returns how many were new."""
    identity = ("name", "address", "language")
    return sum(seed_household(scope, entry["household_id"], **{key: entry[key] for key in identity if entry.get(key)})
               for entry in entries)


def match_household(scope: RunScope, hint: Mapping[str, str], fuzzy: bool = False) -> str | None:
    """Resolve an identity hint within the run. Ambiguity returns None rather than a guess.

    A dwelling-level address decides: only households at that dwelling can match, a name that
    clearly belongs to someone else vetoes one, and the exact name picks between several. If the
    dwelling matches nobody, no name overrides it. Without a dwelling address an exact name matches
    (with fuzzy=True, a fuzzy one too), unless a street-only mention puts that household elsewhere.
    """
    households = scope.find(HOUSEHOLDS)
    name = (hint.get("name") or "").strip()
    number, street, unit = parse_address(hint.get("address") or "")
    if number and street:
        here = [(h, parse_address(h.get("address") or "")[2]) for h in households
                if parse_address(h.get("address") or "")[:2] == (number, street)
                and _names_agree(name, h.get("name") or "")]
        if unit:  # the same unit wins; a household with no unit on file stays possible; another unit is out
            here = [pair for pair in here if pair[1] == unit] or [pair for pair in here if pair[1] is None]
        if len(here) > 1:
            here = [pair for pair in here if name and normalize(pair[0].get("name") or "") == normalize(name)]
        return here[0][0]["household_id"] if len(here) == 1 else None
    if not name:
        return None
    named = [h for h in households if normalize(h.get("name") or "") == normalize(name)
             and _same_street(street, h.get("address") or "")]
    if len(named) == 1:
        return named[0]["household_id"]
    return _fuzzy_name(scope, name, street) if fuzzy and not named else None


def file_household(scope: RunScope, hint: Mapping[str, str]) -> str | None:
    """File an unregistered household from a report that names a person at a dwelling address.

    For hints that matched nobody. A description ("elderly woman lives alone"), a street-only
    mention or a block range isn't enough, so background reports never become households.
    """
    name, address = (hint.get("name") or "").strip(), (hint.get("address") or "").strip()
    key = dwelling_key(address)
    if not key or not name_words(name):
        return None
    household_id = stable_id("filed", scope.run_id, key, normalize(name))
    seed_household(scope, household_id, name=name, address=address, filed=True)  # W1 traces the match
    return household_id


def _names_agree(name: str, other: str) -> bool:
    """False only when both name someone and no word is even a near spelling of the other's."""
    words, others = name_words(name), list(name_words(other))
    return not words or not others or any(difflib.get_close_matches(w, others, n=1, cutoff=CLOSE_WORD) for w in words)


def _same_street(street: str | None, address: str) -> bool:
    other = parse_address(address)[1]
    return street is None or other is None or other == street


def _fuzzy_name(scope: RunScope, name: str, street: str | None) -> str | None:
    if not name_words(name):  # a description can't fuzzily match anyone
        return None
    words = name_words(name)
    hits = []
    for household in scope.find(HOUSEHOLDS):
        others = name_words(household.get("name") or "")
        if not others or not _names_agree(name, household.get("name") or ""):
            continue
        if not _same_street(street, household.get("address") or ""):
            continue
        score = sum(max(difflib.SequenceMatcher(None, word, other).ratio() for other in others)
                    for word in words) / len(words)
        hits.append({**household, "score": score})
    hits.sort(key=lambda hit: (-hit["score"], hit["household_id"]))
    if len(hits) == 1 or (len(hits) > 1 and hits[0]["score"] >= AMBIGUITY_RATIO * hits[1]["score"]):
        return hits[0]["household_id"]
    return None


def apply_event(scope: RunScope, household_id: str, event_id: str, ts: float) -> bool:
    """Record an event against a household exactly once. False means it was already applied.

    The id is pushed in one atomic update that only matches while it is absent, so a replayed
    or duplicated event can't be applied twice.
    """
    scope.update_one(HOUSEHOLDS, {"household_id": household_id},
                     {"$setOnInsert": {"applied_event_ids": []}}, upsert=True)
    result = scope.update_one(HOUSEHOLDS, {"household_id": household_id, "applied_event_ids": {"$ne": event_id}},
                              {"$push": {"applied_event_ids": event_id}, "$max": {"last_event_ts": ts}})
    if result.modified_count:
        emit(scope, "memory", "event_applied", ts, household_id=household_id, event_id=event_id)
    return bool(result.modified_count)


def get_household(scope: RunScope, household_id: str) -> dict | None:
    return scope.find_one(HOUSEHOLDS, {"household_id": household_id})


def last_contact_by_household(scope: RunScope, scenario_id: str, as_of_ts: float) -> dict[str, float]:
    """Latest person contact per household that the run could see by `as_of_ts`.

    Only events this run applied to the household count, and only a visit note or a call not
    marked unanswered. Reading events (not a stored maximum) keeps it exact for any `as_of_ts`.
    """
    applied: dict[str, list[str]] = {}
    for household in scope.find(HOUSEHOLDS):
        for event_id in household.get("applied_event_ids", []):
            applied.setdefault(event_id, []).append(household["household_id"])
    if not applied:
        return {}
    query = {**visible_query(scope.run_id, scenario_id, as_of_ts), "_id": {"$in": list(applied)},
             "source": {"$in": list(CONTACT_SOURCES)}, "answered": {"$ne": False}}
    last: dict[str, float] = {}
    for event in checked_events(scope.db[EVENTS].find(query), scope.run_id, scenario_id, as_of_ts):
        for household_id in applied[event["_id"]]:
            last[household_id] = max(event["ts"], last.get(household_id, event["ts"]))
    return last
