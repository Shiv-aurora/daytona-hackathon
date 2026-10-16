"""The call bridge: one session per claimed CallRequest, spoken through ElevenLabs or typed.

Voice mode: ElevenLabs speaks the agent's fixed `first_message` (our code-owned disclosure, set by
`calls.voice.setup_agent` per language) and sends each resident turn to `POST /v1/chat/completions`
(ElevenLabs Custom LLM). Text mode (the demo fallback): the page sends typed turns to `text_turn`
and speaks the replies with the browser's own voice. Both answer from `CallSession.hear`, so
`safety_check` runs before any model sees the words, and an emergency returns the fixed 911 line.
If ElevenLabs is unavailable the same claimed call continues in text mode instead of failing.
Network calls (the signed URL) are injected, so CI never needs a key.
"""

from __future__ import annotations

import hmac
import json
import secrets
import threading
from collections.abc import Callable, Iterator

from calls.agent import CallAgent, CallSession, Turn
from calls.responders import CLOSINGS, line_for
from calls.safety import emergency_line, safety_check
from schemas import CallRequest, CallResult

SESSION_KEY = "relay_session_id"
MODEL_NAME = "relay-call-agent"
# Fixed bridge lines per language (reviewed translations, never model output).
FAILURE_LINES = {"en": "I'm sorry, I'm having trouble on my end. A person from the recovery team will follow up.",
                 "zh": "抱歉，我这边出了点问题。恢复团队的工作人员会跟进。"}
NOT_CAUGHT_LINES = {"en": "Sorry, I didn't catch that. Could you say that again?",
                    "zh": "抱歉，我没听清楚，您能再说一遍吗？"}
ARE_YOU_THERE_LINES = {"en": "Hello, are you there?", "zh": "您好，您还在吗？"}
# Spoken at once while the model thinks (ElevenLabs' "buffer words"), only after the safety check
# has cleared the utterance. The trailing "... " keeps the speech natural.
FILLERS = {"en": "Okay... ", "zh": "好的…… "}
FILLER, FAILURE_LINE, NOT_CAUGHT_LINE = FILLERS["en"], FAILURE_LINES["en"], NOT_CAUGHT_LINES["en"]


def _chunk(delta: dict, finish: str | None = None, model: str = MODEL_NAME) -> str:
    body = {"id": "chatcmpl-relay", "object": "chat.completion.chunk", "created": 0, "model": model,
            "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}
    return f"data: {json.dumps(body)}\n\n"


def sse_chunks(turn: Turn, with_role: bool = True) -> list[str]:
    """An OpenAI chat.completion.chunk stream: the reply, then `end_call` if the call should end."""
    delta = {"role": "assistant", "content": turn.text} if with_role else {"content": turn.text}
    lines = [_chunk(delta)]
    if turn.end:
        reason = "emergency: human escalation created" if turn.emergency else "follow-up complete"
        lines.append(_chunk({"tool_calls": [{"index": 0, "id": "call_end", "type": "function", "function": {
            "name": "end_call", "arguments": json.dumps({"reason": reason})}}]}))
    lines.append(_chunk({}, "tool_calls" if turn.end else "stop"))
    lines.append("data: [DONE]\n\n")
    return lines


def last_user_text(messages: list[dict]) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, list):  # OpenAI content parts
                content = " ".join(part.get("text", "") for part in content if isinstance(part, dict))
            return str(content or "").strip()
    return ""


def _turn_json(turn: Turn) -> dict:
    return {"reply": turn.text, "end": turn.end, "emergency": turn.emergency}


