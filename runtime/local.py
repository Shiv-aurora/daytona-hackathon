"""`LocalStore`: an in-process reference implementation of the shared ports, with no database.

It backs the runtime's tests and the offline demo (the default store), and mirrors the semantics of
the reference storage adapters: run-scoped reads (scenario inputs plus the run's own events, via
`event_visible_to_run`), insert-once writes by `_id`, forward-only statuses, one queued call per
proposal (like `db.writes.schedule_call`), and W3's `CallBackend` and `CallLedger`
(queued -> dialing -> done) so the real `CallAgent` can claim a queued request exactly once and
write its result into it.
"""

from __future__ import annotations

import re

from interfaces import event_visible_to_run
from runtime.extract import address_key

CONTACT_SOURCES = ("visit_note", "call_result")  # a person was seen or heard from


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _insert_once(table: dict, doc: dict, key: str = "_id") -> bool:
    if doc[key] in table:
        return False
    table[doc[key]] = dict(doc)
    return True


class LocalStore:
    """Memory, ledger, retrieval, LLM cache, call queue and W3 call backend in one object."""

    def __init__(self, households: dict | None = None, registry: dict | None = None):
        self.households = dict(households or {})  # (run_id, household_id) -> {"name", "address"}
        self.registry = dict(registry or {})  # household_id -> registry entry
        self.events: list[dict] = []
        self.applied: set[tuple[str, str, str]] = set()
        self.applied_ids: dict[tuple[str, str], list[str]] = {}
        self.applied_events: dict[tuple[str, str], list[dict]] = {}
        self.promises: dict[str, dict] = {}
        self.proposals: dict[str, dict] = {}
        self.system_events: dict[str, dict] = {}
        self.metrics: dict[str, dict] = {}
        self.policy_changes: dict[str, dict] = {}
        self.llm_cache: dict[str, dict] = {}
        self.call_requests: dict[tuple[str, str], dict] = {}  # (run_id, proposal_id) -> request
        self.searches: list[dict] = []

    # MemoryPort
    def events_after(self, run_id, scenario_id, after, until_ts, limit):
        rows = [event for event in self.events
                if event_visible_to_run(event, run_id, scenario_id) and event["ts"] <= until_ts
                and (after is None or (event["ts"], event["_id"]) > after)]
        return sorted(rows, key=lambda event: (event["ts"], event["_id"]))[:limit]

    def match_household(self, run_id, identity_hint):
        """Exact address, then address key, then name; ambiguity is no match."""
        mine = {hh: doc for (rid, hh), doc in self.households.items() if rid == run_id}
        rules = (("address", _norm), ("address", address_key), ("name", _norm))
        for field, key in rules:
            wanted = key(identity_hint.get(field) or "")
            if wanted:
                hits = sorted(hh for hh, doc in mine.items() if key(doc.get(field) or "") == wanted)
                if len(hits) == 1:
                    return hits[0]
        return None

    def apply_household_event(self, run_id, household_id, event):
        key = (run_id, household_id, event["_id"])
        is_new = key not in self.applied
        if is_new:
            self.applied.add(key)
            self.applied_ids.setdefault((run_id, household_id), []).append(event["_id"])
            self.applied_events.setdefault((run_id, household_id), []).append(event)
        return is_new

    def household(self, run_id, household_id):
        doc = self.households.get((run_id, household_id))
        if doc is None and (run_id, household_id) not in self.applied_ids:
            return None
        return {**(doc or {}), "run_id": run_id, "household_id": household_id,
                "applied_event_ids": list(self.applied_ids.get((run_id, household_id), []))}

    def registry_entry(self, household_id):
        return self.registry.get(household_id)

    def insert_promise(self, promise):
        return _insert_once(self.promises, promise)

    def open_promises(self, run_id, household_id=None, due_before=None):
        rows = [promise for promise in self.promises.values()
                if promise["run_id"] == run_id and promise["status"] == "open"
                and household_id in (None, promise["household_id"])
                and (due_before is None or promise["due_ts"] < due_before)]
        return sorted(rows, key=lambda promise: (promise["due_ts"], promise["_id"]))

    def set_promise_status(self, run_id, promise_id, status, ts):
        promise = self.promises.get(promise_id)
        if not promise or promise["run_id"] != run_id or promise["status"] != "open":
            return False
        promise.update(status=status, status_ts=ts)
        return True

    def insert_proposal(self, proposal):
        return _insert_once(self.proposals, {"status": "pending", **proposal})

    def proposals_with_status(self, run_id, status):
        return sorted((proposal for proposal in self.proposals.values()
                       if proposal["run_id"] == run_id and proposal["status"] == status),
                      key=lambda proposal: proposal["_id"])

    def system_event(self, event):
        self.system_events.setdefault(event["_id"], event)

    def actions(self, run_id):
        return [event["action"] for event in self.system_events.values() if event["run_id"] == run_id]

    # LedgerPort
    def run_promises(self, run_id):
        return sorted((p for p in self.promises.values() if p["run_id"] == run_id),
                      key=lambda promise: (promise["due_ts"], promise["_id"]))

    def run_proposals(self, run_id):
        return [p for p in self.proposals.values() if p["run_id"] == run_id]

    def registry_entries(self, scenario_id):
        return [{"household_id": household_id, **entry} for household_id, entry in sorted(self.registry.items())
                if entry.get("scenario_id", scenario_id) == scenario_id]

    def last_contact_by_household(self, run_id, scenario_id, as_of_ts):
        """Person contacts only: a visit note, or a call not marked unanswered, that this run applied."""
        last = {}
        for (rid, household_id), events in self.applied_events.items():
            for event in events:
                if (rid == run_id and event_visible_to_run(event, run_id, scenario_id) and event["ts"] <= as_of_ts
                        and event.get("source") in CONTACT_SOURCES and event.get("answered") is not False):
                    last[household_id] = max(event["ts"], last.get(household_id, event["ts"]))
        return last

    def record_metric(self, metric):
        _insert_once(self.metrics, metric)

    def record_policy_change(self, change):
        _insert_once(self.policy_changes, change)

    def policy_change(self, run_id, version):
        return next((c for c in self.policy_changes.values() if c["run_id"] == run_id and c["version"] == version),
                    None)

    # RetrievalPort: word overlap stands in for semantic search, with the same run/time filter.
    def search_events(self, run_id, scenario_id, query, as_of_ts, limit):
        self.searches.append({"run_id": run_id, "query": query, "as_of_ts": as_of_ts})
        words = set(re.findall(r"[a-z0-9]{3,}", query.lower()))
        scored = [(len(words & set(re.findall(r"[a-z0-9]{3,}", str(event.get("text", "")).lower()))), event)
                  for event in self.events
                  if event_visible_to_run(event, run_id, scenario_id) and event["ts"] <= as_of_ts]
        ranked = sorted((pair for pair in scored if pair[0]), key=lambda pair: (-pair[0], pair[1]["ts"]))
        return [event for _, event in ranked[:limit]]

    # LLMCachePort
    def llm_cache_get(self, key):
        return self.llm_cache.get(key)

    def llm_cache_put(self, key, value):
        self.llm_cache[key] = value

    # CallsPort: one queued call per proposal, like db.writes.schedule_call
    def schedule_call(self, request):
        key = (request["run_id"], request["proposal_id"])
        if key in self.call_requests:
            return False
        self.call_requests[key] = {**request, "status": "queued"}
        return True

    # The coordinator's decision (what the console's Approve / Dismiss buttons do through W2)
    def decide(self, run_id, proposal_id, decision, ts):
        proposal = self.proposals.get(proposal_id)
        if not proposal or proposal["run_id"] != run_id or proposal["status"] != "pending":
            return False
        proposal.update(status=decision, status_ts=ts)
        return True

    # W3 CallLedger (calls.agent.CallLedger): only a queued request can be claimed, and only once
    def claim(self, request, ts):
        queued = self._queued(request)
        if queued is None or queued["status"] != "queued":
            return False
        queued.update(status="dialing", status_ts=ts)
        return True

    def finish(self, request, result):
        queued = self._queued(request)
        if queued is not None and queued["status"] == "dialing":
            queued.update(status="done", result=dict(result))

    def result(self, request_id):
        done = next((r for r in self.call_requests.values() if r["_id"] == request_id and "result" in r), None)
        return dict(done["result"]) if done else None

    def _queued(self, request):
        queued = self.call_requests.get((request["run_id"], request.get("proposal_id")))
        return queued if queued is not None and queued["_id"] == request["_id"] else None

    # W3 CallBackend: lets calls.agent.CallAgent run against this store
    def household_context(self, run_id, household_id):
        """What W3 may put in front of the voice model: promises not yet kept (open or past due),
        so the call can ask about them."""
        entry = self.registry.get(household_id) or {}
        promises = [{"text": p["text"], "made_ts": p["made_ts"], "due_ts": p["due_ts"]}
                    for p in self.run_promises(run_id)
                    if p["household_id"] == household_id and p["status"] in ("open", "lapsed")]
        context = {"first_name": entry.get("first_name"), "language": entry.get("language"),
                   "open_promises": promises}
        return {key: value for key, value in context.items() if value is not None}

    def write_event(self, event):
        if any(existing["_id"] == event["_id"] for existing in self.events):
            return False
        self.events.append(dict(event))
        return True

    def escalate(self, proposal):
        return self.insert_proposal(proposal)
