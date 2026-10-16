"""Write-time conversion from the generators' internal shapes to the shared contract.

The generators reason in days since storm start. `schemas.py` (integration-owned) says every simulated
timestamp is hours since scenario day 0, scenario input events carry run_id == "scenario", and events are
keyed by `_id`. Day 0 is storm start: 2021-09-01 20:00, New York wall clock.

Ground truth follows schemas.Needle {deadline, danger_at} and schemas.TruthPromise
{household_id, source_event_id, made_ts, due_ts, status, status_ts}, all in hours.
"""

DAY0 = "2021-09-01T20:00:00-04:00"  # explicit EDT offset so JS Date.parse is not browser-local
SCENARIO_RUN_ID = "scenario"  # must equal schemas.SCENARIO_RUN_ID (asserted in data/tests)
TS_UNIT = "hours since day0 (storm start, New York wall clock)"


def hours(days):
    return None if days is None else round(days * 24, 3)


def event(e):
    """Internal event (event_id, ts in days) -> schemas.Event plus the data spec's extra fields."""
    rest = {k: v for k, v in e.items() if k not in ("event_id", "scenario_id", "ts")}
    return {"_id": e["event_id"], "run_id": SCENARIO_RUN_ID, "scenario_id": e["scenario_id"], "ts": hours(e["ts"]),
            **rest}


def needle(n):
    """-> schemas.Needle (+ scenario_id, summary)."""
    return {"needle_id": n["needle_id"], "scenario_id": n["scenario_id"], "household_id": n["household_id"],
            "kind": n["kind"], "required_event_ids": n["required_event_ids"], "deadline": hours(n["deadline_day"]),
            "danger_at": hours(n["danger_day"]), "response_hours": n["response_hours"],
            "people_at_risk": n["people_at_risk"], **({"summary": n["summary"]} if "summary" in n else {})}


def promise(p):
    """-> schemas.TruthPromise (+ promise_id, who, what, evidence_event_ids)."""
    return {"promise_id": p["promise_id"], "household_id": p["household_id"], "who": p["who"], "what": p["what"],
            "source_event_id": p["made_in_event_id"], "made_ts": hours(p["made_day"]), "due_ts": hours(p["due_day"]),
            "status": "kept" if p["status"] == "kept" else "lapsed", "status_ts": hours(p["resolved_day"]),
            "evidence_event_ids": [p["evidence_event_id"]] if p.get("evidence_event_id") else []}


def registry_entry(r):
    """-> schemas.RegistryEntry (+ scenario_id, registered_ts and the matching hints Relay needs)."""
    first = " ".join(r["name"].split()[:-1]) or r["name"]
    return {"household_id": r["household_id"], "scenario_id": r["scenario_id"], "opt_in": r["opt_in"],
            "language": r["language"], "first_name": first, "callback_number": r["callback_number"],
            "registered_ts": hours(r["registered_day"]), "name": r["name"], "address": r["address"],
            "registered_by": r["registered_by"], "note": r["note"]}


_TIME_KEYS = {"day": "ts", "due_day": "due_ts", "until_day": "until_ts"}


def timeline_fact(f):
    return {_TIME_KEYS.get(k, k): hours(v) if k in _TIME_KEYS else v for k, v in f.items()}


def household(h):
    return {**h, "timeline": [timeline_fact(f) for f in h["timeline"]]}


def outage_block(b):
    return {**b, "start": hours(b["start"]), "restore_ts": hours(b["restore_ts"])}


def scenario_meta(meta):
    """Replace the internal day clock (t0, ts_unit) with the contract's day0 + hours."""
    out = {k: v for k, v in meta.items() if k not in ("t0", "ts_unit", "outage_blocks")}
    out.update(day0=DAY0, ts_unit=TS_UNIT, end_ts=hours(meta["days"]))
    if "outage_blocks" in meta:
        out["outage_blocks"] = [outage_block(b) for b in meta["outage_blocks"]]
    return out
