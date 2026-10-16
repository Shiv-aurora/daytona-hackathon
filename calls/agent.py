"""Call agent core: opt-in gate, fixed disclosure, safety-first turns, replay-safe dialing.

A `CallSession` is one claimed call attempt. The offline loop (`CallAgent.start`, used by CI and
simulated calls) and the live ElevenLabs voice bridge both drive the same session, so opt-in,
the disclosure and the emergency path cannot differ between them.

Storage is injected: `interfaces.CallBackend` for events, proposals and traces, and a
`CallLedger` (implemented by W2 over `call_requests`) that claims each request exactly once.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from calls.questions import build_questions
from calls.safety import DEFAULT_LANGUAGE, disclosure, emergency_line, safety_check
from interfaces import CallBackend
from schemas import CallRequest, CallResult, Event, Proposal

OUTCOMES = frozenset({"completed", "no_answer", "emergency_escalated", "refused_no_opt_in", "failed"})
# The only household fields the voice model may see, and the only keys kept inside each list item.
CONTEXT_FIELDS = ("first_name", "language", "open_promises", "recent_calls", "outage_status", "recovery_status")
PROMISE_FIELDS = ("text", "made_ts", "due_ts")
CALL_FIELDS = ("ts", "outcome", "answered")
MAX_RESULT_TEXT = 4000
MAX_REPLY_CHARS = 400


class Transport(Protocol):
    def dial(self, household_id: str) -> bool: ...
    def say(self, text: str) -> None: ...
    def listen(self) -> str | None: ...  # None means the resident hung up or went silent
    def hang_up(self) -> None: ...


@dataclass(frozen=True)
class Reply:
    text: str
    end: bool = False


class Responder(Protocol):
    """The model side. It only ever sees utterances that already passed `safety_check`."""

    def reply(self, context: dict, transcript: list[dict]) -> Reply | str: ...


class CallLedger(Protocol):
    """One real call attempt per CallRequest `_id`. W2 implements this over `call_requests`:

    - `claim`: atomic compare-and-set `queued -> dialing`. False unless the request was explicitly
      queued (W1 -> `schedule_call`) and not yet claimed, so an unknown request can never be placed.
    - `finish`: `dialing -> done`, storing the CallResult so a replay can return it.
    - `result`: the stored CallResult, or None if the request was never finished.

    A crash mid-call, or an emergency whose human escalation failed to persist, leaves the request
    in `dialing` for manual attention: it is never dialed again automatically.
    """

    def claim(self, request: CallRequest, ts: float) -> bool: ...
    def finish(self, request: CallRequest, result: CallResult) -> None: ...
    def result(self, request_id: str) -> CallResult | None: ...


@dataclass(frozen=True)
class Turn:
    text: str
    end: bool = False
    emergency: bool = False


def result_event_id(call_id: str) -> str:
    return f"{call_id}:result"


def _pick(item: object, fields: tuple[str, ...]) -> object:
    if isinstance(item, dict):
        return {key: item[key] for key in fields if key in item}
    return str(item)


class CallTools:
    """Tools exposed to the voice model, bound to one call request.

    The model cannot pick a different household or run: those come from the request.
    """

    def __init__(self, backend: CallBackend, request: CallRequest):
        self._backend, self._request = backend, request

    def get_household_context(self) -> dict:
        raw = self._backend.household_context(self._request["run_id"], self._request["household_id"]) or {}
        context = {key: raw[key] for key in CONTEXT_FIELDS if key in raw}
        if "open_promises" in context:
            context["open_promises"] = [_pick(item, PROMISE_FIELDS) for item in context["open_promises"]]
        if "recent_calls" in context:
            context["recent_calls"] = [_pick(item, CALL_FIELDS) for item in context["recent_calls"]]
        return context

    def log_call_result(self, outcome: str, transcript: list[dict],
                        emergency_phrase: str | None = None) -> CallResult:
        """Write the result as a run-scoped `call_result` event the runtime reads next tick."""
        result = self.result_for(outcome, transcript)
        request = self._request
        event: Event = {
            "_id": result_event_id(request["_id"]),
            "run_id": request["run_id"],
            "scenario_id": request["scenario_id"],
            "household_id": request["household_id"],
            "ts": request["requested_ts"],
            "source": "call_result",
            "text": result["text"],
        }
        self._backend.write_event({**event, "call_id": request["_id"], "outcome": outcome,
                                   "answered": result["answered"], "emergency_phrase": emergency_phrase,
                                   "transcript": transcript})
        return result

    def result_for(self, outcome: str, transcript: list[dict]) -> CallResult:
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown call outcome: {outcome!r}")
        request = self._request
        text = "\n".join(f"{turn['speaker']}: {turn['text']}" for turn in transcript)[:MAX_RESULT_TEXT]
        return {"run_id": request["run_id"], "household_id": request["household_id"], "outcome": outcome,
                "scenario_id": request["scenario_id"], "call_id": request["_id"], "ts": request["requested_ts"],
                "answered": outcome not in ("no_answer", "refused_no_opt_in"), "text": text}


class CallSession:
    """One claimed call attempt. Every resident turn is safety-checked before the responder."""

    def __init__(self, agent: CallAgent, request: CallRequest, language: str):
        self.agent, self.request, self.language = agent, request, language
        self.tools = CallTools(agent.backend, request)
        self.disclosure = disclosure(language, agent.callback_number)  # code-owned, never model text
        self.transcript: list[dict] = [{"speaker": "relay", "text": self.disclosure}]
        self.context: dict | None = None
        self.escalated = False
        self.escalation_persisted = False
        self.emergency_phrase: str | None = None
        self.result: CallResult | None = None

    def hear(self, utterance: str) -> Turn:
        if self.result is not None:
            raise RuntimeError("call session is already closed")
        self.transcript.append({"speaker": "resident", "text": utterance})
        verdict = safety_check(utterance, self.language)
        if verdict["emergency"]:
            return self._emergency(utterance, verdict.get("reason"))
        if self.context is None:
            self.context = self.tools.get_household_context()
            self.context["language"] = self.language  # the call's language, from the registry
            self.context["questions"] = build_questions(self.context, self.language)
        reply = self.agent.responder.reply(self.context, list(self.transcript))
        reply = reply if isinstance(reply, Reply) else Reply(str(reply))
        text = reply.text.strip()[:MAX_REPLY_CHARS] or "Thank you."
        self.transcript.append({"speaker": "relay", "text": text})
        return Turn(text, end=reply.end)

    def _emergency(self, utterance: str, phrase: str | None) -> Turn:
        # The human escalation is the critical side effect, so it is written before anything is
        # spoken or logged, and retried once if the first write fails.
        self.escalated, self.emergency_phrase = True, phrase
        request = self.request
        proposal: Proposal = {
            "_id": f"{request['_id']}:emergency",
            "run_id": request["run_id"],
            "scenario_id": request["scenario_id"],
            "household_id": request["household_id"],
            "kind": "emergency",
            "status": "pending",
            "reason": "emergency_phrase",
            "ts": request["requested_ts"],
            "cited_event_ids": [],  # call-result evidence is attached during later integration
            "queue": "urgent_human",
            "urgent": True,
        }
        doc = {**proposal, "matched_phrase": phrase, "utterance": utterance, "call_id": request["_id"]}
        for attempt in (1, 2):
            try:
                self.agent.backend.escalate(doc)  # False = insert-once found it already written
                self.escalation_persisted = True
                break
            except Exception as exc:  # noqa: BLE001 - retry once, then record the failure loudly
                self.agent.trace(request, f"escalation_write_failed_{attempt}", error=type(exc).__name__)
        if self.escalation_persisted:
            self.agent.trace(request, "emergency_escalated", matched_phrase=phrase)
        else:
            self.agent.trace(request, "emergency_escalation_persist_failed", matched_phrase=phrase,
                             utterance=utterance)
        line = emergency_line(self.language)
        self.transcript.append({"speaker": "relay", "text": line})
        return Turn(line, end=True, emergency=True)

    def close(self, outcome: str) -> CallResult:
        """Log the result once. A failed write never hides an escalation or reopens the call."""
        if self.result is not None:
            return self.result
        if self.escalated:
            outcome = "emergency_escalated"
        try:
            result = self.tools.log_call_result(outcome, self.transcript, self.emergency_phrase)
        except Exception as exc:  # noqa: BLE001 - the call still ends; the trace records the gap
            self.agent.trace(self.request, "result_write_failed", error=type(exc).__name__)
            result = self.tools.result_for(outcome, self.transcript)
        if self.escalated and not self.escalation_persisted:
            # No durable human Proposal: keep the request in "dialing" for manual attention.
            self.agent.trace(self.request, "ledger_left_dialing_escalation_missing")
        else:
            try:
                self.agent.ledger.finish(self.request, result)
            except Exception as exc:  # noqa: BLE001 - request stays "dialing": recoverable, never redialed
                self.agent.trace(self.request, "ledger_finish_failed", error=type(exc).__name__)
        self.agent.trace(self.request, "call_result_logged", outcome=result["outcome"],
                         event_id=result_event_id(self.request["_id"]))
        self.result = result
        return result


class CallAgent:
    def __init__(self, backend: CallBackend, transport: Transport, responder: Responder,
                 callback_number: str, ledger: CallLedger, max_turns: int = 12):
        self.backend, self.transport, self.responder = backend, transport, responder
        self.callback_number, self.ledger, self.max_turns = callback_number, ledger, max_turns

    def open(self, request: CallRequest) -> CallSession | CallResult:
        """Validate, claim, then re-check opt-in. Nothing external happens before this returns.

        Returns an open session, or a CallResult when the call must not be placed:
        - the request is unknown/unqueued or already claimed: the stored result, if any;
        - the household is no longer opted in: claimed and finished as `refused_no_opt_in`,
          so it is terminal rather than left queued, and a replay returns that result.
        """
        scenario_id = request.get("scenario_id")
        if not isinstance(scenario_id, str) or not scenario_id.strip():
            raise ValueError("call request needs a non-empty scenario_id before dialing")
        tools = CallTools(self.backend, request)
        entry = self.backend.registry_entry(request["household_id"]) or {}
        language = entry.get("language") or DEFAULT_LANGUAGE
        disclosure(language, self.callback_number)  # a config error must not consume the request
        if not self.ledger.claim(request, request["requested_ts"]):
            self.trace(request, "call_not_placed")
            stored = self.ledger.result(request["_id"])
            return stored if stored is not None else {
                **tools.result_for("failed", []), "answered": False,
                "text": "not placed: request is not queued, or an earlier attempt is unfinished"}
        if entry.get("opt_in") is not True:
            refused = tools.result_for("refused_no_opt_in", [])
            self.ledger.finish(request, refused)
            self.trace(request, "call_refused_no_opt_in")
            return refused
        self.trace(request, "call_started", language=language)
        return CallSession(self, request, language)

    def start(self, request: CallRequest) -> CallResult:
        """Offline loop over a Transport (CI, simulated residents). Dials at most once per request."""
        opened = self.open(request)
        if not isinstance(opened, CallSession):
            return opened
        session = opened
        try:
            if not self.transport.dial(request["household_id"]):
                return session.close("no_answer")
        except Exception as exc:  # noqa: BLE001 - a dial error is a logged failure, never a retry
            self.trace(request, "dial_failed", error=type(exc).__name__)
            return session.close("failed")
        outcome = "completed"
        try:
            self.transport.say(session.disclosure)
            for _ in range(self.max_turns):
                heard = self.transport.listen()
                if heard is None:
                    break
                turn = session.hear(heard)
                self.transport.say(turn.text)
                if turn.end:
                    break
        except Exception as exc:  # noqa: BLE001 - any model/transport failure ends as a logged call
            self.trace(request, "call_failed", error=type(exc).__name__)
            outcome = "failed"
        finally:
            try:
                self.transport.hang_up()
            except Exception as exc:  # noqa: BLE001 - hanging up must not mask the result
                self.trace(request, "hang_up_failed", error=type(exc).__name__)
        return session.close(outcome)

    def trace(self, request: CallRequest, action: str, **detail) -> None:
        """Best-effort system_event with a deterministic id, so replays dedupe in W2."""
        try:
            self.backend.system_event({"_id": f"{request['_id']}:{action}", "run_id": request["run_id"],
                                       "module": "calls", "action": action, "ts": request["requested_ts"],
                                       "household_id": request["household_id"], "call_id": request["_id"],
                                       **detail})
        except Exception:  # noqa: BLE001, S110 - tracing is never allowed to break a call
            pass