class VoiceBridge:
    def __init__(self, agent: CallAgent, llm_secret: str, signed_url: Callable[[str], str],
                 log: Callable[[str], None] = lambda line: None):
        if not llm_secret:
            raise ValueError("RELAY_LLM_SECRET is required: the Custom LLM endpoint is public")
        self.agent, self._secret, self._signed_url, self._log = agent, llm_secret, signed_url, log
        self._sessions: dict[str, CallSession] = {}
        self._closed: dict[str, CallSession] = {}  # recently closed, to answer follow-ups politely
        self._lock = threading.Lock()

    def open_session(self, request: CallRequest, voice: bool = True) -> tuple[int, dict]:
        """Re-check opt-in and claim the request before any voice session exists.

        In voice mode a signed ElevenLabs URL for the call's language is attached. If ElevenLabs is
        unavailable, the same claimed call is returned in text mode (the demo fallback), never failed.
        """
        try:
            opened = self.agent.open(request)
        except (KeyError, TypeError, ValueError) as exc:
            return 400, {"error": str(exc)}
        if not isinstance(opened, CallSession):
            return 409, {"error": "call not placed", "result": opened}
        session_id = secrets.token_urlsafe(16)
        payload = {"session_id": session_id, "first_message": opened.disclosure, "language": opened.language,
                   "mode": "text"}
        if voice:
            try:
                payload.update(mode="voice", signed_url=self._signed_url(opened.language))
            except Exception as exc:  # noqa: BLE001 - fall back to text on the same claim
                payload["voice_error"] = f"voice unavailable: {type(exc).__name__}"
                self.agent.trace(opened.request, "voice_unavailable_text_fallback", error=type(exc).__name__)
        with self._lock:
            self._sessions[session_id] = opened
        self._log(f"session call={opened.request['_id']} mode={payload['mode']} language={opened.language}")
        return 200, payload

    def text_turn(self, session_id: str, text: str) -> tuple[int, dict]:
        """One typed resident turn (fallback mode). Same session, same safety check as voice."""
        with self._lock:
            session = self._sessions.get(session_id) or self._closed.get(session_id)
        if session is None:
            return 404, {"error": "no open call session"}
        if session.result is not None:
            return 200, _turn_json(self._after_close(session, "text"))
        text = (text or "").strip()
        if not text:
            return 200, _turn_json(Turn(line_for(NOT_CAUGHT_LINES, session.language)))
        return 200, _turn_json(self._turn(session_id, session, text, "text"))

    def chat_completion(self, body: dict, authorization: str) -> tuple[int, Iterator[str] | list[str] | dict]:
        """One resident turn from ElevenLabs. Answers only for an open session and the shared secret."""
        if not hmac.compare_digest(authorization or "", f"Bearer {self._secret}"):
            return 401, {"error": "unauthorized"}
        session_id, session, via = self._session_for(body)
        if session is None:
            return 404, {"error": "no open call session"}
        messages = body.get("messages") or []
        if session.result is not None:
            return 200, sse_chunks(self._after_close(session, via))
        if not messages or messages[-1].get("role") != "user":
            self._log(f"no-new-speech call={session.request['_id']} via={via}")
            return 200, sse_chunks(Turn(line_for(NOT_CAUGHT_LINES, session.language)))
        text = last_user_text(messages)
        if not text:
            return 200, sse_chunks(Turn(line_for(ARE_YOU_THERE_LINES, session.language)))
        if safety_check(text, session.language)["emergency"]:
            return 200, sse_chunks(self._turn(session_id, session, text, via))  # fixed line, no filler
        return 200, self._with_filler(session_id, session, text, via)

    def _with_filler(self, session_id: str, session: CallSession, text: str, via: str) -> Iterator[str]:
        """Stream the filler at once, then the model's reply, so ElevenLabs never waits in silence."""
        yield _chunk({"role": "assistant", "content": line_for(FILLERS, session.language)})
        yield from sse_chunks(self._turn(session_id, session, text, via), with_role=False)

    def _turn(self, session_id: str, session: CallSession, text: str, via: str) -> Turn:
        try:
            turn = session.hear(text)
        except Exception as exc:  # noqa: BLE001 - end politely; the result is logged as failed
            self.agent.trace(session.request, "voice_turn_failed", error=type(exc).__name__)
            self.end_session(session_id, "failed")
            return Turn(line_for(FAILURE_LINES, session.language), end=True)
        self._log(f"turn call={session.request['_id']} via={via} emergency={turn.emergency} end={turn.end}")
        if turn.end:
            self.end_session(session_id, "completed")
        return turn

    def _after_close(self, session: CallSession, via: str) -> Turn:
        # The resident (or room noise) talked over the last line while the call was ending. Repeat the
        # full fixed line and end again: the 911 line after an emergency, otherwise the closing.
        # No model, nothing re-logged.
        self._log(f"after-close call={session.request['_id']} via={via} repeat_emergency={session.escalated}")
        line = emergency_line(session.language) if session.escalated else line_for(CLOSINGS, session.language)
        return Turn(line, end=True, emergency=session.escalated)

    def end_session(self, session_id: str, outcome: str | None = None) -> CallResult | None:
        """Close once (browser disconnect, end_call, or failure). Returns the logged result.

        Without an explicit outcome the bridge decides from what it heard: a call where the resident
        never spoke is `no_answer`, so a failed or silent session never counts as contact.
        """
        with self._lock:
            session = self._sessions.pop(session_id, None)
            if session is not None:
                self._closed[session_id] = session
                while len(self._closed) > 100:
                    self._closed.pop(next(iter(self._closed)))
        if session is None:
            return None
        if outcome is None:
            spoke = any(turn["speaker"] == "resident" for turn in session.transcript)
            outcome = "completed" if spoke else "no_answer"
        return session.close(outcome)

    def _session_for(self, body: dict) -> tuple[str | None, CallSession | None, str]:
        extra = body.get("elevenlabs_extra_body") or {}
        with self._lock:
            if extra.get(SESSION_KEY) in self._sessions:
                return extra[SESSION_KEY], self._sessions[extra[SESSION_KEY]], "extra_body"
            if extra.get(SESSION_KEY) in self._closed:
                return extra[SESSION_KEY], self._closed[extra[SESSION_KEY]], "extra_body"
            if len(self._sessions) == 1:  # demo mode: one live call at a time
                return (*next(iter(self._sessions.items())), "single_session_fallback")
        return None, None, "none"
