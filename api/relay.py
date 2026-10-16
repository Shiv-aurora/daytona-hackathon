"""Relay run API v0, the contract in ui/lib/live/client.ts, over the sandbox database.

A run's responses are built from that run's documents plus the scenario inputs it can see up to its
clock; nothing here reads another run's data. `handle` returns (HTTP status, JSON body).
"""

from __future__ import annotations

from typing import Any
from urllib.parse import unquote, urlsplit

from db.bootstrap import (
    CALL_REQUESTS,
    EVENTS,
    HOUSEHOLDS,
    METRICS,
    POLICY_CHANGES,
    PROPOSALS,
    RUNS,
    SYSTEM_EVENTS,
)
from db.events import events_after
from db.runs import load_run_state
from db.scope import RunIsolationError, RunScope
from db.writes import PROPOSAL_DECISIONS, decide_proposal, insert_proposal
from memory.adapter import DemoMemory
from memory.startup import run_meta

RUN_META = ("run_id", "scenario_id", "day0", "mode")
ESCALATION_REASON = "Coordinator asked for a person to follow up from Call View."


class NotFound(LookupError):
    pass


def handle(db: Any, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    parts = [unquote(part) for part in urlsplit(path).path.split("/") if part]
    try:
        if method == "GET" and parts == ["health"]:
            return 200, {"ok": True}
        if method == "GET" and parts == ["runs"]:
            return 200, list_runs(db)
        if parts[:1] == ["runs"] and len(parts) == 3 and parts[2] == "console" and method == "GET":
            return 200, console(db, parts[1])
        if parts[:1] == ["runs"] and len(parts) == 5 and parts[2:5:2] == ["proposals", "decision"] and method == "POST":
            return decide(db, parts[1], parts[3], body or {})
        if parts[:1] == ["runs"] and len(parts) == 5 and parts[2:5:2] == ["calls", "escalate"] and method == "POST":
            return escalate(db, parts[1], parts[3])
    except NotFound as exc:
        return 404, {"error": str(exc)}
    except RunIsolationError as exc:
        return 400, {"error": str(exc)}
    return 404, {"error": "not found"}


def list_runs(db: Any) -> dict:
    runs = []
    for doc in db[RUNS].find({}, sort=[("run_id", 1)]):
        meta = run_meta(db, doc["run_id"]) if isinstance(doc.get("run_id"), str) else None
        if meta and all(key in meta for key in RUN_META):  # skip anything that isn't a started run
            runs.append({"run_id": meta["run_id"], "scenario_id": meta["scenario_id"], "now_ts": _now(db, meta)})
    return {"runs": runs}


def console(db: Any, run_id: str) -> dict:
    meta, memory, scope = _meta(db, run_id), DemoMemory(db), RunScope(db, run_id)
    now = _now(db, meta)
    households = scope.find(HOUSEHOLDS, sort=[("household_id", 1)])
    proposals = memory.run_proposals(run_id)
    here = {household["household_id"] for household in households}
    snapshot = {
        "run": {key: meta[key] for key in RUN_META},
        "now_ts": now,
        "households": households,
        "events": events_after(db, run_id, meta["scenario_id"], None, now, 0),  # all it could see by now
        "promises": memory.run_promises(run_id),
        "proposals": proposals,
        "decisions": {p["_id"]: {"status": p["status"], "ts": p.get("status_ts"), "reason": p.get("decision_reason")}
                      for p in proposals if p["status"] in PROPOSAL_DECISIONS},
        "registry": [entry for entry in memory.registry_entries(meta["scenario_id"]) if entry["household_id"] in here],
        "call_requests": scope.find(CALL_REQUESTS, sort=[("requested_ts", 1), ("_id", 1)]),
        "system_events": scope.find(SYSTEM_EVENTS, sort=[("ts", 1), ("_id", 1)]),
        "metrics": scope.find(METRICS, sort=[("ts", 1), ("_id", 1)]),
        "policy_changes": scope.find(POLICY_CHANGES, sort=[("version", 1)]),
    }
    if "start_ts" in meta:
        snapshot["start_ts"] = meta["start_ts"]
    return snapshot


def decide(db: Any, run_id: str, proposal_id: str, body: dict) -> tuple[int, dict]:
    """pending -> approved | dismissed, forward-only (db.writes.decide_proposal)."""
    status = body.get("status")
    reason = body.get("reason").strip() if isinstance(body.get("reason"), str) else None
    if status not in PROPOSAL_DECISIONS:
        return 400, {"error": "status must be approved or dismissed"}
    if status == "dismissed" and not reason:
        return 400, {"error": "a dismissal needs a reason"}
    meta, scope = _meta(db, run_id), RunScope(db, run_id)
    proposal = scope.find_one(PROPOSALS, {"_id": proposal_id})
    if proposal is None:
        raise NotFound(f"no proposal {proposal_id} in run {run_id}")
    now = _now(db, meta)
    if proposal["status"] != "pending" or not decide_proposal(scope, proposal_id, status, now, reason):
        return 409, {"error": f"proposal is already {scope.find_one(PROPOSALS, {'_id': proposal_id})['status']}"}
    DemoMemory(db).system_event({"_id": f"ui:proposal_decided:{proposal_id}", "run_id": run_id, "module": "ui",
                                  "action": "proposal_decided", "ts": now, "proposal_id": proposal_id,
                                  "decision": status, **({"reason": reason} if reason else {})})
    return 200, scope.find_one(PROPOSALS, {"_id": proposal_id})


def escalate(db: Any, run_id: str, call_id: str) -> tuple[int, dict]:
    """An urgent pending proposal for a person to follow up on a call. Asking twice returns the same one."""
    meta, scope = _meta(db, run_id), RunScope(db, run_id)
    call = scope.find_one(CALL_REQUESTS, {"_id": call_id})
    if call is None:
        raise NotFound(f"no call {call_id} in run {run_id}")
    proposal_id, now = f"{call_id}:human", _now(db, meta)
    result = scope.find_one(EVENTS, {"_id": f"{call_id}:result"})
    if insert_proposal(scope, {
            "_id": proposal_id, "scenario_id": meta["scenario_id"], "household_id": call["household_id"],
            "kind": "human_escalation", "status": "pending", "reason": ESCALATION_REASON, "ts": now,
            "cited_event_ids": [result["_id"]] if result else [], "due_ts": now + 1, "queue": "welfare_check",
            "urgent": True, "call_id": call_id}):
        DemoMemory(db).system_event({"_id": f"ui:human_escalation_requested:{call_id}", "run_id": run_id,
                                      "module": "ui", "action": "human_escalation_requested", "ts": now,
                                      "call_request_id": call_id, "proposal_id": proposal_id})
    return 200, scope.find_one(PROPOSALS, {"_id": proposal_id})


def _meta(db: Any, run_id: str) -> dict:
    meta = run_meta(db, run_id)
    if meta is None or not all(key in meta for key in RUN_META):
        raise NotFound(f"run {run_id} not found")
    return meta


def _now(db: Any, meta: dict) -> float:
    """The run's simulated clock: its last saved tick, or its start before the first tick."""
    state = load_run_state(db, meta["run_id"])
    return state["now_ts"] if state else float(meta.get("start_ts") or 0.0)
