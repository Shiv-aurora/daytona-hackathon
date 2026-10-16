"""Typed or spoken volunteer visit note -> one Relay event (same shape as data/scenarios/*/events.jsonl).

    python -m intake.visit_note --scenario s1 --run-id run-1 --ts 42.6 --author "Volunteer Ana R." "Visited ..."
    python -m intake.visit_note --scenario s1 --run-id run-1 --ts 42.6 --author "Volunteer Ana R." --transcript note.json

Events follow `schemas.Event`: `_id`, `run_id`, `scenario_id`, `ts` in hours since scenario day 0
(storm start, 2021-09-01 20:00 New York). A note entered during a run carries that run's id; a note
authored into scenario input carries `schemas.SCENARIO_RUN_ID`.

Spoken notes arrive as a speech-to-text transcript (e.g. ElevenLabs Scribe output from the UI);
this module makes no network calls. Events never carry a household_id: matching is Relay's job.
Event ids are content hashes, so the same note always yields the same event, and `merge` keeps a
stream in deterministic (ts, _id) order, the runtime's cursor order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

from schemas import SCENARIO_RUN_ID

DAY0 = datetime(2021, 9, 1, 20, 0)  # noqa: DTZ001 - scenario day 0 = storm start, NY wall clock
EVENT_FIELDS = ("_id", "run_id", "scenario_id", "ts", "ts_real", "source", "text", "address_raw", "geo",
                "household_ref_raw", "channel_meta", "real_311_key", "origin")
ISO_639_3 = {"eng": "en", "spa": "es", "cmn": "zh", "zho": "zh", "kor": "ko", "ben": "bn"}

_SUFFIX = r"(?:St|Street|Ave|Avenue|Rd|Road|Pl|Place|Blvd|Boulevard|Dr|Drive|Ln|Lane|Ct|Court|Pkwy|Parkway|Ter|Terrace)"
_STREET = r"(?:\d+(?:st|nd|rd|th)?|[A-Z][a-z]+(?: [A-Z][a-z]+)?)"
ADDRESS_RE = re.compile(rf"\b(\d{{2,3}}-\d{{2,3}}[A-Z]?) ({_STREET}) ({_SUFFIX})\b\.?")
SUFFIX_SHORT = {"Street": "St", "Avenue": "Ave", "Road": "Rd", "Place": "Pl", "Boulevard": "Blvd", "Drive": "Dr",
                "Lane": "Ln", "Court": "Ct", "Parkway": "Pkwy", "Terrace": "Ter"}
REF_RE = re.compile(r"\b((?:Mr|Mrs|Ms|Miss|Dr)\.? [A-Z][A-Za-z'\-]+|[A-Z][a-z]+ family)\b")


def extract_address(text: str) -> str | None:
    """First Queens-style house address in the note, suffix abbreviated ('41-22 Hollow Oak Lane' -> '41-22 Hollow
    Oak Ln'), else None. Registry identities are written that way, so W2's normalized match resolves a spoken
    "Lane" to the registered "Ln"."""
    m = ADDRESS_RE.search(text)
    return f"{m.group(1)} {m.group(2)} {SUFFIX_SHORT.get(m.group(3), m.group(3))}" if m else None


def extract_ref(text: str) -> str | None:
    """First way the note refers to the resident ('Mrs. Chen', 'Islam family'), else None."""
    m = REF_RE.search(text)
    return m.group(1) if m else None


def visit_note_event(text: str, *, ts: float, author: str, scenario_id: str, run_id: str, language: str = "en",
                     channel: str = "typed", stt: dict | None = None) -> dict:
    text = " ".join((text or "").split())
    if not text:
        raise ValueError("visit note text is empty")
    if not ts >= 0:
        raise ValueError(f"ts must be >= 0 hours since day 0, got {ts!r}")
    if not author.strip():
        raise ValueError("visit note needs an author")
    if not run_id:
        raise ValueError(f"run_id is required (the active run, or {SCENARIO_RUN_ID!r} for scenario input)")
    digest = hashlib.sha256(f"{scenario_id}|{run_id}|{ts:.6f}|{author}|{text}".encode()).hexdigest()[:12]
    meta = {"author": author, "language": language, "channel": channel, **({"stt": stt} if stt else {})}
    return {
        "_id": f"{scenario_id}_vn_{digest}",
        "run_id": run_id,
        "scenario_id": scenario_id,
        "ts": round(ts, 3),
        "ts_real": (DAY0 + timedelta(hours=ts)).strftime("%Y-%m-%dT%H:%M"),
        "source": "visit_note",
        "text": text,
        "address_raw": extract_address(text),
        "geo": None,
        "household_ref_raw": extract_ref(text),
        "channel_meta": meta,
        "real_311_key": None,
        "origin": "intake",  # hidden from Relay, like every event's origin
    }


def from_transcript(transcript: dict, *, ts: float, author: str, scenario_id: str, run_id: str) -> dict:
    """Spoken note: a speech-to-text result with at least `text` (and optionally `language_code`)."""
    code = (transcript.get("language_code") or "en").lower()
    stt = {k: transcript[k] for k in ("engine", "language_probability") if k in transcript}
    return visit_note_event(transcript.get("text", ""), ts=ts, author=author, scenario_id=scenario_id,
                            run_id=run_id, language=ISO_639_3.get(code, code[:2]), channel="spoken",
                            stt=stt or None)


def system_event(event: dict, run_id: str) -> dict:
    """`schemas.SystemEvent` intake reports when it accepts a note (persisted by the runtime/DB layer)."""
    if not run_id or run_id == SCENARIO_RUN_ID:
        raise ValueError("system events are run-scoped; an active run_id is required")
    return {"_id": f"sys_intake_{run_id}_{event['_id']}", "run_id": run_id, "module": "intake",
            "action": "event_in", "ts": event["ts"], "ref_ids": [event["_id"]],
            "summary": f"visit note from {event['channel_meta']['author']}"}


def merge(events: list[dict], new: list[dict]) -> list[dict]:
    """Add events to a stream: idempotent for identical events, sorted by (ts, _id)."""
    by_id = {e["_id"]: e for e in events}
    for e in new:
        if e["_id"] in by_id and by_id[e["_id"]] != e:
            raise ValueError(f"event id collision with different content: {e['_id']}")
        by_id[e["_id"]] = e
    return sorted(by_id.values(), key=lambda e: (e["ts"], e["_id"]))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("text", nargs="?", help="typed note (omit with --transcript)")
    ap.add_argument("--scenario", required=True)
    ap.add_argument("--ts", type=float, required=True, help="hours since scenario day 0 (storm start)")
    ap.add_argument("--author", required=True)
    ap.add_argument("--language", default="en")
    ap.add_argument("--transcript", type=Path, help="speech-to-text JSON with a 'text' field")
    ap.add_argument("--run-id", default=SCENARIO_RUN_ID,
                    help=f"active run (also prints its system_event); default {SCENARIO_RUN_ID!r} = scenario input")
    args = ap.parse_args(argv)
    if args.transcript:
        event = from_transcript(json.loads(args.transcript.read_text()), ts=args.ts, author=args.author,
                                scenario_id=args.scenario, run_id=args.run_id)
    else:
        event = visit_note_event(args.text or "", ts=args.ts, author=args.author, scenario_id=args.scenario,
                                 run_id=args.run_id, language=args.language)
    print(json.dumps(event, ensure_ascii=False))
    if args.run_id != SCENARIO_RUN_ID:
        print(json.dumps(system_event(event, args.run_id), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
