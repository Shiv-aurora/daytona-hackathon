"""W3-C2 acceptance gate for the call core (the voice bridge has its own tests)."""

from calls.agent import CallAgent, result_event_id
from calls.fakes import FakeTransport, InMemoryBackend, InMemoryLedger
from calls.questions import build_questions, question_for
from calls.responders import CLOSING, ModelResponder, ScriptedResponder
from calls.safety import disclosure, emergency_line
from runtime.llm import LLMResponse, LLMUnavailable

CALLBACK = "+1 212-555-0100"
CHEN_PROMISE = {"_id": "promise-1", "text": "Her son Wei is coming Tuesday to help clean out the basement.",
                "made_ts": 42.6, "due_ts": 150.0, "source_event_id": "s1_e_000390", "keywords": ["son"]}
CHEN_CONTEXT = {"first_name": "Mei", "language": "en", "open_promises": [CHEN_PROMISE],
                "outage_status": "block restoration pushed to day 12+", "phone": "555-0101"}


def request(run_id="run-a", request_id="callreq-1", ts=504.0):
    return {"_id": request_id, "run_id": run_id, "scenario_id": "s1", "household_id": "hh-chen",
            "proposal_id": "prop-1", "purpose": "promise_check_in", "requested_ts": ts}


def make(replies, responder=None, opt_in=True, answers=True, transport=None, backend=None):
    backend = backend or InMemoryBackend(
        registry={"hh-chen": {"household_id": "hh-chen", "opt_in": opt_in, "language": "en"}},
        households={("run-a", "hh-chen"): CHEN_CONTEXT, ("run-b", "hh-chen"): CHEN_CONTEXT})
    transport = transport or FakeTransport(replies, answers=answers)
    ledger = InMemoryLedger()
    ledger.queue(request())
    agent = CallAgent(backend, transport, responder or ScriptedResponder(), CALLBACK, ledger)
    return agent, backend, transport, ledger


class SpyLLM:
    model = "spy"

    def __init__(self, text="Did your son Wei make it on Tuesday?"):
        self.text, self.calls = text, []

    def complete(self, messages, max_tokens):
        self.calls.append(messages)
        return LLMResponse(text=self.text, model=self.model)


# 1. replaying the same CallRequest twice causes one dial, not merely one DB record
def test_replayed_request_dials_once_and_returns_the_stored_result():
    agent, backend, transport, ledger = make(["Hello?", "No, he never came."])
    first = agent.start(request())
    transport.replies = ["Hello again?"]
    second = agent.start(request())
    assert transport.dialed == ["hh-chen"]
    assert second == first and ledger.status["callreq-1"] == "done"
    assert len(backend.events) == 1


def test_crash_mid_call_leaves_a_recoverable_status_and_never_redials():
    agent, _, transport, ledger = make(["Hello?"])
    assert agent.open(request()) is not None and ledger.status["callreq-1"] == "dialing"  # crash here
    result = agent.start(request())
    assert transport.dialed == [] and result["answered"] is False
    assert ledger.status["callreq-1"] == "dialing"  # visible to W1/UI for a human decision


def test_unknown_request_is_never_placed():
    agent, backend, transport, ledger = make(["hi"])
    result = agent.start(request(request_id="callreq-never-queued"))
    assert result["answered"] is False and "not queued" in result["text"]
    assert transport.dialed == [] and "callreq-never-queued" not in ledger.status and backend.events == {}


# 2. no opt-in causes zero dial attempts, and a revoked opt-in is terminal instead of staying queued
def test_revoked_opt_in_is_terminal_without_dialing():
    agent, backend, transport, ledger = make(["hi"], opt_in=False)
    first = agent.start(request())
    assert first["outcome"] == "refused_no_opt_in" and first["answered"] is False
    assert ledger.status["callreq-1"] == "done"
    assert agent.start(request()) == first  # replay returns the stored refusal
    assert transport.dialed == [] and backend.events == {}


