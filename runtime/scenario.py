"""Load a W5 scenario directory for a run: only the files W5 marks visible to Relay.

`scenario.json`, `events.jsonl` (with `origin` stripped) and `registry.json` are read. The truth
files (needles, decoys, promises, households_truth, personas, event_truth) are never opened here;
only the scoring step of the demo reads them, after the run, to call W4's evaluator.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from schemas import SCENARIO_RUN_ID

VISIBLE_FILES = ("scenario.json", "events.jsonl", "registry.json")
HIDDEN_EVENT_FIELDS = ("origin",)  # W5: "hidden from Relay, like every event's origin"


class ScenarioError(ValueError):
    """The scenario directory is missing a file or breaks the event contract."""


@dataclass(frozen=True)
class Scenario:
    scenario_id: str
    day0: str
    end_ts: float
    events: list[dict]
    registry: list[dict]
    callback_number: str | None = None  # Relay's number in the fixed call disclosure


def load_scenario(directory: str | Path) -> Scenario:
    directory = Path(directory)
    missing = [name for name in VISIBLE_FILES if not (directory / name).is_file()]
    if missing:
        raise ScenarioError(f"{directory} is missing {missing}; expected a W5 scenario directory "
                            "(e.g. data/scenarios/s1 from W5's branch)")
    meta = json.loads((directory / "scenario.json").read_text())
    events = []
    for number, line in enumerate((directory / "events.jsonl").read_text().splitlines(), 1):
        if not line.strip():
            continue
        event = {k: v for k, v in json.loads(line).items() if k not in HIDDEN_EVENT_FIELDS}
        if event.get("run_id") != SCENARIO_RUN_ID or event.get("scenario_id") != meta["scenario_id"]:
            raise ScenarioError(f"events.jsonl line {number}: scenario inputs need run_id {SCENARIO_RUN_ID!r} "
                                f"and scenario_id {meta['scenario_id']!r}")
        events.append(event)
    events.sort(key=lambda event: (event["ts"], event["_id"]))
    registry = json.loads((directory / "registry.json").read_text())
    return Scenario(meta["scenario_id"], meta["day0"], float(meta["end_ts"]), events, registry,
                    meta.get("callback_number"))


def seed_local(store, run_id: str, scenario: Scenario) -> None:
    """Put a scenario into a `LocalStore`: inputs, the shared registry, and each registered
    household's identity for this run (the reference registry bootstrap)."""
    known = {event["_id"] for event in store.events}
    store.events.extend(event for event in scenario.events if event["_id"] not in known)
    for entry in scenario.registry:
        store.registry[entry["household_id"]] = dict(entry)
        store.households.setdefault((run_id, entry["household_id"]),
                                    {"name": entry.get("name"), "address": entry.get("address")})
