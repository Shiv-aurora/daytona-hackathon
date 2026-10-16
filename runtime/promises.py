"""Promise, proposal and call-request documents with deterministic ids.

Ids are hashes of their inputs, so every write is insert-once: a replayed tick rebuilds the same
documents and the memory layer ignores them.
"""

from __future__ import annotations

import hashlib

from runtime.extract import PromiseDraft

PROPOSAL_KIND = "check_in"  # a promise is at risk
SILENCE_KIND = "silence_check_in"  # an opted-in household has gone quiet for more than 72h
RISK_KIND = "cross_service_check_in"  # several services report trouble at one household
ESCALATION_KIND = "escalation"  # a promise is past due and new trouble was reported: a person should go
CALLABLE_KINDS = frozenset({PROPOSAL_KIND, SILENCE_KIND, RISK_KIND})  # once approved, and only with opt-in


def stable_id(prefix: str, *parts: object) -> str:
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


def build_promise(run_id: str, household_id: str, event: dict, index: int, draft: PromiseDraft) -> dict:
    return {
        "_id": stable_id("promise", run_id, event["_id"], index),
        "run_id": run_id,
        "scenario_id": event.get("scenario_id"),
        "household_id": household_id,
        "text": draft.text,
        "keywords": sorted(draft.keywords),
        "made_ts": event["ts"],
        "due_ts": draft.due_ts,
        "status": "open",
        "source_event_id": event["_id"],
    }


def is_fulfilled_by(promise: dict, fulfilments: tuple[frozenset[str], ...]) -> bool:
    keywords = set(promise["keywords"])
    return any(keywords & statement for statement in fulfilments)


def build_proposal(promise: dict, now_ts: float) -> dict:
    """One check-in per promise (same `_id` whether it comes early or at the lapse)."""
    early = promise["due_ts"] >= now_ts
    status = "falls due soon with no fulfilment on record yet" if early else (
        "passed its deadline with no fulfilment on record")
    return {
        "_id": stable_id("proposal", promise["run_id"], promise["_id"], PROPOSAL_KIND),
        "run_id": promise["run_id"],
        "scenario_id": promise.get("scenario_id"),
        "household_id": promise["household_id"],
        "kind": PROPOSAL_KIND,
        "status": "pending",  # only a human (UI Approve/Dismiss) moves it on
        "promise_id": promise["_id"],
        "reason": f'Promise {status}: "{promise["text"]}"',
        "due_ts": promise["due_ts"],
        "cited_event_ids": [promise["source_event_id"]],
        "ts": now_ts,  # `ts` / `cited_event_ids`: the proposal fields W4's scorer reads
        "early": early,
    }


def build_escalation(run_id: str, scenario_id: str, event: dict, household_id: str, reason: str) -> dict:
    """Immediate urgent-human escalation for an emergency phrase (W3's shape); no model is consulted."""
    return {
        "_id": stable_id("proposal", run_id, event["_id"], "emergency"),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "household_id": household_id,
        "kind": "emergency",
        "status": "pending",
        "queue": "urgent_human",
        "urgent": True,
        "reason": f"Emergency phrase ({reason}) in a {event.get('source', 'note')}: {str(event.get('text', ''))[:200]}",
        "cited_event_ids": [event["_id"]],
        "ts": event["ts"],
    }


def build_silence_proposal(run_id: str, scenario_id: str, household_id: str, silent_since: float, now_ts: float,
                           cited_event_ids: list[str]) -> dict:
    """One follow-up per silence episode: the `_id` includes when the silence began."""
    return {
        "_id": stable_id("proposal", run_id, household_id, SILENCE_KIND, silent_since),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "household_id": household_id,
        "kind": SILENCE_KIND,
        "status": "pending",
        "reason": f"No contact with this opted-in household for {now_ts - silent_since:.0f} hours "
                  "(goal: never more than 72).",
        "cited_event_ids": cited_event_ids,
        "suggested_action": "call",
        "ts": now_ts,
    }


def build_lapse_escalation(check_in: dict, event: dict, cited_event_ids: list[str],
                           corroborated: bool = False) -> dict:
    """One escalation per lapsed promise, raised by the first new report of trouble after it.

    When that first escalation came from an unanswered call, a later report from a service may add
    one `corroborated` escalation, so a promise is escalated at most twice.
    """
    report = f'a new report says: "{str(event.get("text", ""))[:160]}"'
    if corroborated:
        what = f"the check-in call went unanswered, and {report}"
    else:
        what = "the check-in call went unanswered" if event.get("source") == "call_result" else report
    parts = (check_in["promise_id"], ESCALATION_KIND) + (("corroborated",) if corroborated else ())
    return {
        "_id": stable_id("proposal", check_in["run_id"], *parts),
        "run_id": check_in["run_id"],
        "scenario_id": check_in.get("scenario_id"),
        "household_id": check_in["household_id"],
        "kind": ESCALATION_KIND,
        "status": "pending",
        "promise_id": check_in["promise_id"],
        "reason": f"A promise to this household is past due and {what}",
        "cited_event_ids": cited_event_ids,
        "suggested_action": "visit",
        "trigger_event_id": event["_id"],
        "trigger_source": event.get("source"),
        "ts": event["ts"],
    }


def risk_proposal_id(run_id: str, household_id: str) -> str:
    return stable_id("proposal", run_id, household_id, RISK_KIND)


def build_risk_proposal(run_id: str, scenario_id: str, household_id: str, cited_event_ids: list[str],
                        suggested_action: str, rationale: str, now_ts: float) -> dict:
    """At most one cross-service follow-up per household per run."""
    return {
        "_id": risk_proposal_id(run_id, household_id),
        "run_id": run_id,
        "scenario_id": scenario_id,
        "household_id": household_id,
        "kind": RISK_KIND,
        "status": "pending",
        "reason": "Reports from several services point to an unresolved problem at this household.",
        "cited_event_ids": cited_event_ids,
        "suggested_action": suggested_action,
        "rationale": rationale,
        "ts": now_ts,
    }


def build_call_request(proposal: dict, now_ts: float) -> dict:
    request = {
        "_id": stable_id("callreq", proposal["run_id"], proposal["_id"]),
        "run_id": proposal["run_id"],
        "scenario_id": proposal.get("scenario_id"),
        "household_id": proposal["household_id"],
        "proposal_id": proposal["_id"],
        "purpose": "promise_check_in" if proposal["kind"] == PROPOSAL_KIND else proposal["kind"],
        "requested_ts": now_ts,
    }
    if proposal.get("promise_id"):
        request["promise_id"] = proposal["promise_id"]
    return request
