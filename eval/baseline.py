"""W4-C2 plain long-context baseline: one LLM reading the whole visible event log, no memory store.

It is what Relay is compared against, so it gets Relay's inputs, model client, identity resolution
and output format, and nothing in it is tuned to make it lose:
- it reads events only through `MemoryPort.events_after` under its own run_id (this scenario's
  inputs plus its own output, never another run's), and checks every event again here;
- it knows households only by the visible hints on each event (`household_ref_raw`, `address_raw`),
  never by hidden household ids. It names a household by those hints and `MemoryPort.match_household`
  resolves them, exactly as for Relay; an unresolved or ambiguous identity produces no proposal;
- it calls the model through W1's `runtime.llm.LLMClient`, so it can share Relay's model id, client
  and `CachedLLM` cache;
- it writes `schemas.Proposal` documents through `MemoryPort.insert_proposal` and answers the
  evaluator's probes as `schemas.PromiseProbe`.

How often it decides is a required argument, never a default; the comparison records it next to
Relay's tick. Nothing is dropped from the prompt unless `max_context_chars` is set, and every drop,
unresolved identity and model call is traced as a system_event.
"""

from __future__ import annotations

import hashlib
import json
import math

from interfaces import MemoryPort, event_visible_to_run
from runtime.llm import LLMClient
from schemas import SCENARIO_RUN_ID

MODULE = "baseline"
PROPOSAL_KIND = "escalation"
BATCH_SIZE = 200
MAX_REASON = 500
DECIDE_MAX_TOKENS = 2000
PROBE_MAX_TOKENS = 1000
_RULES = "Reply with JSON only. Never give medical advice. Never compare or rank households."

DECIDE_SYSTEM = (
    "You help a community response team during a long-running emergency. You get the full event log so far: "
    "visit notes, service reports, call results and other records, each with an id, a time in hours since day 0 "
    "and, when the record gives them, the resident's name and address. Raise an escalation for a household when "
    "the log shows it needs a person to follow up now: for example a promise to the household that was not kept "
    "by its deadline, a household that has gone silent, or a risk that only shows when reports from different "
    "services are read together. Do not escalate a problem the log shows is already resolved. Cite the ids of "
    f"the events that support each escalation. {_RULES}"
)
PROBE_SYSTEM = (
    "You help a community response team. From the event log, list the promises that are still open for each "
    "household asked about: promises made to or about the household that have not been kept and are not yet past "
    "their deadline. Name each promise by the id of the event where it was made. Use an empty list for a household "
    f"with no open promises. {_RULES}"
)


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def identity_hint(name: object, address: object) -> dict[str, str]:
    """The `MemoryPort.match_household` hint: only the parts actually given."""
    hint = {"name": name, "address": address}
    return {key: " ".join(value.split()) for key, value in hint.items() if isinstance(value, str) and value.strip()}


def describe(hint: dict[str, str]) -> str:
    return ", ".join(hint[key] for key in ("name", "address") if key in hint) or "(no name or address on file)"


def render_event(event: dict) -> str:
    """One log line: what any reader of the record can see. Hidden truth never reaches the event."""
    parts = [f"[{event['_id']}] h{event['ts']:g} source={event.get('source', '-')}"]
    parts += [f"{label}={event[key]}" for label, key in (("name", "household_ref_raw"), ("address", "address_raw"))
              if event.get(key)]
    return " ".join(parts) + ": " + " ".join(str(event.get("text", "")).split())


def parse_json_object(reply: str) -> dict | None:
    """The outermost {...} in a model reply, or None when there is no valid JSON object."""
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


