"""W3-C3: text-mode demo fallback and Mandarin as the second language (all offline)."""

from calls.agent import CallAgent, result_event_id
from calls.fakes import FakeTransport, InMemoryBackend, InMemoryLedger
from calls.questions import build_questions, question_for
from calls.responders import CLOSINGS, ModelResponder, ScriptedResponder
from calls.safety import (
    DISCLOSURE_TEMPLATES,
    EMERGENCY_LINES,
    disclosure,
    emergency_line,
    safety_check,
)
from calls.voice.bridge import VoiceBridge
from calls.voice.server import demo_backend, demo_requests
from calls.voice.setup_agent import agent_config, agent_env_var, problems
from runtime.llm import LLMResponse

CALLBACK = "+1 212-555-0100"
PROMISE = {"text": "Her son Wei is coming Tuesday to help clean out the basement.", "due_ts": 150.0}


def request(request_id="callreq-1"):
    return {"_id": request_id, "run_id": "run-a", "scenario_id": "s1", "household_id": "hh-chen",
            "proposal_id": "prop-1", "purpose": "promise_check_in", "requested_ts": 504.0}


class SpyLLM:
    model = "spy"

    def __init__(self):
        self.calls = []

    def complete(self, messages, max_tokens):
        self.calls.append(messages)
        return LLMResponse(text="您的儿子Wei星期二来了吗？", model=self.model)


def make(language="en", responder=None):
    backend = InMemoryBackend(registry={"hh-chen": {"household_id": "hh-chen", "opt_in": True, "language": language}},
                              households={("run-a", "hh-chen"): {"first_name": "Mei", "open_promises": [PROMISE]}})
    ledger, opened = InMemoryLedger(), []
    ledger.queue(request())
    agent = CallAgent(backend, FakeTransport([]), responder or ScriptedResponder(), CALLBACK, ledger)

    def signed_url(lang):
        opened.append(lang)
        return "wss://example.invalid/signed"

    return VoiceBridge(agent, "secret", signed_url), backend, ledger, opened


# --- stable fallback: text mode on the same claimed call ---------------------------------------

def test_text_call_opens_no_voice_session_and_keeps_the_fixed_disclosure():
    bridge, _, ledger, opened = make()
    status, body = bridge.open_session(request(), voice=False)
    assert status == 200 and body["mode"] == "text" and opened == []
    assert body["first_message"] == disclosure("en", CALLBACK) and ledger.status["callreq-1"] == "dialing"


def test_text_call_asks_the_memory_question_and_logs_a_run_scoped_result():
    bridge, backend, ledger, _ = make()
    session_id = bridge.open_session(request(), voice=False)[1]["session_id"]
    first = bridge.text_turn(session_id, "Hello?")[1]
    assert first == {"reply": "Thank you for taking our call. Did your son Wei make it on Tuesday?",
                     "end": False, "emergency": False}
    last = bridge.text_turn(session_id, "No, he never came.")[1]
    assert last["end"] and last["reply"] == CLOSINGS["en"] and ledger.status["callreq-1"] == "done"
    event = backend.events[result_event_id("callreq-1")]
    assert event["run_id"] == "run-a" and event["outcome"] == "completed" and event["answered"]


def test_text_call_i_fell_is_the_fixed_line_without_the_model():
    llm = SpyLLM()
    bridge, backend, ledger, _ = make(responder=ModelResponder(llm))
    session_id = bridge.open_session(request(), voice=False)[1]["session_id"]
    reply = bridge.text_turn(session_id, "I fell")[1]
    assert reply == {"reply": emergency_line("en"), "end": True, "emergency": True}
    assert llm.calls == [] and len(backend.escalations) == 1 and ledger.status["callreq-1"] == "done"
    assert bridge.text_turn(session_id, "Hello?")[1]["reply"] == emergency_line("en")  # repeats, still no model
    assert llm.calls == []


def test_text_turn_for_an_unknown_session_is_refused():
    bridge, _, _, _ = make()
    assert bridge.text_turn("not-a-session", "Hello?")[0] == 404


def test_demo_requests_are_explicit_and_counted_after_env_load():
    requests = demo_requests(3)
    assert [r["_id"] for r in requests] == ["callreq-demo-1", "callreq-demo-2", "callreq-demo-3"]
    backend, ledger = demo_backend(requests, "zh")
    assert set(ledger.status.values()) == {"queued"} and len(ledger.status) == 3
    assert backend.registry_entry("hh-chen")["language"] == "zh"


# --- Mandarin as the second language -------------------------------------------------------------

def test_mandarin_disclosure_and_911_line_are_fixed_code_owned_text():
    assert disclosure("zh", CALLBACK) == DISCLOSURE_TEMPLATES["zh"].format(callback_number=CALLBACK)
    assert CALLBACK in disclosure("zh", CALLBACK) and "911" in EMERGENCY_LINES["zh"]
    assert safety_check("我摔倒了，起不来", "zh") == {"emergency": True, "reason": "摔倒"}


def test_mandarin_call_uses_the_mandarin_agent_disclosure_and_questions():
    bridge, _, _, opened = make(language="zh")
    status, body = bridge.open_session(request())
    assert status == 200 and opened == ["zh"] and body["language"] == "zh"
    assert body["first_message"] == disclosure("zh", CALLBACK)
    reply = bridge.text_turn(body["session_id"], "你好？")[1]["reply"]
    assert reply == "谢谢您接听我们的电话。您的儿子Wei星期二来了吗？"


def test_mandarin_i_fell_gets_the_mandarin_911_line():
    bridge, backend, _, _ = make(language="zh")
    session_id = bridge.open_session(request(), voice=False)[1]["session_id"]
    assert bridge.text_turn(session_id, "我摔倒了")[1]["reply"] == emergency_line("zh")
    assert len(backend.escalations) == 1


def test_mandarin_questions_are_deterministic():
    assert question_for(PROMISE["text"], "zh") == "您的儿子Wei星期二来了吗？"
    assert question_for("Neighbor promised to visit this weekend.", "zh") == "您的邻居这个周末来了吗？"
    assert build_questions({"open_promises": [PROMISE]}, "zh") == ["您的儿子Wei星期二来了吗？"]


def test_model_is_told_the_residents_language():
    llm = SpyLLM()
    bridge, _, _, _ = make(language="zh", responder=ModelResponder(llm))
    session_id = bridge.open_session(request(), voice=False)[1]["session_id"]
    bridge.text_turn(session_id, "你好？")
    assert '"language": "zh"' in llm.calls[0][1]["content"] and "Mandarin" in llm.calls[0][0]["content"]


def test_mandarin_agent_config_and_check():
    config = agent_config(CALLBACK, "relay.example", "secret-zh", "zh")
    agent = config["conversation_config"]["agent"]
    assert agent["first_message"] == disclosure("zh", CALLBACK) and agent["language"] == "zh"
    assert config["conversation_config"]["tts"]["model_id"] == "eleven_flash_v2_5"
    assert problems(config, CALLBACK, "zh") == []
    assert "first_message is not the code-owned disclosure" in problems(config, CALLBACK, "en")
    assert agent_env_var("zh") == "ELEVENLABS_AGENT_ID_ZH" and agent_env_var("en") == "ELEVENLABS_AGENT_ID"
