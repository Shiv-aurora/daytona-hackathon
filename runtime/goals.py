"""Goal tracking: is every promise met (kept, or escalated to a person) before it falls due?

Computed from the run's own promises and proposals only, never from ground truth. "Before" is
strictly earlier, matching the evaluator. A rate is None when nothing is there to measure
(`schemas.GoalStatus`: undefined rather than a fake 100).
"""

from __future__ import annotations

INF = float("inf")


def goal_metrics(promises: list[dict], proposals: list[dict], now: float) -> dict[str, float | None]:
    escalated_at: dict[str, float] = {}
    for proposal in proposals:
        if promise_id := proposal.get("promise_id"):
            escalated_at[promise_id] = min(escalated_at.get(promise_id, INF), proposal["ts"])
    due = [p for p in promises if p["due_ts"] <= now]
    met = [p for p in due if _kept_before_due(p) or escalated_at.get(p["_id"], INF) < p["due_ts"]]
    early = [p for p in promises if escalated_at.get(p["_id"], INF) < p["due_ts"]]
    unneeded = [p for p in early if p["status"] == "kept"]
    return {
        "promises_open": float(sum(p["status"] == "open" for p in promises)),
        "promises_due": float(len(due)),
        "promises_met": float(len(met)),
        "promises_on_time_pct": 100.0 * len(met) / len(due) if due else None,
        "early_checkins": float(len(early)),
        "unneeded_checkin_pct": 100.0 * len(unneeded) / len(early) if early else None,
    }


def _kept_before_due(promise: dict) -> bool:
    return promise["status"] == "kept" and promise.get("status_ts", INF) < promise["due_ts"]
