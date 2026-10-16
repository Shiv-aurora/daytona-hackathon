"""Call agent integration over the offline ledger and backend."""

from calls.agent import CallAgent
from calls.fakes import FakeTransport, SpyResponder
from db.bootstrap import CALL_REQUESTS, EVENTS, PROPOSALS, REGISTRY
from db.runs import save_run_state
from db.scope import RunScope, stable_id
from memory.adapter import DemoMemory
from memory.calls import DemoCallBackend, DemoCallLedger
from memory.startup import start_run

CALLBACK = "+1 212-555-0100"


def setup(database):
    database[REGISTRY].insert_one({"household_id": "hh-chen", "scenario_id": "s1", "opt_in": True, "language": "en",
                                   "first_name": "Mei", "name": "Mei Chen", "address": "41-22 Hollow Oak Ln"})
    for run_id in ("run-a", "run-b"):
        start_run(database, run_id, "s1", "2021-09-01T20:00:00-04:00")
    DemoMemory(database).insert_promise({
        "_id": "promise-1", "run_id": "run-a", "scenario_id": "s1", "household_id": "hh-chen",
        "text": "Son Wei will take her to stay with him", "keywords": [], "made_ts": 42.6, "due_ts": 144.0,
        "status": "open", "source_event_id": "s1_e_000376"})
    return DemoCallLedger(database), DemoCallBackend(database)


def request(requested_ts=150.0, proposal_id="proposal-1"):
    return {"_id": stable_id("callreq", "run-a", proposal_id), "run_id": "run-a", "scenario_id": "s1",
            "household_id": "hh-chen", "proposal_id": proposal_id, "purpose": "promise_check_in",
            "requested_ts": requested_ts}


def test_one_queued_request_places_one_call_whose_answer_is_contact_for_that_run_only(database):
    ledger, backend = setup(database)
    memory, queued = DemoMemory(database), request()
    assert ledger.schedule_call(queued)
    context = backend.household_context("run-a", "hh-chen")
    assert context["first_name"] == "Mei" and context["open_promises"][0]["due_ts"] == 144.0

    transport = FakeTransport(["Yes. My son never came, but I'm staying with my neighbor."])
    agent = CallAgent(backend, transport, SpyResponder(), CALLBACK, ledger)
    first = agent.start(queued)
    assert first["outcome"] == "completed" and first["answered"] and transport.dialed == ["hh-chen"]

    # Replaying the dispatch returns the stored result without dialing again.
    assert agent.start(queued) == first and transport.dialed == ["hh-chen"]
    assert not ledger.claim(queued, 151.0)
    [stored] = RunScope(database, "run-a").find(CALL_REQUESTS)
    assert stored["status"] == "done" and stored["result"] == first

    # The runtime reads the result on its next tick; an answered call is contact.
    [result] = [e for e in memory.events_after("run-a", "s1", None, 156.0, 100) if e["source"] == "call_result"]
    assert result["_id"] == f"{queued['_id']}:result" and result["run_id"] == "run-a"
    assert memory.apply_household_event("run-a", "hh-chen", result)
    assert memory.last_contact_by_household("run-a", "s1", as_of_ts=156.0) == {"hh-chen": 150.0}
    assert backend.household_context("run-a", "hh-chen")["recent_calls"] == [
        {"ts": 150.0, "outcome": "completed", "answered": True}]

    # Another run sees none of it.
    assert all(e["run_id"] != "run-a" for e in memory.events_after("run-b", "s1", None, 156.0, 100))
    assert memory.last_contact_by_household("run-b", "s1", as_of_ts=156.0) == {}
    assert backend.household_context("run-b", "hh-chen").get("recent_calls", []) == []


def test_an_unqueued_request_is_never_placed(database):
    ledger, backend = setup(database)
    transport = FakeTransport(["hello"])
    result = CallAgent(backend, transport, SpyResponder(), CALLBACK, ledger).start(request())
    assert result["outcome"] == "failed" and transport.dialed == []


def test_an_emergency_escalates_through_demo_memory_before_the_call_ends(database):
    ledger, backend = setup(database)
    queued = request()
    ledger.schedule_call(queued)
    result = CallAgent(backend, FakeTransport(["I fell"]), SpyResponder(), CALLBACK, ledger).start(queued)
    [escalation] = RunScope(database, "run-a").find(PROPOSALS, {"kind": "emergency"})
    assert result["outcome"] == "emergency_escalated" and escalation["urgent"] and escalation["status"] == "pending"
    assert RunScope(database, "run-b").count(PROPOSALS) == 0


def test_a_result_stamped_behind_the_saved_cursor_is_refused_not_lost_silently(database):
    ledger, backend = setup(database)
    save_run_state(database, {"run_id": "run-a", "scenario_id": "s1", "tick": 30, "now_ts": 180.0, "cursor_ts": 175.0,
                              "cursor_id": "s1_e_000999", "pending_proposal_ids": [], "pending_call_ids": [],
                              "policy_version": 0})
    queued = request(requested_ts=150.0)  # W3 stamps results with requested_ts, now behind the cursor
    ledger.schedule_call(queued)
    result = CallAgent(backend, FakeTransport(["Fine, thanks."]), SpyResponder(), CALLBACK, ledger).start(queued)
    run = RunScope(database, "run-a")
    assert result["outcome"] == "completed" and run.count(EVENTS, {"source": "call_result"}) == 0
    assert run.count("system_events", {"action": "result_write_failed"}) == 1  # W3 traces the refusal
