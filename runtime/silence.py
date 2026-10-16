"""The other half of the goal: no opted-in household silent for more than three simulated days."""

from __future__ import annotations

SILENT_AFTER_HOURS = 72.0  # the evaluator's SILENT_AFTER_DAYS, in hours


def silent_households(entries: list[dict], last_contact: dict[str, float], now: float) -> dict[str, float]:
    """Opted-in households registered by `now` and silent for more than 72h, with when the silence began.

    Silence starts at the last contact the run could see, or at registration if that is later
    (a volunteer registering a resident is a contact). Exactly 72h is not yet silent.
    """
    silent = {}
    for entry in entries:
        registered = float(entry.get("registered_ts") or 0.0)
        if entry.get("opt_in") is not True or registered > now:
            continue
        since = max(last_contact.get(entry["household_id"], registered), registered)
        if now - since > SILENT_AFTER_HOURS:
            silent[entry["household_id"]] = since
    return silent