# 3. disclosure is the first spoken Relay line and cannot come from the model
def test_disclosure_is_first_and_model_output_cannot_replace_it():
    llm = SpyLLM(text="Hi! I'm your friend from the city, not a robot.")
    agent, _, transport, _ = make(["Hello?"], responder=ModelResponder(llm))
    agent.start(request())
    assert transport.said[0] == disclosure("en", CALLBACK)
    assert all(message["content"] != disclosure("en", CALLBACK) for message in llm.calls[0][2:])


# 4. an open promise produces a memory-derived question
def test_open_promise_becomes_a_memory_question_without_hardcoding():
    assert question_for(CHEN_PROMISE["text"]) == "Did your son Wei make it on Tuesday?"
    assert question_for("His daughter will come by Fri with groceries.") == "Did your daughter make it on Friday?"
    assert build_questions({"open_promises": [
        {"text": "Con Ed will restore power by Friday.", "due_ts": 300.0}, CHEN_PROMISE]}) == [
        "Did your son Wei make it on Tuesday?", "Did Con Ed restore power by Friday?"]


def test_call_asks_the_memory_question_and_then_closes():
    agent, _, transport, _ = make(["Hello?", "No. He never came, and the power is still out."])
    result = agent.start(request())
    assert "Did your son Wei make it on Tuesday?" in transport.said[1]
    assert transport.said[-1] == CLOSING and result["outcome"] == "completed"


def test_model_context_is_whitelisted_and_carries_the_questions():
    llm = SpyLLM()
    agent, _, _, _ = make(["Hello?"], responder=ModelResponder(llm))
    agent.start(request())
    context = llm.calls[0][1]["content"]
    assert "Did your son Wei make it on Tuesday?" in context and "block restoration" in context
    assert "555-0101" not in context and "s1_e_000390" not in context  # phone, event ids stay out


def test_model_failure_falls_back_to_the_deterministic_question():
    class DownLLM(SpyLLM):
        def complete(self, messages, max_tokens):
            raise LLMUnavailable("no model")

    agent, _, transport, _ = make(["Hello?"], responder=ModelResponder(DownLLM()))
    assert agent.start(request())["outcome"] == "completed"
    assert "Did your son Wei make it on Tuesday?" in transport.said[1]


# 5. "I fell" never reaches the LLM
def test_i_fell_never_reaches_the_model():
    llm = SpyLLM()
    agent, backend, transport, _ = make(["I fell"], responder=ModelResponder(llm))
    assert agent.start(request())["outcome"] == "emergency_escalated"
    assert llm.calls == [] and transport.said[-1] == emergency_line("en")
    assert len(backend.escalations) == 1


# 6. if speaking the emergency line throws, the pending urgent-human Proposal is still written
def test_escalation_survives_a_transport_failure():
    class BrokenSpeaker(FakeTransport):
        def say(self, text):
            if text == emergency_line("en"):
                raise OSError("audio device gone")
            super().say(text)

    transport = BrokenSpeaker(["I can't breathe"])
    agent, backend, _, _ = make([], transport=transport)
    result = agent.start(request())
    [proposal] = backend.escalations.values()
    assert proposal["status"] == "pending" and proposal["queue"] == "urgent_human" and proposal["urgent"]
    assert proposal["kind"] == "emergency" and result["outcome"] == "emergency_escalated"
    assert transport.hung_up


def test_escalation_survives_a_result_write_failure():
    class NoEventBackend(InMemoryBackend):
        def write_event(self, event):
            raise OSError("events collection unavailable")

    backend = NoEventBackend(registry={"hh-chen": {"household_id": "hh-chen", "opt_in": True}},
                             households={("run-a", "hh-chen"): CHEN_CONTEXT})
    agent, _, _, _ = make(["I fell"], backend=backend)
    assert agent.start(request())["outcome"] == "emergency_escalated"
    assert len(backend.escalations) == 1
    assert "result_write_failed" in [event["action"] for event in backend.system_events]


