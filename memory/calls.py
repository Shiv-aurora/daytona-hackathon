"""Offline adapters for W3's call agent: `CallLedger` over call_requests, and `interfaces.CallBackend`.

A request moves queued -> dialing -> done, each step one atomic compare-and-set on its status, so it
is dialed at most once and a replay gets the stored result. A call result is written as the run's
own event; one that sorts at or before the run's saved cursor is refused (db.events.LateEventError)
rather than silently never read, so call results must be stamped with the time the call ended.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from db.bootstrap import CALL_REQUESTS, EVENTS
from db.events import record_event
from db.scope import RunScope
from db.writes import advance_status, insert_proposal, schedule_call
from memory.adapter import DemoMemory
from memory.households import get_household

PROMISE_FIELDS = ("text", "made_ts", "due_ts")
RECENT_CALLS = 5


class DemoCallLedger:
    """calls.agent.CallLedger, plus interfaces.CallsPort for the runtime to queue with."""

    def __init__(self, db: Any):
        self.db = db

    def schedule_call(self, request: Mapping) -> bool:
        """Queue once per proposal (db.writes.schedule_call)."""
        return schedule_call(RunScope(self.db, request["run_id"]), request)

    queue = schedule_call  # the name W3's in-memory ledger uses

    def claim(self, request: Mapping, ts: float) -> bool:
        """queued -> dialing. False for a request that was never queued or is already claimed."""
        return advance_status(RunScope(self.db, request["run_id"]), CALL_REQUESTS, request["_id"], "queued",
                              "dialing", ts)

    def finish(self, request: Mapping, result: Mapping) -> None:
        """dialing -> done, keeping the result so a replay returns it instead of redialing."""
        advance_status(RunScope(self.db, request["run_id"]), CALL_REQUESTS, request["_id"], "dialing", "done",
                       result.get("ts", request["requested_ts"]), result=dict(result))

    def result(self, request_id: str) -> dict | None:
        # Request ids are derived from their run_id, so the id alone names one run's request.
        doc = self.db[CALL_REQUESTS].find_one({"_id": request_id})
        return None if doc is None else doc.get("result")


class DemoCallBackend:
    """interfaces.CallBackend: run-scoped reads, insert-once writes."""

    def __init__(self, db: Any):
        self.db, self.memory = db, DemoMemory(db)

    def registry_entry(self, household_id: str) -> dict | None:
        return self.memory.registry_entry(household_id)

    def household_context(self, run_id: str, household_id: str) -> dict:
        """What the call may talk about: open promises and earlier calls, from this run only."""
        scope = RunScope(self.db, run_id)
        entry = self.memory.registry_entry(household_id) or {}
        household = get_household(scope, household_id) or {}
        calls = scope.find(EVENTS, {"household_id": household_id, "source": "call_result"}, sort=[("ts", -1)],
                           limit=RECENT_CALLS)
        context = {
            "first_name": entry.get("first_name"),
            "language": entry.get("language") or household.get("language"),
            "open_promises": [{key: p[key] for key in PROMISE_FIELDS if key in p}
                              for p in self.memory.open_promises(run_id, household_id=household_id)],
            "recent_calls": [{"ts": c["ts"], "outcome": c.get("outcome"), "answered": c.get("answered")}
                             for c in calls],
        }
        return {key: value for key, value in context.items() if value is not None}

    def write_event(self, event: Mapping) -> bool:
        return record_event(RunScope(self.db, event["run_id"]), event)

    def escalate(self, proposal: Mapping) -> bool:
        return insert_proposal(RunScope(self.db, proposal["run_id"]), proposal)

    def system_event(self, event: dict) -> None:
        self.memory.system_event(event)
