"""Approved lessons in the offline reference store; SurrealDB persistence comes next."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from db.bootstrap import LESSONS
from db.scope import require_run_id


class LessonStore:
    def __init__(self, db: Any):
        self.collection = db[LESSONS]

    def add(self, lesson: Mapping, *, run_id: str, scenario_id: str, ts: float) -> bool:
        run_id = require_run_id(run_id)
        result = self.collection.update_one(
            {"_id": lesson["lesson_id"]},
            {"$setOnInsert": {**lesson, "approved": False, "run_id": run_id,
                              "scenario_id": scenario_id, "ts": ts}}, upsert=True)
        return result.upserted_id is not None

    def approve(self, lesson_id: str) -> bool:
        result = self.collection.update_one({"_id": lesson_id, "approved": False},
                                             {"$set": {"approved": True}})
        return bool(result.modified_count)

    def visible(self, run_id: str, scenario_id: str, as_of_ts: float) -> list[dict]:
        require_run_id(run_id)
        approved = self.collection.find({"approved": True})
        usable = [{k: v for k, v in item.items() if k != "_id"} for item in approved
                  if item["scenario_id"] != scenario_id
                  or (item["run_id"] == run_id and item["ts"] <= as_of_ts)]
        return sorted(usable, key=lambda item: (item["ts"], item["lesson_id"]))
