"""Event writes and the reads that span two run_ids.

A run sees its scenario's inputs (run_id "scenario") plus the events it generated itself, and
never another run's, and never anything after the time it asks about. Those rules live here as
explicit queries rather than loosening RunScope, and every result is re-checked before returning.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Mapping
from typing import Any

from db.bootstrap import EVENTS
from db.runs import run_cursor
from db.scope import RunIsolationError, RunScope, require_run_id
from interfaces import Cursor, event_visible_to_run
from schemas import SCENARIO_RUN_ID, Event

REQUIRED_FIELDS = ("_id", "scenario_id", "ts")


class LateEventError(ValueError):
    """A run event at or before the run's saved cursor would never be read, so it is refused."""


def record_event(scope: RunScope, event: Mapping) -> bool:
    """Store an event once by its `_id`, under the scope's run (RunScope.scenario(db) for inputs)."""
    missing = [field for field in REQUIRED_FIELDS if field not in event]
    if missing:
        raise ValueError(f"event is missing {missing}")
    if scope.run_id != SCENARIO_RUN_ID:
        cursor = run_cursor(scope.db, scope.run_id)
        late = cursor is not None and (event["ts"], event["_id"]) <= cursor
        if late and scope.find_one(EVENTS, {"_id": event["_id"]}) is None:
            raise LateEventError(f"event {event['_id']!r} at ts {event['ts']} is not after run "
                                 f"{scope.run_id!r}'s cursor {cursor}, so the run would never read it")
    return scope.insert_once(EVENTS, event)


def events_after(db: Any, run_id: str, scenario_id: str, after: Cursor | None, until_ts: float,
                 limit: int) -> list[Event]:
    """Visible events with (ts, _id) > after and ts <= until_ts, ordered by (ts, _id)."""
    query = visible_query(run_id, scenario_id, until_ts)
    if after is not None:
        after_ts, after_id = after
        query["$or"] = [{"ts": {"$gt": after_ts}}, {"ts": after_ts, "_id": {"$gt": after_id}}]
    return checked_events(db[EVENTS].find(query, sort=[("ts", 1), ("_id", 1)], limit=limit), run_id, scenario_id, until_ts)


def search_events(db: Any, run_id: str, scenario_id: str, query: str, as_of_ts: float,
                  limit: int) -> list[Event]:
    """Rank visible past events by shared words in the offline reference store."""
    visible = visible_query(run_id, scenario_id, as_of_ts)
    if not query.strip() or limit <= 0:
        return []
    found = _rank_by_shared_words(db[EVENTS].find(visible), query, limit)
    return checked_events(found, run_id, scenario_id, as_of_ts)


def visible_query(run_id: str, scenario_id: str, until_ts: float) -> dict:
    if not scenario_id:
        raise ValueError("scenario_id is required")
    return {"scenario_id": scenario_id, "run_id": {"$in": [SCENARIO_RUN_ID, require_run_id(run_id)]},
            "ts": {"$lte": until_ts}}


def checked_events(events: Iterable[dict], run_id: str, scenario_id: str, until_ts: float) -> list[Event]:
    events = list(events)
    if not all(event_visible_to_run(event, run_id, scenario_id) and event["ts"] <= until_ts for event in events):
        raise RunIsolationError(f"event read for run {run_id!r} returned events it may not see")
    return events


def _words(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.casefold()))


def _rank_by_shared_words(events: Iterable[dict], query: str, limit: int) -> list[dict]:
    terms = _words(query)
    scored = [(len(terms & _words(event.get("text") or "")), event) for event in events]
    ranked = sorted((pair for pair in scored if pair[0]), key=lambda pair: (-pair[0], pair[1]["ts"], pair[1]["_id"]))
    return [event for _, event in ranked[:limit]]
