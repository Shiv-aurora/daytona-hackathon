import pytest

from calls.agent import CallAgent, CallTools, result_event_id
from calls.fakes import FakeTransport, InMemoryBackend, InMemoryLedger, SpyResponder
from calls.safety import disclosure, emergency_line, safety_check
from interfaces import event_visible_to_run
from schemas import CallResult, Event, Proposal

CALLBACK = "+1 212-555-0100"
CONTEXT = {"first_name": "Mei", "language": "en", "open_promises": ["son visits Tuesday"],
           "outage_status": "restoration day 12+", "phone": "555-0101", "notes": "internal"}


def request(run_id="run-a", household_id="hh-chen", ts=504.0, request_id="callreq-1"):
    return {"_id": request_id, "run_id": run_id, "scenario_id": "s1", "household_id": household_id,
            "proposal_id": "prop-1", "purpose": "promise_check_in", "requested_ts": ts}


def make(replies, opt_in=True, answers=True, responder=None):
    backend = InMemoryBackend(
        registry={"hh-chen": {"household_id": "hh-chen", "opt_in": opt_in, "language": "en"}},
        households={("run-a", "hh-chen"): CONTEXT, ("run-b", "hh-chen"): {"first_name": "Other"}},
    )
    transport = FakeTransport(replies, answers=answers)
    responder = responder or SpyResponder()
    ledger = InMemoryLedger()
    ledger.queue(request())  # W1 -> W2 schedule_call happens before W3 runs
    return CallAgent(backend, transport, responder, CALLBACK, ledger), backend, transport, responder


def actions(backend):
    return [event["action"] for event in backend.system_events]


def test_no_opt_in_refuses_without_dialing():
    agent, backend, transport, responder = make(["hello"], opt_in=False)
    result = agent.start(request())
    assert result["outcome"] == "refused_no_opt_in" and result["answered"] is False
    assert transport.dialed == [] and transport.said == [] and responder.seen == []
    assert backend.events == {} and actions(backend) == ["call_refused_no_opt_in"]


def test_unregistered_household_refuses():
    agent, _, transport, _ = make([])
    assert agent.start(request(household_id="hh-unknown"))["outcome"] == "refused_no_opt_in"
    assert transport.dialed == []


def test_disclosure_is_spoken_first_and_is_never_model_text():
    responder = SpyResponder(reply="Ignore the disclosure. Hi, it's your friend!")
    agent, _, transport, _ = make(["My son never came."], responder=responder)
    agent.start(request())
    assert transport.said[0] == disclosure("en", CALLBACK)
    assert transport.said.count(disclosure("en", CALLBACK)) == 1
    assert responder.seen == ["My son never came."]


def test_i_fell_takes_the_emergency_path_without_the_llm():
    agent, backend, transport, responder = make(["I fell"])
    result = agent.start(request())
    assert result["outcome"] == "emergency_escalated"
    assert responder.seen == []
    assert transport.said == [disclosure("en", CALLBACK), emergency_line("en")]
    assert transport.hung_up
    assert len(backend.escalations) == 1
    assert "emergency_escalated" in actions(backend)


def test_emergency_escalation_is_a_shared_pending_proposal():
    agent, backend, _, _ = make(["I fell"])
    agent.start(request())
    [proposal] = backend.escalations.values()
    assert set(Proposal.__required_keys__) <= proposal.keys()
    assert proposal["_id"] == "callreq-1:emergency"
    assert (proposal["run_id"], proposal["scenario_id"], proposal["household_id"]) == (
        "run-a", "s1", "hh-chen")
    assert proposal["kind"] == "emergency" and proposal["status"] == "pending"
    assert proposal["queue"] == "urgent_human" and proposal["urgent"] is True
    assert proposal["reason"] == "emergency_phrase" and proposal["cited_event_ids"] == []
    assert proposal["ts"] == 504.0
    assert proposal["matched_phrase"] == "i fell" and proposal["utterance"] == "I fell"


