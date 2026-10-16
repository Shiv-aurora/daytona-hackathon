"""Crash/resume: each run's small state (graph_state.GraphState), saved after every completed tick.

Resuming loads the last saved state and runs the next tick from its cursor. A crash after a tick's
writes but before its save replays that tick, and every write in a tick is insert-once or
forward-only, so the replay changes nothing. The saved tick only moves forward, so a stale writer
(such as the process that crashed) can never rewind a run's cursor.
"""

from __future__ import annotations

from collections.abc import Mapping

from db.bootstrap import RUN_STATE
from db.checkpoint import check_small_state
from db.scope import DUPLICATE_KEY, RunScope
from interfaces import Cursor


def save_run_state(db, state: Mapping) -> bool:
    """The runtime's on_tick hook. False if this tick, or a later one, is already saved."""
    check_small_state(state)
    scope = RunScope(db, state["run_id"])
    fields = {key: value for key, value in state.items() if key != "run_id"}
    try:
        result = scope.update_one(RUN_STATE, {"_id": scope.run_id, "tick": {"$lt": state["tick"]}},
                                  {"$set": fields}, upsert=True)
    except Exception as exc:  # the driver's DuplicateKeyError: the saved tick is not older
        if getattr(exc, "code", None) != DUPLICATE_KEY:
            raise
        return False
    return result.upserted_id is not None or result.modified_count > 0


def load_run_state(db, run_id: str) -> dict | None:
    """The run's last saved state, to resume from. None for a run that never completed a tick."""
    doc = RunScope(db, run_id).find_one(RUN_STATE, {"_id": run_id})
    return None if doc is None else {key: value for key, value in doc.items() if key != "_id"}


def run_cursor(db, run_id: str) -> Cursor | None:
    """(ts, _id) of the last event the run consumed, as of its last saved tick."""
    state = load_run_state(db, run_id)
    if not state or state.get("cursor_ts") is None:
        return None
    return state["cursor_ts"], state["cursor_id"]