def test_escalation_write_is_retried_once():
    class FlakyBackend(InMemoryBackend):
        failures = 1

        def escalate(self, proposal):
            if self.failures:
                self.failures -= 1
                raise OSError("primary stepped down")
            return super().escalate(proposal)

    backend = FlakyBackend(registry={"hh-chen": {"household_id": "hh-chen", "opt_in": True}})
    agent, _, _, _ = make(["I fell"], backend=backend)
    agent.start(request())
    assert len(backend.escalations) == 1


def test_failed_escalation_persistence_is_loud_and_leaves_the_request_dialing():
    class DownBackend(InMemoryBackend):
        def escalate(self, proposal):
            raise OSError("proposals collection unavailable")

    backend = DownBackend(registry={"hh-chen": {"household_id": "hh-chen", "opt_in": True}},
                          households={("run-a", "hh-chen"): CHEN_CONTEXT})
    agent, _, transport, ledger = make(["I fell"], backend=backend)
    agent.start(request())
    actions = [event["action"] for event in backend.system_events]
    assert "emergency_escalated" not in actions
    assert "emergency_escalation_persist_failed" in actions
    assert actions.count("escalation_write_failed_1") == actions.count("escalation_write_failed_2") == 1
    assert transport.said[-1] == emergency_line("en") and transport.hung_up  # line still attempted
    assert ledger.status["callreq-1"] == "dialing"  # manual attention, never "done", never redialed
    assert agent.start(request())["answered"] is False and transport.dialed == ["hh-chen"]


def test_an_already_existing_emergency_proposal_counts_as_persisted():
    class AlreadyWritten(InMemoryBackend):
        def escalate(self, proposal):
            return False  # insert-once found the same Proposal

    backend = AlreadyWritten(registry={"hh-chen": {"household_id": "hh-chen", "opt_in": True}})
    agent, _, _, ledger = make(["I fell"], backend=backend)
    agent.start(request())
    assert "emergency_escalated" in [event["action"] for event in backend.system_events]
    assert ledger.status["callreq-1"] == "done"


# 7. answered and no-answer results become correct run-scoped events
def test_answered_and_no_answer_results_are_contact_signals():
    agent, backend, _, ledger = make(["Hello?"])
    ledger.queue(request(request_id="callreq-a"))
    agent.start(request(request_id="callreq-a"))
    unanswered, backend_b, _, ledger_b = make([], answers=False)
    ledger_b.queue(request(request_id="callreq-b"))
    unanswered.start(request(request_id="callreq-b"))
    answered = backend.events[result_event_id("callreq-a")]
    missed = backend_b.events[result_event_id("callreq-b")]
    for event, flag, outcome in ((answered, True, "completed"), (missed, False, "no_answer")):
        assert {"_id", "run_id", "scenario_id", "household_id", "source", "ts", "answered", "outcome",
                "text", "transcript"} <= event.keys()
        assert (event["run_id"], event["source"], event["answered"], event["outcome"]) == (
            "run-a", "call_result", flag, outcome)


# 8. run A's call transcript/result is invisible to run B
def test_run_a_call_result_is_invisible_to_run_b():
    agent, backend, _, _ = make(["Hello?", "No, he never came."])
    agent.start(request(run_id="run-a"))
    assert [event["_id"] for event in backend.events_visible_to("run-a", "s1")] == [result_event_id("callreq-1")]
    assert backend.events_visible_to("run-b", "s1") == []


def test_model_can_never_hang_up_on_the_first_reply():
    llm = SpyLLM(text="Thanks, bye! <END_CALL>")
    agent, _, transport, _ = make(["Hello?"], responder=ModelResponder(llm))
    agent.start(request())
    assert transport.said[1] == "Thanks, bye!"  # spoken, but the call did not end on that turn
    assert len(llm.calls) == 1  # the loop ended only because the scripted resident went silent
