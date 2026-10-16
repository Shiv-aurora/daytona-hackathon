"""Simulated-time tick loop: event -> household -> promise -> proposal -> call request.

A tick advances the simulated clock (hours since day 0) by `tick_hours` and consumes the run's
visible events up to it in (ts, _id) order. Each event is matched to a household through the memory
port; for a matched household the emergency check runs before any model sees the text, then promises
are extracted by the OpenRouter path when a model is configured, or by the regex fallback. The
watcher turns each promise into one check-in proposal, early (within the policy's lead time) or when
it lapses. The goal has two halves, promises met in time and no opted-in household silent for more
than 72h, so every tick also raises one follow-up per silence episode; once a simulated day the goal
is scored, the policy may move within its bounds, and a bounded cross-service scan asks the model
about registered households with trouble reported by two or more services. Every write goes through
the ports and is insert-once or forward-only, so replaying a tick from its starting state (e.g. after
a crash before the checkpoint) changes nothing.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date, datetime

from interfaces import event_visible_to_run
from runtime.clock import SimClock
from runtime.extract import Extraction, address_key, extract, has_cue
from runtime.goals import goal_metrics
from runtime.llm import MODEL_ERRORS, LLMClient, LLMResponse, TokenLedger
from runtime.llm_paths import (
    MIN_RISK_SOURCES,
    decision_messages,
    extraction_messages,
    parse_decision,
    parse_extraction,
    parse_risk,
    risk_messages,
)
from runtime.policy import (
    DEFAULT_POLICY,
    REVIEW_EVERY_HOURS,
    build_policy_change,
    review,
    review_due,
)
from runtime.ports import (
    CallsPort,
    Cursor,
    LedgerPort,
    MemoryPort,
    RetrievalPort,
    SafetyCheck,
)
from runtime.promises import (
    CALLABLE_KINDS,
    PROPOSAL_KIND,
    SILENCE_KIND,
    build_call_request,
    build_escalation,
    build_lapse_escalation,
    build_promise,
    build_proposal,
    build_risk_proposal,
    build_silence_proposal,
    is_fulfilled_by,
    risk_proposal_id,
    stable_id,
)
from runtime.retrieval import retrieve
from runtime.silence import silent_households
from runtime.state import RuntimeState, assert_small_state

MODULE = "runtime"
MAX_CITED = 5
EVIDENCE_LIMIT = 8
MAX_RISK_CHECKS = 20  # model questions per daily cross-service scan
MAX_PENDING_IDS = 100  # newest ids kept in the checkpoint, so it stays small on a long run
CALL_DELAY_HOURS = 0.25  # a call happens after the tick that queued it, so its result sorts after the cursor
SERVICE_SOURCES = ("311", "crew", "utility")  # reports from services, independent of a volunteer's visit
# A later report that the household is still in trouble (or an unanswered call) escalates a lapsed promise.
TROUBLE = re.compile(
    r"\b(?:no one answered|nobody answered|not answering|no answer|did(?:n't| not) answer|not reconnected|"
    r"still (?:no|without|waiting|dark|flooded)|delayed|never came|did(?:n't| not) come|no power|no heat|"
    r"no electricity|not (?:yet )?(?:restored|fixed|repaired|reconnected))\b", re.IGNORECASE)


class TickFailed(RuntimeError):
    """A tick stopped part-way. Nothing was checkpointed, so replaying the same tick is safe."""

    def __init__(self, run_id: str, tick: int, now: float, step: str, error: Exception):
        super().__init__(f"run {run_id!r} tick {tick} (hour {now:g}) failed while {step}: "
                         f"{type(error).__name__}: {error}. The checkpoint was not advanced; replaying "
                         "this tick from it is safe.")
        self.run_id, self.tick, self.now, self.step = run_id, tick, now, step


class Runtime:
    def __init__(self, memory: MemoryPort, calls: CallsPort, day0: datetime | date | str, tick_hours: float = 1.0,
                 batch_size: int = 200, *, llm: LLMClient | None = None, safety: SafetyCheck | None = None,
                 ledger: LedgerPort | None = None, retrieval: RetrievalPort | None = None):
        """`day0` is the wall-clock start of simulated hour 0 (`RunMeta.day0`).

        C2 ports are optional: `llm` (OpenRouter, usually behind a `CachedLLM`) requires `safety`,
        because emergency handling runs before any model; `ledger` turns on goal tracking and the
        policy; `retrieval` supplies time-safe evidence for proposals.
        """
        if tick_hours <= 0 or batch_size <= 0:
            raise ValueError("tick_hours and batch_size must be positive")
        if llm is not None and safety is None:
            raise ValueError("a model path needs a safety check: emergency handling runs before the LLM")
        self.memory, self.calls, self.clock = memory, calls, SimClock(day0)
        self.tick_hours, self.batch_size = tick_hours, batch_size
        self.llm, self.safety, self.ledger, self.retrieval = llm, safety, ledger, retrieval
        self._policies: dict[tuple[str, int], dict] = {}

    def run(self, state: RuntimeState, until_ts: float,
            on_tick: Callable[[RuntimeState], None] | None = None) -> RuntimeState:
        """Tick until the clock reaches `until_ts`; `on_tick` is the checkpoint hook."""
        while state["now_ts"] < until_ts:
            state = self.tick(state)
            if on_tick is not None:
                on_tick(state)
        return state

    def tick(self, state: RuntimeState) -> RuntimeState:
        assert_small_state(state)
        run_id, scenario_id, tick = state["run_id"], state["scenario_id"], state["tick"] + 1
        if not scenario_id:
            raise ValueError("scenario_id is required: a run reads its scenario's input events")
        now = state["now_ts"] + self.tick_hours
        cursor: Cursor | None = None
        if state["cursor_ts"] is not None:
            cursor = (state["cursor_ts"], state["cursor_id"])
        step = "loading the policy"
        try:
            policy = self._policy(run_id, state["policy_version"])
            tokens = TokenLedger()
            self._emit(run_id, now, "tick_started", f"tick:{tick}", tick=tick)

            step, consumed = "reading events", 0
            while True:
                batch = self.memory.events_after(run_id, scenario_id, cursor, now, self.batch_size)
                for event in batch:
                    self._handle_event(run_id, scenario_id, event, tokens)
                    cursor = (event["ts"], event["_id"])
                consumed += len(batch)
                if len(batch) < self.batch_size:
                    break

            step = "watching promises"
            pending_docs = self.memory.proposals_with_status(run_id, "pending")
            open_items = _open_items(pending_docs)
            lapsed = self._watch_promises(run_id, scenario_id, now, policy, tokens, open_items)
            step = "watching silence"
            silent = self._watch_silence(run_id, scenario_id, now, open_items)
            if review_due(state["now_ts"], now):
                step = "scanning across services"
                self._scan_cross_service(run_id, scenario_id, now, tokens)
            step = "scheduling calls"
            call_ids, scheduled = self._schedule_calls(run_id, now)
            step = "reviewing the goal and policy"
            version = self._review_policy(run_id, state["policy_version"], state["now_ts"], now, policy, silent)
            self._account_tokens(run_id, tick, now, tokens)
            step = "closing the tick"
            pending = _newest_ids(self.memory.proposals_with_status(run_id, "pending"))
            self._emit(run_id, now, "tick_completed", f"tick:{tick}", tick=tick, events=consumed, lapsed=lapsed,
                       silent_households=silent, calls_scheduled=scheduled, policy_version=version)
        except TickFailed:
            raise
        except Exception as error:  # re-raised with where it failed; nothing was checkpointed
            raise TickFailed(run_id, tick, now, step, error) from error
        return RuntimeState(run_id=run_id, scenario_id=scenario_id, tick=tick, now_ts=now,
                            cursor_ts=cursor[0] if cursor else None, cursor_id=cursor[1] if cursor else None,
                            pending_proposal_ids=pending, pending_call_ids=call_ids[:MAX_PENDING_IDS],
                            policy_version=version)

    def _handle_event(self, run_id: str, scenario_id: str, event: dict, tokens: TokenLedger) -> None:
        # Visible: this scenario's inputs (run_id "scenario") and this run's own events. Nothing else.
        if not event_visible_to_run(event, run_id, scenario_id):
            raise RuntimeError(f"run isolation violated: event {event.get('_id')!r} is not visible to run "
                               f"{run_id!r} in scenario {scenario_id!r}")
        event_id, ts = event["_id"], event["ts"]
        # Call transcripts include Relay's own questions, so they are not mined for promises.
        text = "" if event.get("source") == "call_result" else str(event.get("text") or "")
        found = extract(text, ts, self.clock)
        hint = _identity_hint(event, found.household_ref)
        household_id = event.get("household_id") or (self.memory.match_household(run_id, hint) if hint else None)
        if not household_id:
            if "name" in hint:  # a person was named but is not on file; bare addresses are background
                self._emit(run_id, ts, "household_unmatched", event_id, event_id=event_id, ref=hint)
            return
        self.memory.apply_household_event(run_id, household_id, event)
        self._emit(run_id, ts, "household_matched", event_id, event_id=event_id, household_id=household_id)
        # Corroboration for a lapsed promise: an unanswered call, a report of trouble, or any new
        # report about the household from a service (311, crew, utility) rather than a visit.
        if event.get("answered") is False or TROUBLE.search(text) or event.get("source") in SERVICE_SOURCES:
            self._escalate_lapsed(run_id, household_id, event)
        if not text:
            return
        # Only for a known household (a background record is never a person-level alert), and always
        # before any model sees the text.
        emergency = self._check_emergency(run_id, scenario_id, event, text, household_id)

        # Only promises made before this event, as it found them: on a replay the event's own promises
        # already exist, and showing them would change the prompt (and the cached answer).
        open_promises = [promise for promise in self.memory.open_promises(run_id, household_id=household_id)
                         if (promise["made_ts"], promise["source_event_id"]) < (ts, event_id)]
        if self.llm is not None and not emergency and (open_promises or has_cue(text)):
            found = self._model_extract(run_id, event, text, open_promises, tokens) or found
        for promise in open_promises:
            if promise["_id"] in found.kept_promise_ids or is_fulfilled_by(promise, found.fulfilments):
                self._emit(run_id, ts, "promise_kept", promise["_id"], promise_id=promise["_id"],
                           household_id=household_id, event_id=event_id)
                self.memory.set_promise_status(run_id, promise["_id"], "kept", ts)
        for index, draft in enumerate(found.promises):
            promise = build_promise(run_id, household_id, event, index, draft)
            self.memory.insert_promise(promise)
            self._emit(run_id, ts, "promise_created", promise["_id"], promise_id=promise["_id"],
                       household_id=household_id, event_id=event_id, due_ts=promise["due_ts"])

    def _check_emergency(self, run_id: str, scenario_id: str, event: dict, text: str, household_id: str) -> bool:
        """Phrase check before any model: an emergency becomes an immediate urgent-human proposal."""
        if self.safety is None:
            return False
        verdict = self.safety(text)
        if not verdict.get("emergency"):
            return False
        escalation = build_escalation(run_id, scenario_id, event, household_id,
                                      str(verdict.get("reason") or "emergency"))
        self.memory.insert_proposal(escalation)
        self._emit(run_id, event["ts"], "emergency_escalated", escalation["_id"], proposal_id=escalation["_id"],
                   event_id=event["_id"], household_id=escalation["household_id"])
        return True

    def _model_extract(self, run_id: str, event: dict, text: str, open_promises: list[dict],
                       tokens: TokenLedger) -> Extraction | None:
        messages = extraction_messages(text, self.clock, event["ts"], open_promises)
        response = self._complete(run_id, event["ts"], "extract", event["_id"], messages, 700, tokens)
        if response is None:
            return None
        found = parse_extraction(response.text, event["ts"], self.clock, {p["_id"] for p in open_promises})
        if found is None:
            self._emit(run_id, event["ts"], "llm_output_rejected", f"extract:{event['_id']}", purpose="extract")
        return found

    def _escalate_lapsed(self, run_id: str, household_id: str, event: dict) -> None:
        """New trouble after a promise lapsed: escalate that promise to a person, once.

        If that escalation came from an unanswered call, the first later report from a service (311,
        crew, utility) is independent corroboration and escalates the promise once more, citing both.
        """
        for status in ("pending", "approved"):  # a dismissed check-in was a coordinator's call; respect it
            for check_in in self.memory.proposals_with_status(run_id, status):
                if (check_in["household_id"] != household_id or check_in.get("kind") != PROPOSAL_KIND
                        or not check_in.get("due_ts", event["ts"]) < event["ts"] or check_in["ts"] > event["ts"]):
                    continue
                source_id, *evidence = check_in["cited_event_ids"]  # the promise's own note comes first
                escalation = build_lapse_escalation(check_in, event, _cite(source_id, event["_id"], *evidence))
                created = self.memory.insert_proposal(escalation)
                later = None if created else self._corroborate(run_id, check_in, escalation["_id"], event)
                for proposal in (escalation, later):
                    if proposal is not None:  # the trace's deterministic _id makes a replay a no-op
                        self._emit(run_id, event["ts"], "promise_escalated", proposal["_id"],
                                   proposal_id=proposal["_id"], promise_id=check_in["promise_id"],
                                   household_id=household_id, event_id=event["_id"])

    def _corroborate(self, run_id: str, check_in: dict, escalation_id: str, event: dict) -> dict | None:
        """The one corroborated escalation, when an unanswered-call escalation is followed by a service report."""
        if event.get("source") not in SERVICE_SOURCES or self.ledger is None:
            return None
        earlier = next((p for p in self.ledger.run_proposals(run_id) if p["_id"] == escalation_id), None)
        if earlier is None or earlier.get("trigger_source") != "call_result" or not earlier["ts"] < event["ts"]:
            return None
        source_id, *evidence = check_in["cited_event_ids"]
        cited = _cite(source_id, earlier["trigger_event_id"], event["_id"], *evidence)
        corroborated = build_lapse_escalation(check_in, event, cited, corroborated=True)
        self.memory.insert_proposal(corroborated)  # insert-once: a promise is corroborated at most once
        return corroborated

    def _suppress(self, run_id: str, now: float, proposal_id: str, household_id: str, why: str) -> None:
        """Keep the console readable: record (once) that a proposal was held back, and why."""
        self._emit(run_id, now, "proposal_suppressed", proposal_id, proposal_id=proposal_id,
                   household_id=household_id, why=why)

    def _watch_promises(self, run_id: str, scenario_id: str, now: float, policy: dict,
                        tokens: TokenLedger, open_items: dict[str, set[str]]) -> int:
        """Check in on each open promise once: early within the policy's lead time, or at the lapse.

        An early check-in is speculative, so it waits while the household already has an open
        follow-up; the check-in at the lapse is never held back.
        """
        lead = policy["lead_hours"]
        proposed = {p["_id"] for p in self.ledger.run_proposals(run_id)} if self.ledger and lead else set()
        lapsed = 0
        for promise in self.memory.open_promises(run_id, due_before=now + lead):
            proposal = build_proposal(promise, now)
            household_id = promise["household_id"]
            if proposal["_id"] not in proposed and proposal["early"] and open_items.get(household_id):
                self._suppress(run_id, now, proposal["_id"], household_id, "household already has an open follow-up")
            elif proposal["_id"] not in proposed:
                proposal = self._decide(run_id, scenario_id, promise, proposal, now, tokens)
                # Proposal first, status flip last: a crash in between is healed by replaying the tick,
                # and the deterministic _id stops the replay from creating a second proposal.
                self.memory.insert_proposal(proposal)
                open_items.setdefault(household_id, set()).add(PROPOSAL_KIND)
                self._emit(run_id, now, "proposal_created", proposal["_id"], proposal_id=proposal["_id"],
                           promise_id=promise["_id"], household_id=household_id, early=proposal["early"])
            if promise["due_ts"] < now:
                self.memory.set_promise_status(run_id, promise["_id"], "lapsed", now)
                lapsed += 1
        return lapsed

    def _watch_silence(self, run_id: str, scenario_id: str, now: float, open_items: dict[str, set[str]]) -> int:
        """Goal, second half: one follow-up per silence episode past 72h, for opted-in households only.

        While an earlier silence follow-up for the household is still pending, a new episode adds
        nothing new for the coordinator, so it is recorded as suppressed rather than proposed again.
        """
        if self.ledger is None:
            return 0
        silent = silent_households(self.ledger.registry_entries(scenario_id),
                                   self.ledger.last_contact_by_household(run_id, scenario_id, now), now)
        proposed = {p["_id"] for p in self.ledger.run_proposals(run_id)} if silent else set()
        for household_id, since in sorted(silent.items()):
            proposal = build_silence_proposal(run_id, scenario_id, household_id, since, now, [])
            if proposal["_id"] in proposed:  # this episode already has its follow-up
                continue
            if SILENCE_KIND in open_items.get(household_id, ()):
                self._suppress(run_id, now, proposal["_id"], household_id, "an earlier silence alert is still open")
                continue
            proposal["cited_event_ids"] = self._own_evidence(run_id, scenario_id, household_id, now)
            self.memory.insert_proposal(proposal)
            open_items.setdefault(household_id, set()).add(SILENCE_KIND)
            self._emit(run_id, now, "silence_escalated", proposal["_id"], proposal_id=proposal["_id"],
                       household_id=household_id, silent_since=since)
        return len(silent)

    def _own_evidence(self, run_id: str, scenario_id: str, household_id: str, now: float) -> list[str]:
        """Time-safe citations for a silence alert: reports already tied to this household, plus the
        utility's status for its street (a silent resident on a dark block is the concern)."""
        household = self.memory.household(run_id, household_id) or {}
        entry = self.memory.registry_entry(household_id) or {}
        address = entry.get("address") or household.get("address")
        query = " ".join(str(part) for part in (entry.get("name") or household.get("name"), address) if part)
        evidence, leaked = retrieve(self.retrieval, run_id, scenario_id, query, now, EVIDENCE_LIMIT)
        if leaked:
            self._emit(run_id, now, "retrieval_filtered", f"silence:{household_id}:{now}", household_id=household_id,
                       dropped_event_ids=leaked)
        own = set(household.get("applied_event_ids") or [])
        street = (address_key(address) or "|").split("|")[1]
        same_street = re.compile(rf"\b{re.escape(street)}(?:st|nd|rd|th)?\b") if street else None
        block = str(address or "").split("-")[0] if re.match(r"\d+-\d+", str(address or "")) else None
        same_block = re.compile(rf"\b{block}-\d+ to {block}-\d+") if block else None  # "67-01 to 67-99"
        on_street = sorted((event for event in evidence if event.get("source") == "utility" and same_street
                            and same_street.search(str(event.get("text", "")).lower())),
                           key=lambda event: not (same_block and same_block.search(str(event.get("text", "")))))
        cited = [e["_id"] for e in evidence if e["_id"] in own] + [e["_id"] for e in on_street[:2]]
        return list(dict.fromkeys(cited))[:MAX_CITED]

    def _scan_cross_service(self, run_id: str, scenario_id: str, now: float, tokens: TokenLedger) -> int:
        """Daily and bounded: ask the model about registered households with trouble from 2+ services."""
        if self.llm is None or self.retrieval is None or self.ledger is None:
            return 0
        day = int(now // REVIEW_EVERY_HOURS)
        proposed = {p["_id"] for p in self.ledger.run_proposals(run_id)}
        # Known households: registered by now, or heard from by this run (unregistered: no opt-in, so no calls).
        known = {e["household_id"]: e for e in self.ledger.registry_entries(scenario_id)
                 if float(e.get("registered_ts") or 0.0) <= now}
        for household_id in self.ledger.last_contact_by_household(run_id, scenario_id, now):
            if household_id not in known:
                household = self.memory.household(run_id, household_id) or {}
                known[household_id] = {"household_id": household_id, "name": household.get("name"),
                                       "address": household.get("address")}
        entries = sorted(known.values(), key=lambda e: stable_id("scan", day, e["household_id"]))  # fair under the cap
        asked = created = 0
        for entry in entries:
            household_id = entry["household_id"]
            if asked >= MAX_RISK_CHECKS:
                break
            if risk_proposal_id(run_id, household_id) in proposed:
                continue
            query = " ".join(str(part) for part in (entry.get("name"), entry.get("address")) if part)
            evidence, leaked = retrieve(self.retrieval, run_id, scenario_id, query, now, EVIDENCE_LIMIT)
            if leaked:
                self._emit(run_id, now, "retrieval_filtered", f"risk:{household_id}:day:{day}",
                           household_id=household_id, dropped_event_ids=leaked)
            sources = {event["_id"]: str(event.get("source")) for event in evidence}
            if len(set(sources.values())) < MIN_RISK_SOURCES:
                continue  # one service's view is not a cross-service concern; the model is not asked
            asked += 1
            messages = risk_messages(entry, self.clock, now, evidence)
            response = self._complete(run_id, now, "risk", f"{household_id}:day:{day}", messages, 400, tokens)
            decision = parse_risk(response.text, sources) if response is not None else None
            if response is not None and decision is None:
                self._emit(run_id, now, "llm_output_rejected", f"risk:{household_id}:day:{day}", purpose="risk")
            if decision is None or not decision.follow_up:
                continue
            action = decision.suggested_action if entry.get("opt_in") is True else "visit"  # calls need opt-in
            proposal = build_risk_proposal(run_id, scenario_id, household_id, list(decision.cited_event_ids), action,
                                           decision.rationale, now)
            self.memory.insert_proposal(proposal)
            self._emit(run_id, now, "proposal_created", proposal["_id"], proposal_id=proposal["_id"],
                       household_id=household_id, kind=proposal["kind"])
            created += 1
        return created

    def _decide(self, run_id: str, scenario_id: str, promise: dict, proposal: dict, now: float,
                tokens: TokenLedger) -> dict:
        """Cite evidence the run could see by `now` and suggest call or visit (calls need opt-in)."""
        household = self.memory.household(run_id, promise["household_id"]) or {}
        query = " ".join(str(part) for part in (promise["text"], household.get("name"), household.get("address"))
                         if part)
        evidence, leaked = retrieve(self.retrieval, run_id, scenario_id, query, now, EVIDENCE_LIMIT)
        if leaked:
            self._emit(run_id, now, "retrieval_filtered", f"decide:{promise['_id']}", promise_id=promise["_id"],
                       dropped_event_ids=leaked)
        evidence = [event for event in evidence if event["_id"] != promise["source_event_id"]]
        decision = None
        if self.llm is not None and evidence:
            messages = decision_messages(promise, self.clock, now, evidence)
            response = self._complete(run_id, now, "decide", promise["_id"], messages, 400, tokens)
            if response is not None:
                decision = parse_decision(response.text, {event["_id"] for event in evidence})
                if decision is None:
                    self._emit(run_id, now, "llm_output_rejected", f"decide:{promise['_id']}", purpose="decide")
        if decision is not None:
            cited, action = list(decision.cited_event_ids), decision.suggested_action
        else:  # deterministic: only evidence already tied to this household
            own = set(household.get("applied_event_ids") or [])
            cited, action = [event["_id"] for event in evidence if event["_id"] in own], "call"
        opted_in = (self.memory.registry_entry(promise["household_id"]) or {}).get("opt_in") is True
        decided = {**proposal, "cited_event_ids": [promise["source_event_id"], *cited][:MAX_CITED],
                   "suggested_action": action if opted_in else "visit"}  # calls are opt-in only
        if decision is not None and decision.rationale:
            decided["rationale"] = decision.rationale
        return decided

    def _complete(self, run_id: str, ts: float, purpose: str, subject: str, messages: list[dict],
                  max_tokens: int, tokens: TokenLedger) -> LLMResponse | None:
        """One model call. Any failure falls back to the deterministic path instead of failing the tick."""
        try:
            response = self.llm.complete(messages, max_tokens)
        except MODEL_ERRORS as error:  # the regex/deterministic path always remains available
            self._emit(run_id, ts, "llm_unavailable", f"{purpose}:{subject}", purpose=purpose,
                       error=type(error).__name__)
            return None
        tokens.add(response)
        self._emit(run_id, ts, "llm_call", f"{purpose}:{subject}", purpose=purpose, model=response.model,
                   cached=response.cached, prompt_tokens=response.prompt_tokens,
                   completion_tokens=response.completion_tokens)
        return response

    def _schedule_calls(self, run_id: str, now: float) -> tuple[list[str], int]:
        """Queue one call per approved check-in proposal, for opted-in households only.

        W3 claims each queued request once and writes a run-scoped `call_result` (answered or not)
        that this run reads like any other event; once it has been read the call is complete. A call
        W3 refused because the household withdrew its opt-in writes no result, and is dropped here
        for the same reason W3 refused it.
        """
        queued, scheduled = [], 0
        for proposal in self.memory.proposals_with_status(run_id, "approved"):
            if proposal.get("kind") not in CALLABLE_KINDS:
                continue
            household_id = proposal["household_id"]
            request = build_call_request(proposal, now + CALL_DELAY_HOURS)
            applied = (self.memory.household(run_id, household_id) or {}).get("applied_event_ids") or []
            if call_result_id(request["_id"]) in applied:  # the call happened; its result was read already
                self._emit(run_id, now, "call_completed", request["_id"], call_request_id=request["_id"],
                           proposal_id=proposal["_id"], household_id=household_id)
                continue
            entry = self.memory.registry_entry(household_id) or {}
            if entry.get("opt_in") is not True:
                self._emit(run_id, now, "call_skipped_no_opt_in", proposal["_id"],
                           proposal_id=proposal["_id"], household_id=household_id)
                continue
            scheduled += bool(self.calls.schedule_call(request))  # one queued call per proposal, ever
            queued.append(request["_id"])
            self._emit(run_id, now, "call_scheduled", request["_id"], call_request_id=request["_id"],
                       proposal_id=proposal["_id"], household_id=household_id)
        return sorted(queued), scheduled

    def _policy(self, run_id: str, version: int) -> dict:
        if version == 0:
            return DEFAULT_POLICY
        if (run_id, version) not in self._policies:
            change = self.ledger.policy_change(run_id, version) if self.ledger is not None else None
            if change is None:
                raise RuntimeError(f"policy version {version} of run {run_id!r} is not on record")
            self._policies[(run_id, version)] = change["params"]
        return self._policies[(run_id, version)]

    def _review_policy(self, run_id: str, version: int, previous_ts: float, now: float, policy: dict,
                       silent: int) -> int:
        """Once a simulated day: score both halves of the goal, record them, and move the policy if needed."""
        if self.ledger is None or not review_due(previous_ts, now):
            return version
        metrics = {**goal_metrics(self.ledger.run_promises(run_id), self.ledger.run_proposals(run_id), now),
                   "silent_households": float(silent)}  # schemas.GoalStatus.silent_households
        measured = {name: value for name, value in metrics.items() if value is not None}  # no fake zeros
        day = int(now // REVIEW_EVERY_HOURS)
        for name, value in measured.items():
            self.ledger.record_metric({"_id": stable_id("metric", run_id, name, f"day:{day}"), "run_id": run_id,
                                       "name": name, "value": value, "scope": "goal", "ts": now})
        self._emit(run_id, now, "goal_scored", f"day:{day}", **metrics)
        change = review(policy, metrics)
        if change is None:
            return version
        new_policy, why = change
        record = build_policy_change(run_id, version + 1, policy, new_policy, why, measured, now)
        self.ledger.record_policy_change(record)
        self._policies[(run_id, version + 1)] = new_policy
        self._emit(run_id, now, "policy_changed", record["_id"], version=version + 1,
                   what_changed=record["what_changed"], metric_values=measured)
        return version + 1

    def _account_tokens(self, run_id: str, tick: int, now: float, tokens: TokenLedger) -> None:
        if not (tokens.calls or tokens.cached_calls):
            return
        metrics = tokens.as_metrics()
        if self.ledger is not None:
            for name, value in metrics.items():
                self.ledger.record_metric({"_id": stable_id("metric", run_id, name, f"tick:{tick}"),
                                           "run_id": run_id, "name": name, "value": value, "scope": "tick",
                                           "ts": now})
        self._emit(run_id, now, "llm_usage", f"tick:{tick}", **metrics)

    def _emit(self, run_id: str, ts: float, action: str, subject: str, **detail) -> None:
        """Trace every action; the deterministic _id keeps a replayed tick from duplicating it."""
        self.memory.system_event({"_id": stable_id("sev", run_id, MODULE, action, subject),
                                  "run_id": run_id, "module": MODULE, "action": action, "ts": ts, **detail})


def call_result_id(call_request_id: str) -> str:
    """The `_id` W3 gives a call's result event (`calls.agent.result_event_id`)."""
    return f"{call_request_id}:result"


def _cite(*event_ids: str) -> list[str]:
    """Citations in priority order, without repeats, capped: what triggered a proposal is never cut."""
    return list(dict.fromkeys(event_ids))[:MAX_CITED]


def _open_items(pending: list[dict]) -> dict[str, set[str]]:
    """Kinds of non-urgent proposals each household already has waiting for the coordinator."""
    open_items: dict[str, set[str]] = {}
    for proposal in pending:
        if not proposal.get("urgent"):
            open_items.setdefault(proposal["household_id"], set()).add(proposal.get("kind", ""))
    return open_items


def _newest_ids(proposals: list[dict]) -> list[str]:
    """Ids of the newest proposals, capped so the checkpoint stays small on a six-week run."""
    newest = sorted(proposals, key=lambda p: (-float(p.get("ts") or 0.0), p["_id"]))[:MAX_PENDING_IDS]
    return sorted(p["_id"] for p in newest)


def _identity_hint(event: dict, ref: dict[str, str]) -> dict[str, str]:
    """Intake's structured hints win over what the regex found in the text."""
    hint = {"name": event.get("household_ref_raw") or ref.get("name"),
            "address": event.get("address_raw") or ref.get("address")}
    return {key: str(value) for key, value in hint.items() if value}
