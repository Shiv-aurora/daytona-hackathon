"""The ElevenLabs Custom LLM bridge, fully mocked: no key, no network."""

import json

from calls.agent import CallAgent, result_event_id
from calls.fakes import FakeTransport, InMemoryBackend, InMemoryLedger
from calls.responders import CLOSING, ModelResponder
from calls.safety import disclosure, emergency_line
from calls.voice.bridge import FILLER, VoiceBridge, sse_chunks
from calls.voice.setup_agent import agent_config, problems
from runtime.llm import LLMResponse

CALLBACK = "+1 212-555-0100"
SECRET = "test-secret"
AUTH = f"Bearer {SECRET}"
CONTEXT = {"first_name": "Mei", "open_promises": [
    {"text": "Her son Wei is coming Tuesday to help.", "due_ts": 150.0, "made_ts": 42.6}]}


class SpyLLM:
    model = "spy"

    def __init__(self):
        self.calls = []

    def complete(self, messages, max_tokens):
        self.calls.append(messages)
        return LLMResponse(text="Did your son Wei make it on Tuesday?", model=self.model)


def request(request_id="callreq-1", run_id="run-a"):
    return {"_id": request_id, "run_id": run_id, "scenario_id": "s1", "household_id": "hh-chen",
            "proposal_id": "prop-1", "purpose": "promise_check_in", "requested_ts": 504.0}


def make(opt_in=True):
    backend = InMemoryBackend(registry={"hh-chen": {"household_id": "hh-chen", "opt_in": opt_in}},
                              households={("run-a", "hh-chen"): CONTEXT})
    llm, ledger, opened = SpyLLM(), InMemoryLedger(), []
    ledger.queue(request())
    agent = CallAgent(backend, FakeTransport([]), ModelResponder(llm), CALLBACK, ledger)

    def signed_url(language="en"):
        opened.append(language)
        return "wss://example.invalid/signed"

    return VoiceBridge(agent, SECRET, signed_url), backend, llm, ledger, opened


def turn(bridge, text, session_id=None, auth=AUTH):
    body = {"messages": [{"role": "assistant", "content": "earlier"}, {"role": "user", "content": text}]}
    if session_id:
        body["elevenlabs_extra_body"] = {"relay_session_id": session_id}
    status, payload = bridge.chat_completion(body, auth)
    if isinstance(payload, dict):
        return status, payload, None
    chunks = [json.loads(line[6:]) for line in payload if line != "data: [DONE]\n\n"]
    text = "".join(c["choices"][0]["delta"].get("content", "") for c in chunks)
    ended = any(c["choices"][0]["delta"].get("tool_calls") for c in chunks)
    return status, text, ended


def test_unknown_request_opens_no_voice_session():
    bridge, backend, _, ledger, opened = make()
    status, _ = bridge.open_session(request(request_id="callreq-never-queued"))
    assert status == 409 and opened == [] and "callreq-never-queued" not in ledger.status
    assert backend.events == {}


def test_revoked_opt_in_opens_no_voice_session_and_is_terminal():
    bridge, _, _, ledger, opened = make(opt_in=False)
    status, body = bridge.open_session(request())
    assert status == 409 and body["result"]["outcome"] == "refused_no_opt_in"
    assert bridge.open_session(request())[1]["result"] == body["result"]  # replay: stored refusal
    assert opened == [] and ledger.status == {"callreq-1": "done"}


def test_same_request_opens_one_voice_session():
    bridge, _, _, _, opened = make()
    assert bridge.open_session(request())[0] == 200
    status, _ = bridge.open_session(request())
    assert status == 409 and opened == ["en"]


def test_first_message_is_the_code_owned_disclosure():
    bridge, _, _, _, _ = make()
    assert bridge.open_session(request())[1]["first_message"] == disclosure("en", CALLBACK)
    config = agent_config(CALLBACK, "relay.example", "secret-1")
    assert problems(config, CALLBACK) == []
    config["conversation_config"]["agent"]["first_message"] = "Hi, it's your friend!"
    assert "first_message is not the code-owned disclosure" in problems(config, CALLBACK)


def test_agent_check_requires_an_uninterruptible_disclosure():
    config = agent_config(CALLBACK, "relay.example", "secret-1")
    assert config["conversation_config"]["agent"]["disable_first_message_interruptions"] is True
    assert config["conversation_config"]["agent"]["prompt"]["built_in_tools"]["end_call"]["disable_interruptions"]
    config["conversation_config"]["agent"]["disable_first_message_interruptions"] = False
    assert "the disclosure can be interrupted before it finishes" in problems(config, CALLBACK)


def test_agent_check_requires_the_extra_body_override():
    config = agent_config(CALLBACK, "relay.example", "secret-1")
    config["platform_settings"]["overrides"]["custom_llm_extra_body"] = False
    assert any("custom_llm_extra_body" in problem for problem in problems(config, CALLBACK))


def test_session_that_never_heard_the_resident_is_no_answer_not_contact():
    bridge, backend, _, _, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    result = bridge.end_session(session_id)  # e.g. ElevenLabs refused the session before any turn
    assert result["outcome"] == "no_answer" and result["answered"] is False
    assert backend.events[result_event_id("callreq-1")]["answered"] is False


def test_turn_needs_the_shared_secret():
    bridge, _, llm, _, _ = make()
    bridge.open_session(request())
    assert turn(bridge, "Hello?", auth="Bearer wrong")[0] == 401 and llm.calls == []