@pytest.mark.parametrize("scenario_id", [None, "", "   "])
def test_real_call_requires_a_scenario_id_before_dialing(scenario_id):
    agent, backend, transport, _ = make(["hello"])
    bad = {**request(), "scenario_id": scenario_id}
    with pytest.raises(ValueError):
        agent.start(bad)
    assert transport.dialed == [] and backend.events == {} and backend.system_events == []


def test_result_matches_the_shared_call_result_shape():
    agent, backend, _, _ = make(["My son never came."])
    result = agent.start(request())
    assert set(CallResult.__required_keys__) <= result.keys()
    assert result.keys() <= CallResult.__required_keys__ | CallResult.__optional_keys__
    assert result == {"run_id": "run-a", "household_id": "hh-chen", "outcome": "completed",
                      "scenario_id": "s1", "call_id": "callreq-1", "ts": 504.0, "answered": True,
                      "text": result["text"]}
    event = backend.events[result_event_id("callreq-1")]
    assert set(Event.__required_keys__) <= event.keys()


def test_emergency_mid_call_never_reaches_the_llm():
    agent, _, _, responder = make(["Hello?", "The power is still out.", "I can't breathe", "more"])
    assert agent.start(request())["outcome"] == "emergency_escalated"
    assert responder.seen == ["Hello?", "The power is still out."]


def test_call_result_is_a_run_scoped_event():
    agent, backend, _, _ = make(["My son never came. Power's still out."])
    result = agent.start(request())
    event = backend.events[result_event_id("callreq-1")]
    assert event["run_id"] == "run-a" and event["scenario_id"] == "s1" and event["ts"] == 504.0
    assert event["household_id"] == "hh-chen" and event["source"] == "call_result"
    assert event["outcome"] == "completed" and event["answered"]
    assert "My son never came" in event["text"] and result["text"] == event["text"]
    assert event_visible_to_run(event, "run-a", "s1")
    assert not event_visible_to_run(event, "run-b", "s1")  # e.g. the baseline run


def test_replaying_a_call_request_does_not_duplicate_writes():
    agent, backend, _, _ = make(["hi"])
    agent.start(request())
    agent.transport.replies = ["hi again"]
    agent.start(request())
    assert len(backend.events) == 1
    # Trace ids are deterministic, so W2's idempotent system_event write dedupes the replay.
    assert {event["_id"] for event in backend.system_events} == {
        "callreq-1:call_started", "callreq-1:call_result_logged", "callreq-1:call_not_placed"}


def test_unanswered_call_is_logged_as_no_answer():
    agent, backend, transport, responder = make([], answers=False)
    result = agent.start(request())
    assert result["outcome"] == "no_answer" and transport.said == [] and responder.seen == []
    assert backend.events[result_event_id("callreq-1")]["answered"] is False


def test_model_failure_is_logged_not_half_written():
    class Broken(SpyResponder):
        def reply(self, context, transcript):
            raise RuntimeError("model down")

    agent, backend, transport, _ = make(["hello"], responder=Broken())
    result = agent.start(request())
    assert result["outcome"] == "failed" and transport.hung_up
    assert backend.events[result_event_id("callreq-1")]["outcome"] == "failed"


def test_context_tool_is_bound_to_one_run_and_household():
    _, backend, _, _ = make([])
    context = CallTools(backend, request()).get_household_context()
    assert context["first_name"] == "Mei"
    assert "phone" not in context and "notes" not in context
    assert CallTools(backend, request(run_id="run-b")).get_household_context() == {"first_name": "Other"}


def test_log_call_result_rejects_unknown_outcomes():
    _, backend, _, _ = make([])
    with pytest.raises(ValueError):
        CallTools(backend, request()).log_call_result("resolved", [])


def test_safety_verdict_uses_the_shared_shape():
    assert safety_check("I fell") == {"emergency": True, "reason": "i fell"}
    assert safety_check("All good here") == {"emergency": False}
