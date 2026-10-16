"""Metric-driven policy: how many hours before a promise falls due to check in, within fixed bounds.

Once a simulated day the runtime scores its goal. Too many promises missed -> check in earlier.
Too many early check-ins turning out unneeded -> check in later. Each change is recorded with the
metric values that caused it, and the lead time can never leave `LEAD_HOURS_BOUNDS`.
"""

from __future__ import annotations

from runtime.promises import stable_id

DEFAULT_POLICY = {"lead_hours": 0.0}
LEAD_HOURS_BOUNDS = (0.0, 48.0)
LEAD_STEP_HOURS = 12.0
REVIEW_EVERY_HOURS = 24.0
TARGET_ON_TIME_PCT = 90.0
MAX_UNNEEDED_PCT = 50.0
MIN_SAMPLE = 2  # never react to a single promise


def review(policy: dict, metrics: dict[str, float | None]) -> tuple[dict, str] | None:
    """The adjusted policy and why, or None to keep the current one."""
    lead = policy["lead_hours"]
    low, high = LEAD_HOURS_BOUNDS
    on_time = metrics["promises_on_time_pct"]
    if metrics["promises_due"] >= MIN_SAMPLE and on_time < TARGET_ON_TIME_PCT and lead < high:
        why = f"promises_on_time_pct {on_time:.0f} < {TARGET_ON_TIME_PCT:.0f}"
        return {**policy, "lead_hours": min(lead + LEAD_STEP_HOURS, high)}, why
    if (metrics["early_checkins"] >= MIN_SAMPLE and metrics["unneeded_checkin_pct"] > MAX_UNNEEDED_PCT
            and lead > low):
        why = f"unneeded_checkin_pct {metrics['unneeded_checkin_pct']:.0f} > {MAX_UNNEEDED_PCT:.0f}"
        return {**policy, "lead_hours": max(lead - LEAD_STEP_HOURS, low)}, why
    return None


def build_policy_change(run_id: str, version: int, old: dict, new: dict, why: str,
                        metrics: dict[str, float], ts: float) -> dict:
    return {
        "_id": stable_id("policy", run_id, version),
        "run_id": run_id,
        "version": version,
        "what_changed": f"lead_hours {old['lead_hours']:g} -> {new['lead_hours']:g} ({why})",
        "params": new,
        "metric_values": metrics,
        "ts": ts,
    }


def review_due(previous_ts: float, now: float) -> bool:
    """True when this tick crossed a review boundary (once per simulated day)."""
    return int(previous_ts // REVIEW_EVERY_HOURS) != int(now // REVIEW_EVERY_HOURS)
