import pytest

from db.bootstrap import REGISTRY
from db.events import record_event
from db.scope import RunScope
from memory.adapter import DemoMemory
from memory.households import seed_household


def event(_id, ts, source, run_id="scenario", **fields):
    return {"_id": _id, "run_id": run_id, "scenario_id": "s1", "ts": ts, "source": source, "text": _id, **fields}


def test_last_contact_counts_only_reached_people_this_run_applied(database):
    memory = DemoMemory(database)
    for doc in (event("visit-chen", 10.0, "visit_note"), event("311-chen", 30.0, "311"),
                event("visit-delgado", 12.0, "visit_note"), event("visit-chen-later", 80.0, "visit_note"),
                event("unapplied-visit", 20.0, "visit_note")):
        record_event(RunScope.scenario(database), doc)
    answered = event("call-chen", 40.0, "call_result", run_id="run-a", answered=True)
    unanswered = event("call-delgado", 45.0, "call_result", run_id="run-a", answered=False)
    for doc in (answered, unanswered):
        record_event(RunScope(database, "run-a"), doc)
    for household_id, doc in (("hh-chen", "visit-chen"), ("hh-chen", "311-chen"), ("hh-delgado", "visit-delgado"),
                              ("hh-chen", "visit-chen-later")):
        memory.apply_household_event("run-a", household_id, event(doc, 0.0, "visit_note"))
    memory.apply_household_event("run-a", "hh-chen", answered)
    memory.apply_household_event("run-a", "hh-delgado", unanswered)

    # A 311 report, an unanswered call, an event nobody applied and anything after as_of don't count.
    assert memory.last_contact_by_household("run-a", "s1", as_of_ts=50.0) == {"hh-chen": 40.0, "hh-delgado": 12.0}
    assert memory.last_contact_by_household("run-a", "s1", as_of_ts=100.0)["hh-chen"] == 80.0
    assert memory.last_contact_by_household("run-a", "s1", as_of_ts=5.0) == {}
    assert memory.last_contact_by_household("run-b", "s1", as_of_ts=100.0) == {}  # run-b applied nothing


def test_registry_entries_are_the_scenarios_own_plus_unscoped_ones(database):
    memory = DemoMemory(database)
    database[REGISTRY].insert_one({"household_id": "hh-b", "scenario_id": "s1", "opt_in": True, "registered_ts": 5.0})
    database[REGISTRY].insert_one({"household_id": "hh-a", "opt_in": False})
    database[REGISTRY].insert_one({"household_id": "hh-c", "scenario_id": "s2", "opt_in": True})
    assert memory.registry_entries("s1") == [{"household_id": "hh-a", "opt_in": False},
                                             {"household_id": "hh-b", "scenario_id": "s1", "opt_in": True,
                                              "registered_ts": 5.0}]


def test_run_promises_and_proposals_cover_every_status_in_the_run(database):
    memory = DemoMemory(database)
    seed_household(RunScope(database, "run-a"), "hh-chen", name="Mei Chen")
    for _id, due_ts in (("p-2", 50.0), ("p-1", 40.0), ("p-3", 40.0)):
        memory.insert_promise({"_id": _id, "run_id": "run-a", "scenario_id": "s1", "household_id": "hh-chen",
                               "text": _id, "keywords": [], "made_ts": 1.0, "due_ts": due_ts, "status": "open",
                               "source_event_id": "e"})
    memory.set_promise_status("run-a", "p-1", "lapsed", ts=41.0)
    for _id in ("prop-b", "prop-a"):
        memory.insert_proposal({"_id": _id, "run_id": "run-a", "scenario_id": "s1", "household_id": "hh-chen",
                                "kind": "check_in", "status": "pending", "reason": "r", "ts": 41.0,
                                "cited_event_ids": []})
    assert [(p["_id"], p["status"]) for p in memory.run_promises("run-a")] == [
        ("p-1", "lapsed"), ("p-3", "open"), ("p-2", "open")]
    assert [p["_id"] for p in memory.run_proposals("run-a")] == ["prop-a", "prop-b"]
    assert memory.run_promises("run-b") == [] and memory.run_proposals("run-b") == []


def test_metrics_and_policy_changes_are_insert_once_and_run_scoped(database):
    memory = DemoMemory(database)
    metric = {"_id": "m-1", "run_id": "run-a", "name": "promises_on_time_pct", "value": 0.4, "scope": "run", "ts": 72.0}
    change = {"_id": "pc-1", "run_id": "run-a", "version": 1, "what_changed": "check in 24h before deadlines",
              "params": {"lead_hours": 24.0}, "metric_values": {"promises_on_time_pct": 0.4}, "ts": 72.0}
    memory.record_metric(metric)
    memory.record_metric({**metric, "value": 0.9})  # a replayed tick
    memory.record_policy_change(change)
    memory.record_policy_change({**change, "what_changed": "rewritten"})
    assert RunScope(database, "run-a").find_one("metrics")["value"] == 0.4
    assert memory.policy_change("run-a", 1) == change
    assert memory.policy_change("run-a", 2) is None and memory.policy_change("run-b", 1) is None
    with pytest.raises(Exception) as clash:  # a different change can't claim version 1
        memory.record_policy_change({**change, "_id": "pc-other"})
    assert clash.value.code == 11000
