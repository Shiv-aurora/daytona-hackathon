"""The OpenRouter extraction and decision paths: prompts out, validated structures back.

The model only proposes structure. Code turns its dates into simulated hours, keeps "kept"
promise ids and citations to ids the run actually showed it, and rejects anything malformed, in
which case the caller falls back to the deterministic path.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date

from runtime.clock import SimClock
from runtime.extract import MAX_PROMISE_TEXT, Extraction, PromiseDraft, keywords

ACTIONS = ("call", "visit")
MAX_REASON = 280
MAX_DUE_AHEAD_HOURS = 60 * 24.0
_RULES = "Reply with JSON only. Never give medical advice. Never compare or rank households."

EXTRACT_SYSTEM = f"You read disaster-recovery field notes about one household and track commitments. {_RULES}"
DECIDE_SYSTEM = f"You help a recovery coordinator follow up on a promise made to a resident. {_RULES}"
RISK_SYSTEM = f"You help a recovery coordinator spot a household whose trouble spans several services. {_RULES}"
MIN_RISK_SOURCES = 2  # a cross-service concern needs evidence from at least two services


@dataclass(frozen=True)
class Decision:
    cited_event_ids: tuple[str, ...]
    suggested_action: str
    rationale: str
    follow_up: bool = True


def extraction_messages(text: str, clock: SimClock, ts: float, open_promises: list[dict]) -> list[dict]:
    on_file = "\n".join(f'- {p["_id"]}: {p["text"]}' for p in open_promises) or "(none)"
    user = (f"Note written {clock.at(ts):%A %Y-%m-%d %H:%M} (local time).\n"
            f"Open promises on file for this household:\n{on_file}\n\nNote:\n{text}\n\n"
            "List new promises someone made to or for this household, with the date they are due, and the "
            "ids of open promises this note shows were kept. JSON: "
            '{"promises": [{"who": str, "what": str, "due_date": "YYYY-MM-DD" or null, '
            '"due_in_hours": number or null}], "kept_promise_ids": [str]}')
    return [{"role": "system", "content": EXTRACT_SYSTEM}, {"role": "user", "content": user}]


def decision_messages(promise: dict, clock: SimClock, now: float, evidence: list[dict]) -> list[dict]:
    user = (f"Now: {clock.at(now):%A %Y-%m-%d %H:%M}.\n"
            f'Promise on file: "{promise["text"]}", due {clock.at(promise["due_ts"]):%A %Y-%m-%d %H:%M}.\n'
            f"Events the team can see:\n{_evidence_lines(clock, evidence)}\n\n"
            "Which events bear on whether this household is still waiting on the promise? Suggest a follow-up. "
            'JSON: {"cited_event_ids": [str], "suggested_action": "call" or "visit", "rationale": "one sentence"}')
    return [{"role": "system", "content": DECIDE_SYSTEM}, {"role": "user", "content": user}]


def risk_messages(entry: dict, clock: SimClock, now: float, evidence: list[dict]) -> list[dict]:
    household = f'{entry.get("name") or "a registered resident"}, {entry.get("address") or "address on file"}'
    user = (f"Now: {clock.at(now):%A %Y-%m-%d %H:%M}.\nRegistered household: {household}.\n"
            f"Events from different services that may concern this household:\n{_evidence_lines(clock, evidence)}\n\n"
            "Taken together, do these events show a problem at this household that is still unresolved and needs a "
            "person to follow up? A problem that was reported and then resolved does not. Cite at least two events "
            'from different services if so. JSON: {"follow_up": true or false, "cited_event_ids": [str], '
            '"suggested_action": "call" or "visit", "rationale": "one sentence"}')
    return [{"role": "system", "content": RISK_SYSTEM}, {"role": "user", "content": user}]


def _evidence_lines(clock: SimClock, evidence: list[dict]) -> str:
    return "\n".join(f'- {event["_id"]} ({clock.at(event["ts"]):%a %m-%d %H:%M}, {event.get("source")}): '
                     f'{str(event.get("text", ""))[:300]}' for event in evidence)


def parse_extraction(reply: str, ts: float, clock: SimClock, open_ids: set[str]) -> Extraction | None:
    data = _json_object(reply)
    if data is None or not isinstance(data.get("promises", []), list):
        return None
    promises = []
    for item in data.get("promises", []):
        if not isinstance(item, dict):
            return None
        who, what = str(item.get("who") or "").strip(), str(item.get("what") or "").strip()
        due = _due(item, ts, clock)
        if what and due is not None:
            text = (f"{who}: {what}" if who else what)[:MAX_PROMISE_TEXT]
            promises.append(PromiseDraft(text, due, keywords(text)))
    kept = data.get("kept_promise_ids", [])
    if not isinstance(kept, list):
        return None
    return Extraction({}, tuple(promises), (), tuple(sorted({str(i) for i in kept} & open_ids)))


def parse_decision(reply: str, allowed_ids: set[str]) -> Decision | None:
    data = _json_object(reply)
    if data is None or data.get("suggested_action") not in ACTIONS or not isinstance(data.get("cited_event_ids"), list):
        return None
    rationale = " ".join(str(data.get("rationale") or "").split())[:MAX_REASON]
    cited = tuple(dict.fromkeys(str(i) for i in data["cited_event_ids"] if str(i) in allowed_ids))
    return Decision(cited, data["suggested_action"], rationale)


def parse_risk(reply: str, sources: dict[str, str]) -> Decision | None:
    """A validated cross-service answer. `sources` maps each event id shown to its service.

    "No follow-up" is a valid answer. "Follow up" counts only when it cites at least two of the
    events shown, from at least two services; anything else is rejected.
    """
    data = _json_object(reply)
    if data is None or not isinstance(data.get("follow_up"), bool):
        return None
    if not data["follow_up"]:
        return Decision((), "visit", "", follow_up=False)
    decision = parse_decision(reply, set(sources))
    if decision is None or len({sources[i] for i in decision.cited_event_ids}) < MIN_RISK_SOURCES:
        return None
    return decision


def _due(item: dict, ts: float, clock: SimClock) -> float | None:
    """A due hour the model gave as a date or an offset; implausible values are dropped."""
    try:
        if item.get("due_date"):
            due = clock.end_of_day(date.fromisoformat(str(item["due_date"])))
        elif item.get("due_in_hours") is not None:
            due = ts + float(item["due_in_hours"])
        else:
            return None
    except (TypeError, ValueError):
        return None
    return due if ts - 7 * 24 <= due <= ts + MAX_DUE_AHEAD_HOURS else None


def _json_object(reply: str) -> dict | None:
    start, end = reply.find("{"), reply.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(reply[start:end + 1])
    except json.JSONDecodeError:
        return None
    return data if isinstance(data, dict) else None
