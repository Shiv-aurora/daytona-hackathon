"""`DemoMemory`: the in-process `interfaces.MemoryPort`, `LedgerPort`, `RetrievalPort` and
`LLMCachePort`, plus the runtime's crash/resume hooks."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from db.bootstrap import (
    METRICS,
    POLICY_CHANGES,
    PROMISES,
    PROPOSALS,
    REGISTRY,
    SYSTEM_EVENTS,
)
from db.cache import llm_cache_get, llm_cache_put
from db.events import events_after, search_events
from db.runs import load_run_state, save_run_state
from db.scope import RunIsolationError, RunScope
from db.writes import advance_status, emit, insert_proposal
from interfaces import Cursor
from memory.households import (
    apply_event,
    file_household,
    get_household,
    last_contact_by_household,
    match_household,
)
from schemas import SCENARIO_RUN_ID, Event, Household, RegistryEntry

PROMISE_OUTCOMES = ("kept", "lapsed")


def _without_id(doc: dict | None) -> dict | None:
    return None if doc is None else {key: value for key, value in doc.items() if key != "_id"}


class DemoMemory:
    """Run-scoped in-process adapter, retained until the SurrealDB worker replaces it."""

    def __init__(self, db: Any, fuzzy: bool = False, file_unregistered: bool = False):
        self.db = db
        self.fuzzy = fuzzy
        self.file_unregistered = file_unregistered

    def events_after(self, run_id: str, scenario_id: str, after: Cursor | None, until_ts: float,
                     limit: int) -> list[Event]:
        return events_after(self.db, run_id, scenario_id, after, until_ts, limit)

    def search_events(self, run_id: str, scenario_id: str, query: str, as_of_ts: float,
                      limit: int) -> list[Event]:
        """Runtime RetrievalPort: relevant events the run could see by `as_of_ts`."""
        return search_events(self.db, run_id, scenario_id, query, as_of_ts, limit)

    def llm_cache_get(self, key: str) -> dict | None:
        """Runtime LLMCachePort."""
        return llm_cache_get(self.db, key)

    def llm_cache_put(self, key: str, value: dict) -> None:
        llm_cache_put(self.db, key, value)

    def save_run_state(self, state: Mapping) -> bool:
        """The runtime's on_tick checkpoint hook; the saved tick only moves forward."""
        return save_run_state(self.db, state)

    def load_run_state(self, run_id: str) -> dict | None:
        """Where a run resumes after a crash or restart."""
        return load_run_state(self.db, run_id)

    def match_household(self, run_id: str, identity_hint: dict[str, str]) -> str | None:
        scope = RunScope(self.db, run_id)
        found = match_household(scope, identity_hint, fuzzy=self.fuzzy)
        if found is None and self.file_unregistered:
            found = file_household(scope, identity_hint)
        return found

    def household(self, run_id: str, household_id: str) -> Household | None:
        return _without_id(get_household(RunScope(self.db, run_id), household_id))

    def apply_household_event(self, run_id: str, household_id: str, event: Event) -> bool:
        if event["run_id"] not in (SCENARIO_RUN_ID, run_id):
            raise RunIsolationError(f"run {run_id!r} cannot apply another run's event {event['_id']!r}")
        return apply_event(RunScope(self.db, run_id), household_id, event["_id"], event["ts"])

    def registry_entry(self, household_id: str) -> RegistryEntry | None:
        return _without_id(self.db[REGISTRY].find_one({"household_id": household_id}))

    def insert_promise(self, promise: dict) -> bool:
        scope = RunScope(self.db, promise["run_id"])
        created = scope.insert_once(PROMISES, {"status": "open", **promise})
        if created:
            emit(scope, "memory", "promise_created", promise.get("made_ts"), promise_id=promise["_id"],
                 household_id=promise.get("household_id"))
        return created

    def open_promises(self, run_id: str, household_id: str | None = None,
                      due_before: float | None = None) -> list[dict]:
        query: dict = {"status": "open"}
        if household_id is not None:
            query["household_id"] = household_id
        if due_before is not None:
            query["due_ts"] = {"$lt": due_before}
        return RunScope(self.db, run_id).find(PROMISES, query, sort=[("due_ts", 1), ("_id", 1)])

    def set_promise_status(self, run_id: str, promise_id: str, status: str, ts: float) -> bool:
        if status not in PROMISE_OUTCOMES:
            raise ValueError(f"a promise can only move from open to one of {PROMISE_OUTCOMES}, not {status!r}")
        return advance_status(RunScope(self.db, run_id), PROMISES, promise_id, "open", status, ts)

    def insert_proposal(self, proposal: dict) -> bool:
        return insert_proposal(RunScope(self.db, proposal["run_id"]), proposal)

    def proposals_with_status(self, run_id: str, status: str) -> list[dict]:
        return RunScope(self.db, run_id).find(PROPOSALS, {"status": status}, sort=[("_id", 1)])

    def system_event(self, event: dict) -> None:
        scope = RunScope(self.db, event["run_id"])
        if "_id" in event:
            scope.insert_once(SYSTEM_EVENTS, event)
        else:
            scope.insert(SYSTEM_EVENTS, event)

    # LedgerPort: run-scoped goal, policy and accounting records.

    def run_promises(self, run_id: str) -> list[dict]:
        return RunScope(self.db, run_id).find(PROMISES, sort=[("due_ts", 1), ("_id", 1)])

    def run_proposals(self, run_id: str) -> list[dict]:
        return RunScope(self.db, run_id).find(PROPOSALS, sort=[("_id", 1)])

    def registry_entries(self, scenario_id: str) -> list[RegistryEntry]:
        """The scenario's registry (entries without a scenario_id belong to every scenario)."""
        entries = self.db[REGISTRY].find({"scenario_id": {"$in": [scenario_id, None]}}, sort=[("household_id", 1)])
        return [_without_id(entry) for entry in entries]

    def last_contact_by_household(self, run_id: str, scenario_id: str, as_of_ts: float) -> dict[str, float]:
        return last_contact_by_household(RunScope(self.db, run_id), scenario_id, as_of_ts)

    def record_metric(self, metric: dict) -> None:
        RunScope(self.db, metric["run_id"]).insert_once(METRICS, metric)

    def record_policy_change(self, change: dict) -> None:
        RunScope(self.db, change["run_id"]).insert_once(POLICY_CHANGES, change)

    def policy_change(self, run_id: str, version: int) -> dict | None:
        return RunScope(self.db, run_id).find_one(POLICY_CHANGES, {"version": version})
