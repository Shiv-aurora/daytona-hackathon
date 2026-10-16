"""Offline call transport, responder, backend and ledger for tests and simulated calls."""

from __future__ import annotations


class FakeTransport:
    """Scripted resident: `replies` are what the resident says, in order."""

    def __init__(self, replies: list[str], answers: bool = True):
        self.replies, self.answers = list(replies), answers
        self.dialed: list[str] = []
        self.said: list[str] = []
        self.hung_up = False

    def dial(self, household_id: str) -> bool:
        self.dialed.append(household_id)
        return self.answers

    def say(self, text: str) -> None:
        self.said.append(text)

    def listen(self) -> str | None:
        return self.replies.pop(0) if self.replies else None

    def hang_up(self) -> None:
        self.hung_up = True


class SpyResponder:
    """Records every utterance the "LLM" was shown."""

    def __init__(self, reply: str = "Thank you. Did your son make it on Tuesday?"):
        self._reply = reply
        self.seen: list[str] = []

    def reply(self, context: dict, transcript: list[dict]) -> str:
        self.seen.append(transcript[-1]["text"])
        return self._reply


class InMemoryBackend:
    """Implements interfaces.CallBackend with W2's semantics: run-scoped reads, insert-once writes."""

    def __init__(self, registry: dict | None = None, households: dict | None = None):
        self.registry = dict(registry or {})  # household_id -> registry entry
        self.households = dict(households or {})  # (run_id, household_id) -> context
        self.events: dict[str, dict] = {}
        self.escalations: dict[str, dict] = {}
        self.system_events: list[dict] = []

    def registry_entry(self, household_id: str) -> dict | None:
        return self.registry.get(household_id)

    def household_context(self, run_id: str, household_id: str) -> dict:
        return self.households.get((run_id, household_id), {})

    def write_event(self, event: dict) -> bool:
        return self.events.setdefault(event["_id"], event) is event

    def escalate(self, proposal: dict) -> bool:
        return self.escalations.setdefault(proposal["_id"], proposal) is proposal

    def system_event(self, event: dict) -> None:
        self.system_events.append(event)

    def events_visible_to(self, run_id: str, scenario_id: str) -> list[dict]:
        from interfaces import event_visible_to_run

        return [event for event in self.events.values() if event_visible_to_run(event, run_id, scenario_id)]


class InMemoryLedger:
    """CallLedger with W2's `call_requests` semantics: queued -> dialing -> done.

    Only explicitly queued requests can be claimed, exactly like W2's queue.
    """

    def __init__(self) -> None:
        self.status: dict[str, str] = {}
        self.results: dict[str, dict] = {}

    def queue(self, request: dict) -> bool:
        """Stand-in for W1 -> W2 `schedule_call`: insert-once as `queued`."""
        return self.status.setdefault(request["_id"], "queued") == "queued"

    def claim(self, request: dict, ts: float) -> bool:
        if self.status.get(request["_id"]) != "queued":
            return False
        self.status[request["_id"]] = "dialing"
        return True

    def finish(self, request: dict, result: dict) -> None:
        if self.status.get(request["_id"]) == "dialing":
            self.status[request["_id"]] = "done"
            self.results[request["_id"]] = result

    def result(self, request_id: str) -> dict | None:
        return self.results.get(request_id)
