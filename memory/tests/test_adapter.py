import inspect

import pytest

from db.bootstrap import REGISTRY, SYSTEM_EVENTS
from db.events import record_event
from db.scope import RunIsolationError, RunScope
from db.writes import decide_proposal
from interfaces import LedgerPort, LLMCachePort, MemoryPort, RetrievalPort
from memory.adapter import DemoMemory
from memory.households import seed_household


def promise(_id, due_ts, run_id="run-a", household_id="hh-chen"):
    return {"_id": _id, "run_id": run_id, "scenario_id": "s1", "household_id": household_id,
            "text": "Son visits Tuesday", "keywords": ["son", "visit"], "made_ts": 3.0, "due_ts": due_ts,
            "status": "open", "source_event_id": "s1_e_042"}


@pytest.mark.parametrize("port", [MemoryPort, LedgerPort, RetrievalPort, LLMCachePort])
def test_demo_memory_implements_every_shared_port_method(port):
    methods = [name for name, member in vars(port).items() if callable(member) and not name.startswith("_")]
    assert methods
    for name in methods:
        ours = inspect.signature(getattr(DemoMemory, name)).parameters.values()
        theirs = inspect.signature(getattr(port, name)).parameters.values()
        assert [(p.name, p.kind, p.default) for p in ours] == [(p.name, p.kind, p.default) for p in theirs], name


def test_household_events_apply_once_and_only_from_visible_sources(database):
    memory = DemoMemory(database)
    seed_household(RunScope(database, "run-a"), "hh-chen", name="Mei Chen", address="12 Elm St")
    scenario_event = {"_id": "s1_e_042", "run_id": "scenario", "scenario_id": "s1", "ts": 3.0,
                      "source": "311", "text": "Son will visit Tuesday"}
    own_event = {**scenario_event, "_id": "run-a:call-1:result", "run_id": "run-a", "ts": 4.0}
    record_event(RunScope.scenario(database), scenario_event)

    assert memory.events_after("run-a", "s1", None, 10.0, 10) == [scenario_event]
    assert memory.match_household("run-a", {"address": "12 elm st."}) == "hh-chen"
    assert memory.apply_household_event("run-a", "hh-chen", scenario_event)
    assert memory.apply_household_event("run-a", "hh-chen", own_event)
    assert not memory.apply_household_event("run-a", "hh-chen", scenario_event)
    with pytest.raises(RunIsolationError):
        memory.apply_household_event("run-b", "hh-chen", own_event)

    household = memory.household("run-a", "hh-chen")
    assert household["applied_event_ids"] == ["s1_e_042", "run-a:call-1:result"] and "_id" not in household
    assert memory.household("run-b", "hh-chen") is None


def test_open_promises_are_run_scoped_and_ordered_by_due_time(database):
    memory = DemoMemory(database)
    assert memory.insert_promise(promise("p-late", due_ts=90.0))
    assert memory.insert_promise(promise("p-soon", due_ts=40.0))
    assert memory.insert_promise(promise("p-other", due_ts=40.0, household_id="hh-delgado"))
    assert not memory.insert_promise(promise("p-soon", due_ts=99.0))

    def open_ids(**filters):
        return [p["_id"] for p in memory.open_promises("run-a", **filters)]

    assert open_ids() == ["p-other", "p-soon", "p-late"]
    assert open_ids(household_id="hh-chen") == ["p-soon", "p-late"]
    assert open_ids(due_before=40.0) == []  # strictly before
    assert open_ids(due_before=40.5) == ["p-other", "p-soon"]
    assert memory.open_promises("run-b") == []


def test_promise_status_only_moves_forward_and_survives_replays(database):
    memory = DemoMemory(database)
    memory.insert_promise(promise("p-17", due_ts=40.0))
    assert not memory.set_promise_status("run-b", "p-17", "kept", ts=41.0)  # another run can't touch it
    assert memory.set_promise_status("run-a", "p-17", "lapsed", ts=41.0)
    assert not memory.set_promise_status("run-a", "p-17", "kept", ts=42.0)
    assert not memory.insert_promise(promise("p-17", due_ts=40.0))  # a replayed tick can't reopen it
    assert memory.open_promises("run-a") == []
    with pytest.raises(ValueError):
        memory.set_promise_status("run-a", "p-17", "open", ts=43.0)


def test_proposals_keep_their_decision_across_replays(database):
    memory = DemoMemory(database)
    proposal = {"_id": "prop-1", "run_id": "run-a", "scenario_id": "s1", "household_id": "hh-chen",
                "kind": "promise_check_in", "status": "pending", "reason": "lapsed", "ts": 41.0,
                "cited_event_ids": ["s1_e_042"]}
    assert memory.insert_proposal(proposal)
    assert decide_proposal(RunScope(database, "run-a"), "prop-1", "approved", ts=42.0)
    assert not memory.insert_proposal(proposal)
    assert [p["_id"] for p in memory.proposals_with_status("run-a", "approved")] == ["prop-1"]
    assert memory.proposals_with_status("run-a", "pending") == []
    assert memory.proposals_with_status("run-b", "approved") == []


def test_registry_reads_and_idempotent_trace_events(database):
    memory = DemoMemory(database)
    database[REGISTRY].insert_one({"household_id": "hh-chen", "opt_in": True, "language": "zh"})
    assert memory.registry_entry("hh-chen") == {"household_id": "hh-chen", "opt_in": True, "language": "zh"}
    assert memory.registry_entry("hh-unknown") is None

    trace = {"_id": "sev-1", "run_id": "run-a", "module": "runtime", "action": "tick_started", "ts": 1.0}
    memory.system_event(trace)
    memory.system_event(trace)  # replayed tick
    memory.system_event({"run_id": "run-a", "module": "runtime", "action": "note", "ts": 1.0})
    run = RunScope(database, "run-a")
    assert run.count(SYSTEM_EVENTS, {"action": "tick_started"}) == 1 and run.count(SYSTEM_EVENTS) == 2
    with pytest.raises(RunIsolationError):
        memory.system_event({**trace, "_id": "sev-2", "run_id": "scenario"})
