import pytest

from db.bootstrap import CALL_REQUESTS, PROPOSALS, SYSTEM_EVENTS
from db.fakes import FakeDatabase
from db.scope import RunIsolationError, RunScope, stable_id
from db.writes import advance_status, decide_proposal, insert_proposal, schedule_call


def proposal(run_id, **fields):
    """Shaped like the runtime's lapsed-promise proposal (schemas.Proposal)."""
    return {"_id": stable_id("proposal", run_id, "promise-17", "promise_check_in"), "run_id": run_id,
            "scenario_id": "s1", "household_id": "hh-chen", "kind": "promise_check_in", "status": "pending",
            "promise_id": "promise-17", "reason": "Promise passed its deadline", "ts": 72.0,
            "cited_event_ids": ["s1_e_000042"], **fields}


def call_request(run_id, proposal_id, now_ts, request_id=None):
    """Shaped like the runtime's CallRequest: requested_ts is the tick that asked."""
    return {"_id": request_id or stable_id("callreq", run_id, proposal_id), "run_id": run_id,
            "scenario_id": "s1", "household_id": "hh-chen", "proposal_id": proposal_id,
            "purpose": "promise_check_in", "requested_ts": now_ts}


def test_replaying_a_proposal_keeps_the_coordinators_decision(database):
    run = RunScope(database, "run-a")
    first = proposal("run-a")
    assert insert_proposal(run, first)
    assert decide_proposal(run, first["_id"], "approved", ts=73.0)

    # The runtime crashes and replays the tick that created the proposal.
    assert not insert_proposal(run, {**first, "reason": "rewritten"})

    [stored] = run.find(PROPOSALS)
    assert stored["status"] == "approved" and stored["reason"] == first["reason"]
    assert run.count(SYSTEM_EVENTS, {"action": "proposal_created"}) == 1


def test_a_decided_proposal_cannot_be_decided_again(database):
    run = RunScope(database, "run-a")
    first = proposal("run-a")
    insert_proposal(run, first)
    assert decide_proposal(run, first["_id"], "dismissed", ts=73.0, reason="Son already picked her up")
    assert not decide_proposal(run, first["_id"], "approved", ts=74.0)
    assert run.find_one(PROPOSALS, {"_id": first["_id"]})["status"] == "dismissed"
    with pytest.raises(ValueError):
        decide_proposal(run, first["_id"], "pending", ts=75.0)


def test_an_approved_proposal_queues_exactly_one_call_across_ticks(database):
    run = RunScope(database, "run-a")
    approved = proposal("run-a", status="approved")["_id"]
    assert schedule_call(run, call_request("run-a", approved, now_ts=74.0))

    # Every later tick re-checks the approved proposal and asks again at the current time,
    # even with a request _id derived from that time.
    for now_ts in (76.0, 78.0, 80.0):
        assert not schedule_call(run, call_request("run-a", approved, now_ts))
        assert not schedule_call(run, call_request("run-a", approved, now_ts, request_id=f"callreq-{now_ts}"))

    [queued] = run.find(CALL_REQUESTS)
    assert queued["_id"] == stable_id("callreq", "run-a", approved)  # the caller's _id is kept
    assert queued["requested_ts"] == 74.0 and queued["status"] == "queued"
    assert run.count(SYSTEM_EVENTS, {"action": "call_queued"}) == 1


def test_a_queued_call_keeps_its_status_when_requested_again(database):
    run = RunScope(database, "run-a")
    request = call_request("run-a", "proposal-1", now_ts=74.0)
    assert schedule_call(run, request)
    assert advance_status(run, CALL_REQUESTS, request["_id"], "queued", "dialed", ts=74.5)
    assert not schedule_call(run, {**request, "requested_ts": 76.0})
    assert run.find_one(CALL_REQUESTS)["status"] == "dialed"


def test_runs_cannot_read_each_others_documents(database):
    run_a, run_b = RunScope(database, "run-a"), RunScope(database, "run-b")
    first = proposal("run-a")
    insert_proposal(run_a, first)
    assert run_b.find_one(PROPOSALS, {"_id": first["_id"]}) is None
    assert run_b.find(PROPOSALS) == [] and run_b.count(SYSTEM_EVENTS) == 0
    for foreign in ({"run_id": "run-a"}, {"run_id": {"$in": ["run-a", "run-b"]}}):
        with pytest.raises(RunIsolationError):
            run_b.find(PROPOSALS, foreign)


def test_runs_cannot_write_each_others_documents(database):
    run_a, run_b = RunScope(database, "run-a"), RunScope(database, "run-b")
    first = proposal("run-a")
    insert_proposal(run_a, first)
    assert not decide_proposal(run_b, first["_id"], "approved", ts=73.0)
    with pytest.raises(RunIsolationError):  # run-a's _id, restamped for run-b
        insert_proposal(run_b, {**first, "run_id": "run-b"})
    with pytest.raises(RunIsolationError):  # a run-a document through run-b's scope
        insert_proposal(run_b, first)
    with pytest.raises(RunIsolationError):
        run_a.update_one(PROPOSALS, {"_id": first["_id"]}, {"$set": {"run_id": "run-b"}})
    with pytest.raises(RunIsolationError):
        run_b.insert(SYSTEM_EVENTS, {"run_id": "run-a", "action": "forged"})
    assert run_a.find_one(PROPOSALS, {"_id": first["_id"]})["status"] == "pending"
    assert run_a.count(SYSTEM_EVENTS, {"action": "forged"}) == 0


def test_runs_have_independent_proposals_and_call_queues(database):
    run_a, run_b = RunScope(database, "run-a"), RunScope(database, "run-b")
    for run in (run_a, run_b):
        assert insert_proposal(run, proposal(run.run_id))
        assert schedule_call(run, call_request(run.run_id, proposal(run.run_id)["_id"], now_ts=74.0))
    assert decide_proposal(run_a, proposal("run-a")["_id"], "approved", ts=73.0)
    assert run_b.find_one(PROPOSALS)["status"] == "pending"
    assert run_a.count(CALL_REQUESTS) == run_b.count(CALL_REQUESTS) == 1


@pytest.mark.parametrize("run_id", ["", "   ", None, "scenario"])
def test_a_scope_needs_a_real_run_id(run_id):
    with pytest.raises(RunIsolationError):
        RunScope(FakeDatabase(), run_id)
