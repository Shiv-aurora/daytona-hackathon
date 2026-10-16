"""Replay-safe writes. Documents carry the caller's deterministic `_id`, creates use
`$setOnInsert`, and status changes are compare-and-set, so replaying a tick never duplicates
a proposal or a queued call and never resets a status a coordinator already set."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from db.bootstrap import CALL_REQUESTS, PROPOSALS, SYSTEM_EVENTS
from db.scope import RunScope

PROPOSAL_DECISIONS = ("approved", "dismissed")


def emit(scope: RunScope, module: str, action: str, ts: float, **detail: Any) -> None:
    """Append a system_event to the run's trace."""
    scope.insert(SYSTEM_EVENTS, {"module": module, "action": action, "ts": ts, **detail})


def insert_proposal(scope: RunScope, proposal: Mapping) -> bool:
    """Insert a proposal once by its `_id` (status defaults to "pending"). Never resets a decision."""
    created = scope.insert_once(PROPOSALS, {"status": "pending", **proposal})
    if created:
        emit(scope, "db", "proposal_created", proposal.get("ts"), proposal_id=proposal["_id"],
             household_id=proposal.get("household_id"))
    return created


def schedule_call(scope: RunScope, request: Mapping) -> bool:
    """Queue a CallRequest once per proposal. False if that proposal already has a queued call.

    Keyed by proposal_id, so asking again for an approved proposal on a later tick (new
    requested_ts, or even a new request _id) never queues a second call. The caller's _id is kept.
    """
    created = scope.insert_once(CALL_REQUESTS, {**request, "status": "queued"}, key="proposal_id")
    if created:
        emit(scope, "db", "call_queued", request.get("requested_ts"), call_request_id=request["_id"],
             proposal_id=request["proposal_id"], household_id=request.get("household_id"))
    return created


def advance_status(scope: RunScope, collection: str, doc_id: str, expected: str, new: str,
                   ts: float, **fields: Any) -> bool:
    """Compare-and-set a document's status (plus `fields`). A replayed or stale transition changes nothing."""
    result = scope.update_one(collection, {"_id": doc_id, "status": expected},
                              {"$set": {**fields, "status": new, "status_ts": ts}})
    if result.modified_count:
        emit(scope, "db", "status_changed", ts, collection=collection, doc_id=doc_id, status=new)
    return bool(result.modified_count)


def decide_proposal(scope: RunScope, proposal_id: str, decision: str, ts: float, reason: str | None = None) -> bool:
    """A coordinator's approve or dismiss. Only a pending proposal can be decided; a dismissal needs a reason."""
    reason = (reason or "").strip() or None
    if decision not in PROPOSAL_DECISIONS:
        raise ValueError(f"decision must be one of {PROPOSAL_DECISIONS}, got {decision!r}")
    if decision == "dismissed" and reason is None:
        raise ValueError("a dismissal needs a reason")
    return advance_status(scope, PROPOSALS, proposal_id, "pending", decision, ts, decision_reason=reason)