class LongContextBaseline:
    def __init__(self, memory: MemoryPort, llm: LLMClient, run_id: str, scenario_id: str, *,
                 decision_every_hours: float, start_ts: float = 0.0, max_context_chars: int | None = None):
        if not run_id or run_id == SCENARIO_RUN_ID:
            raise ValueError("the baseline needs its own run_id, not the shared scenario")
        if not scenario_id:
            raise ValueError("scenario_id is required: the baseline reads that scenario's input events")
        if decision_every_hours <= 0:
            raise ValueError("decision_every_hours must be positive")
        self.memory, self.llm = memory, llm
        self.run_id, self.scenario_id = run_id, scenario_id
        self.decision_every_hours, self.max_context_chars = decision_every_hours, max_context_chars
        self.now = float(start_ts)
        self.log: list[dict] = []  # every event this run may see, read so far, in (ts, _id) order
        self.seen: set[str] = set()
        self.raised: list[dict] = []  # what it escalated and was resolved into a proposal
        self._cursor: tuple[float, str] | None = None

    @property
    def model(self) -> str:
        return self.llm.model

    def advance_to(self, ts: float) -> None:
        """Read events up to `ts`, deciding at every decision point on the way. Time only moves forward."""
        if ts < self.now:
            raise ValueError(f"the baseline is at hour {self.now:g} and cannot go back to {ts:g}")
        step = self.decision_every_hours
        decision = (math.floor(self.now / step) + 1) * step
        while decision <= ts:
            self._read_until(decision)
            self.now = decision
            self._decide()
            decision += step
        self._read_until(ts)
        self.now = ts

    def probe(self, ts: float, household_ids: list[str]) -> list[dict]:
        """The evaluator's memory probe: each household's open promises, named by source event.

        Each opaque household id is shown with the name and address this run has on file for it.
        """
        if ts != self.now:
            raise ValueError(f"probe at hour {ts:g}, but the baseline is at hour {self.now:g}")
        context, _ = self._context()
        asked = "\n".join(f"- {household_id}: {describe(self._on_file(household_id))}" for household_id in household_ids)
        prompt = (f"Current time: hour {ts:g}.\n\nEvent log, oldest first:\n{context}\n\n"
                  f"Households (answer under the id given):\n{asked}\n\n"
                  'JSON: {"open_promises": {"<household id>": ["<id of the event where the promise was made>"]}}')
        reply, usage = self._ask(PROBE_SYSTEM, prompt, PROBE_MAX_TOKENS)
        answers = reply.get("open_promises") if reply else None
        answers = answers if isinstance(answers, dict) else {}
        probes = [{"run_id": self.run_id, "probe_ts": ts, "household_id": household_id,
                   "source_event_ids": self._known_ids(answers.get(household_id))}
                  for household_id in household_ids]
        self._emit("baseline_probed", f"probe:{ts:g}", households=len(probes),
                   named=sum(len(probe["source_event_ids"]) for probe in probes), unparsable=reply is None, **usage)
        return probes

    def _read_until(self, ts: float) -> None:
        while True:
            batch = self.memory.events_after(self.run_id, self.scenario_id, self._cursor, ts, BATCH_SIZE)
            for event in batch:
                # The port promises isolation; the baseline still refuses anything it may not see.
                if not event_visible_to_run(event, self.run_id, self.scenario_id) or event["ts"] > ts:
                    raise RuntimeError(f"run isolation violated: event {event.get('_id')!r} is not visible to "
                                       f"run {self.run_id!r} at hour {ts:g}")
                self.log.append(event)
                self.seen.add(event["_id"])
                self._cursor = (event["ts"], event["_id"])
            if len(batch) < BATCH_SIZE:
                return

    def _context(self) -> tuple[str, int]:
        """The log as prompt text and how many of the oldest events a context limit dropped."""
        lines = [render_event(event) for event in self.log]
        first = 0
        if self.max_context_chars is not None:  # keep the newest events that fit
            first, size = len(lines), 0
            while first > 0 and size + len(lines[first - 1]) + 1 <= self.max_context_chars:
                first -= 1
                size += len(lines[first]) + 1
        return "\n".join(lines[first:]) or "(no events yet)", first

    def _ask(self, system: str, prompt: str, max_tokens: int) -> tuple[dict | None, dict]:
        response = self.llm.complete([{"role": "system", "content": system}, {"role": "user", "content": prompt}],
                                     max_tokens)
        usage = {"model": response.model, "prompt_tokens": response.prompt_tokens,
                 "completion_tokens": response.completion_tokens, "cost_usd": response.cost_usd,
                 "cached": response.cached}
        return parse_json_object(response.text), usage

    def _decide(self) -> None:
        context, dropped = self._context()
        raised = "\n".join(f"- {describe(r['hint'])} at hour {r['ts']:g}, citing {', '.join(r['cited'])}"
                           for r in self.raised) or "(none)"
        prompt = (f"Current time: hour {self.now:g}.\n\nEvent log, oldest first:\n{context}\n\n"
                  f"Escalations you already raised (do not repeat them):\n{raised}\n\n"
                  "Name each household by the name and address exactly as the log gives them. "
                  'JSON: {"escalations": [{"name": str, "address": str, "cited_event_ids": [str], "reason": str}]}')
        reply, usage = self._ask(DECIDE_SYSTEM, prompt, DECIDE_MAX_TOKENS)
        items = reply.get("escalations") if reply else None
        outcomes = [self._raise(item) for item in items] if isinstance(items, list) else []
        self._emit("baseline_decided", f"decide:{self.now:g}", events_in_context=len(self.log) - dropped,
                   events_dropped=dropped, proposals_created=outcomes.count("created"),
                   unresolved=outcomes.count("unresolved"), unparsable=not isinstance(items, list), **usage)

    def _raise(self, item: object) -> str:
        """Resolve one escalation to a household and write it; 'created', 'duplicate', 'unresolved' or 'invalid'."""
        if not isinstance(item, dict):
            return "invalid"
        hint, cited = identity_hint(item.get("name"), item.get("address")), self._known_ids(item.get("cited_event_ids"))
        household_id = self.memory.match_household(self.run_id, hint) if hint else None
        if household_id is None:  # unknown or ambiguous: never guessed
            self._emit("identity_unresolved", f"{self.now:g}|{describe(hint)}", hint=hint, cited_event_ids=cited)
            return "unresolved"
        proposal = {"_id": stable_id("proposal", self.run_id, household_id, *cited), "run_id": self.run_id,
                    "scenario_id": self.scenario_id, "household_id": household_id, "kind": PROPOSAL_KIND,
                    "status": "pending", "reason": str(item.get("reason") or "")[:MAX_REASON], "ts": self.now,
                    "cited_event_ids": cited}
        if not self.memory.insert_proposal(proposal):
            return "duplicate"
        self.raised.append({"hint": hint, "ts": self.now, "cited": cited})
        self._emit("proposal_created", proposal["_id"], proposal_id=proposal["_id"], household_id=household_id,
                   hint=hint)
        return "created"

    def _on_file(self, household_id: str) -> dict[str, str]:
        household = self.memory.household(self.run_id, household_id) or {}
        return identity_hint(household.get("name"), household.get("address"))

    def _known_ids(self, ids: object) -> list[str]:
        """Event ids the run has actually read; a guessed or invented id is evidence of nothing."""
        return sorted({i for i in ids if isinstance(i, str) and i in self.seen}) if isinstance(ids, list) else []

    def _emit(self, action: str, subject: str, **detail) -> None:
        self.memory.system_event({"_id": stable_id("sev", self.run_id, MODULE, action, subject),
                                  "run_id": self.run_id, "module": MODULE, "action": action, "ts": self.now,
                                  **detail})
