"""Crash after a tick's writes but before its checkpoint, then resume: the replay must change nothing."""

from collections import Counter

from db.bootstrap import HOUSEHOLDS, PROMISES, PROPOSALS, SYSTEM_EVENTS
from db.events import record_event
from db.scope import RunScope, stable_id
from memory.adapter import DemoMemory
from memory.households import seed_household

DAY = 24.0
EVENT_TIMES = {"s1_e_001": 11.0, "s1_e_002": 12.0, "s1_e_003": 40.0, "s1_e_004": 41.0, "s1_e_005": 70.0}


class Crash(Exception):
    pass


def new_state(run_id):
    return {"run_id": run_id, "scenario_id": "s1", "tick": 0, "now_ts": 10.0, "cursor_ts": None, "cursor_id": None,
            "pending_proposal_ids": [], "pending_call_ids": [], "policy_version": 0}


def tick(memory, state, crash=False):
    """One tick in the runtime's write order: consume events in batches, record a promise per event,
    lapse overdue promises into proposals, and only then checkpoint."""
    run_id, scenario_id, now = state["run_id"], state["scenario_id"], state["now_ts"] + DAY
    cursor = None if state["cursor_ts"] is None else (state["cursor_ts"], state["cursor_id"])
    while True:
        batch = memory.events_after(run_id, scenario_id, cursor, now, 2)
        for event in batch:
            memory.apply_household_event(run_id, "hh-chen", event)
            memory.insert_promise({"_id": stable_id("promise", run_id, event["_id"]), "run_id": run_id,
                                   "scenario_id": scenario_id, "household_id": "hh-chen", "text": event["text"],
                                   "keywords": [], "made_ts": event["ts"], "due_ts": event["ts"] + DAY,
                                   "status": "open", "source_event_id": event["_id"]})
            cursor = (event["ts"], event["_id"])
        if len(batch) < 2:
            break
    for promise in memory.open_promises(run_id, due_before=now):
        memory.insert_proposal({"_id": stable_id("proposal", run_id, promise["_id"]), "run_id": run_id,
                                "scenario_id": scenario_id, "household_id": "hh-chen", "kind": "check_in",
                                "status": "pending", "reason": "lapsed", "ts": now, "promise_id": promise["_id"],
                                "cited_event_ids": [promise["source_event_id"]]})
        memory.set_promise_status(run_id, promise["_id"], "lapsed", now)
    if crash:
        raise Crash
    state = {**state, "tick": state["tick"] + 1, "now_ts": now,
             "cursor_ts": cursor[0] if cursor else None, "cursor_id": cursor[1] if cursor else None}
    assert memory.save_run_state(state)
    return state


def run(database, run_id, crash_on_tick=None):
    memory = DemoMemory(database)
    seed_household(RunScope(database, run_id), "hh-chen", name="Mei Chen")
    state = memory.load_run_state(run_id) or new_state(run_id)
    while state["tick"] < 4:
        try:
            state = tick(memory, state, crash=state["tick"] + 1 == crash_on_tick)
        except Crash:
            crash_on_tick = None  # the process restarts and resumes from its last checkpoint
            state = memory.load_run_state(run_id) or new_state(run_id)
    scope = RunScope(database, run_id)
    return {"applied": [h["applied_event_ids"] for h in scope.find(HOUSEHOLDS)],
            "promises": sorted((p["source_event_id"], p["status"]) for p in scope.find(PROMISES)),
            "proposals": scope.count(PROPOSALS),
            "trace": Counter(e["action"] for e in scope.find(SYSTEM_EVENTS)),
            "state": {key: value for key, value in memory.load_run_state(run_id).items() if key != "run_id"}}


def test_a_crash_after_writes_but_before_the_checkpoint_replays_safely(database):
    inputs = RunScope.scenario(database)
    for event_id, ts in EVENT_TIMES.items():
        record_event(inputs, {"_id": event_id, "run_id": "scenario", "scenario_id": "s1", "ts": ts,
                              "source": "visit_note", "text": f"note {event_id}"})
    clean = run(database, "relay-clean")
    for crash_on_tick in (1, 2, 3):
        assert run(database, f"relay-crash-{crash_on_tick}", crash_on_tick) == clean
    assert clean["applied"] == [list(EVENT_TIMES)]
    assert clean["proposals"] == 5 and all(status == "lapsed" for _, status in clean["promises"])
    assert clean["state"]["tick"] == 4 and clean["state"]["cursor_id"] == "s1_e_005"
