"""Run startup: register the run (schemas.RunMeta) and seed its households from the scenario registry.

Unregistered households are filed later, one visible report at a time, by the runtime's
`DemoMemory(db, file_unregistered=True)`. Hidden scenario truth is never read here.
"""

from __future__ import annotations

from typing import Any

from db.bootstrap import RUNS
from db.scope import RunScope
from memory.adapter import DemoMemory
from memory.households import seed_registry

RUN_FIELDS = ("run_id", "scenario_id", "day0", "mode", "start_ts")


def start_run(db: Any, run_id: str, scenario_id: str, day0: str, mode: str = "live",
              start_ts: float = 0.0) -> dict:
    """Idempotent: restarting a run changes nothing and returns its original metadata."""
    scope = RunScope(db, run_id)
    scope.insert_once(RUNS, {"_id": run_id, "scenario_id": scenario_id, "day0": day0, "mode": mode,
                             "start_ts": start_ts})
    seed_registry(scope, DemoMemory(db).registry_entries(scenario_id))
    return run_meta(db, run_id)


def run_meta(db: Any, run_id: str) -> dict | None:
    doc = RunScope(db, run_id).find_one(RUNS, {"_id": run_id})
    return None if doc is None else {key: doc[key] for key in RUN_FIELDS if key in doc}