def test_turn_asks_the_memory_question_through_the_model():
    bridge, _, llm, _, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    status, text, ended = turn(bridge, "Hello?", session_id)
    assert status == 200 and text == FILLER + "Did your son Wei make it on Tuesday?" and not ended
    assert "Did your son Wei make it on Tuesday?" in llm.calls[0][1]["content"]


def test_i_fell_ends_the_call_without_the_model():
    bridge, backend, llm, ledger, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    status, text, ended = turn(bridge, "I fell and I can't get up", session_id)
    assert status == 200 and text == emergency_line("en") and ended and llm.calls == []  # no filler either
    [proposal] = backend.escalations.values()
    assert proposal["status"] == "pending" and proposal["queue"] == "urgent_human"
    assert backend.events[result_event_id("callreq-1")]["outcome"] == "emergency_escalated"
    assert ledger.status["callreq-1"] == "done"


def test_disconnect_logs_a_run_scoped_result_with_transcript():
    bridge, backend, _, _, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    turn(bridge, "Hello?", session_id)
    result = bridge.end_session(session_id)
    event = backend.events[result_event_id("callreq-1")]
    assert result["outcome"] == "completed" and event["run_id"] == "run-a" and event["answered"]
    assert [t["speaker"] for t in event["transcript"]] == ["relay", "resident", "relay"]
    assert backend.events_visible_to("run-b", "s1") == []
    assert bridge.end_session(session_id) is None  # closing twice is a no-op


def test_voice_outage_continues_the_same_call_in_text_mode():
    bridge, backend, _, ledger, _ = make()
    bridge._signed_url = lambda language: (_ for _ in ()).throw(OSError("elevenlabs down"))
    status, body = bridge.open_session(request())
    assert status == 200 and body["mode"] == "text" and "signed_url" not in body
    assert "voice unavailable" in body["voice_error"] and ledger.status["callreq-1"] == "dialing"
    assert bridge.text_turn(body["session_id"], "Hello?")[1]["reply"].endswith("Did your son Wei make it on Tuesday?")
    assert "voice_unavailable_text_fallback" in [event["action"] for event in backend.system_events]


def test_sse_stream_shape():
    lines = sse_chunks(__import__("calls.agent", fromlist=["Turn"]).Turn("Bye.", end=True))
    assert all(line.startswith("data: ") and line.endswith("\n\n") for line in lines)
    assert lines[-1] == "data: [DONE]\n\n"
    assert json.loads(lines[1][6:])["choices"][0]["delta"]["tool_calls"][0]["function"]["name"] == "end_call"


def test_turns_resolve_through_the_extra_body_session_id():
    bridge, _, _, _, _ = make()
    lines = []
    bridge._log = lines.append
    session_id = bridge.open_session(request())[1]["session_id"]
    turn(bridge, "Hello?", session_id)
    turn(bridge, "Hello again?")  # no extra body: only the single-session fallback can match
    turns = [line for line in lines if line.startswith("turn ")]
    assert turns[0].endswith("via=extra_body emergency=False end=False")
    assert "via=single_session_fallback" in turns[1]


def test_speech_after_an_emergency_close_repeats_the_fixed_line_and_ends_again():
    """Live bug: talking after end_call sent new turns; an empty reply made ElevenLabs fail the call."""
    bridge, backend, llm, ledger, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    turn(bridge, "I fell", session_id)
    status, text, ended = turn(bridge, "Hello? Are you still there?", session_id)
    assert status == 200 and text == emergency_line("en") and ended
    assert llm.calls == [] and len(backend.escalations) == 1 and ledger.status["callreq-1"] == "done"


def test_speech_after_a_normal_close_repeats_the_full_closing_and_ends_again():
    bridge, backend, llm, _, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    turn(bridge, "Hello?", session_id)
    bridge.end_session(session_id)  # call closed (end_call / browser hang-up)
    calls_before, events_before = len(llm.calls), dict(backend.events)
    status, text, ended = turn(bridge, "What was that?", session_id)
    assert status == 200 and text == CLOSING and ended
    assert len(llm.calls) == calls_before and backend.events == events_before


def test_tool_result_follow_up_mid_call_does_not_repeat_the_question():
    bridge, _, llm, _, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    turn(bridge, "Hello?", session_id)
    body = {"messages": [{"role": "user", "content": "Hello?"}, {"role": "tool", "content": "ok"}],
            "elevenlabs_extra_body": {"relay_session_id": session_id}}
    status, payload = bridge.chat_completion(body, AUTH)
    assert status == 200 and len(llm.calls) == 1 and "didn't catch that" in "".join(payload)


def test_filler_streams_before_the_model_is_called():
    bridge, _, llm, _, _ = make()
    session_id = bridge.open_session(request())[1]["session_id"]
    status, stream = bridge.chat_completion(
        {"messages": [{"role": "user", "content": "Hello?"}],
         "elevenlabs_extra_body": {"relay_session_id": session_id}}, AUTH)
    first = json.loads(next(iter(stream))[6:])
    assert status == 200 and first["choices"][0]["delta"]["content"] == FILLER
    assert llm.calls == []  # the resident hears "Okay..." before the model has been asked
    rest = list(stream)
    assert len(llm.calls) == 1 and rest[-1] == "data: [DONE]\n\n"
