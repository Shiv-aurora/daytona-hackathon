#!/usr/bin/env python3
"""Scenario 1 is frozen: `scenarios/s1/manifest.json` pins the judge/demo dataset.

    python data/freeze.py            # verify the committed files against the manifest (exit 1 on any change)
    python data/freeze.py --write    # re-pin: only after the PM signs off on a new Scenario 1 revision

The manifest holds only what is already visible (scenario metadata, file hashes, registry and event anchors); it
adds no hidden truth. `validate.py` runs `verify` as part of the Scenario 1 gate.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

S1 = Path(__file__).parent / "scenarios" / "s1"
MANIFEST = "manifest.json"
# Every Scenario 1 artifact the runtime, evaluator, call simulator or demo reads.
ARTIFACTS = ("events.jsonl", "registry.json", "scenario.json", "needles.json", "decoys.json", "promises.json",
             "households_truth.json", "event_truth.json", "contact_truth.json", "personas.json", "REVIEW.md")
# Mrs. Chen's visible demo chain: her registry entry and the three events the demo walks through.
CHEN = {"household_id": "s1_h_001", "visit_note": "s1_e_000376", "utility_delay": "s1_e_000818", "crew": "s1_e_001073"}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(directory: Path = S1) -> dict:
    meta = json.loads((directory / "scenario.json").read_text())
    events = {e["_id"]: e for e in map(json.loads, (directory / "events.jsonl").open())}
    entry = next(r for r in json.loads((directory / "registry.json").read_text())
                 if r["household_id"] == CHEN["household_id"])

    def anchor(key):
        e = events[CHEN[key]]
        return {"event_id": e["_id"], "source": e["source"], "ts": e["ts"], "ts_real": e["ts_real"]}

    return {
        "scenario_id": meta["scenario_id"], "seed": meta["seed"], "revision": meta["revision"],
        "day0": meta["day0"], "end_ts": meta["end_ts"], "label": meta["label"],
        "sha256": {name: sha256(directory / name) for name in ARTIFACTS},
        "mrs_chen": {"household_id": entry["household_id"], "name": entry["name"], "address": entry["address"],
                     "visit_note": anchor("visit_note"), "utility_delay": anchor("utility_delay"),
                     "crew": anchor("crew")},
    }


def verify(directory: Path = S1) -> list[str]:
    """Every difference between the committed files and the frozen manifest; empty means frozen."""
    path = directory / MANIFEST
    if not path.exists():
        return [f"missing {path}"]
    frozen = json.loads(path.read_text())
    problems = [f"{name} changed" if (directory / name).exists() else f"{name} missing"
                for name, digest in frozen["sha256"].items()
                if not (directory / name).exists() or sha256(directory / name) != digest]
    try:
        current = build(directory)
    except (OSError, KeyError, StopIteration, json.JSONDecodeError) as exc:
        return [*problems, f"cannot read the frozen artifacts: {exc!r}"]
    problems += [f"{key} changed: {frozen[key]!r} -> {current[key]!r}" for key in frozen
                 if key != "sha256" and current.get(key) != frozen[key]]
    return problems


def main(argv: list[str]) -> int:
    if "--write" in argv:
        (S1 / MANIFEST).write_text(json.dumps(build(), indent=1, ensure_ascii=False) + "\n")
        print(f"pinned {S1 / MANIFEST}")
        return 0
    problems = verify()
    for problem in problems:
        print(f"FROZEN: {problem}")
    print("Scenario 1 matches its frozen manifest" if not problems else f"{len(problems)} frozen-manifest violations")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
