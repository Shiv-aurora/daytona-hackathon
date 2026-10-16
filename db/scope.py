"""Run isolation. Per-run reads and writes go through a RunScope bound to one run_id,
which pins every filter to that run and refuses anything that reaches into another.

"scenario" is not a run: it tags scenario inputs, which every run of that scenario reads.
Only `RunScope.scenario(db)` writes them, so a run can never pass its own events off as inputs.
"""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from schemas import SCENARIO_RUN_ID

DUPLICATE_KEY = 11000  # the reference store's duplicate-key error code


class RunIsolationError(PermissionError):
    """A read or write tried to cross into another run."""


def require_run_id(run_id: object) -> str:
    if not isinstance(run_id, str) or not run_id.strip() or run_id == SCENARIO_RUN_ID:
        raise RunIsolationError(f"run_id must be a non-empty string other than {SCENARIO_RUN_ID!r}, "
                                f"got {run_id!r}")
    return run_id


def stable_id(prefix: str, *parts: object) -> str:
    """Deterministic _id from a natural key (the same formula the runtime uses)."""
    digest = hashlib.sha256("|".join(str(part) for part in parts).encode()).hexdigest()[:16]
    return f"{prefix}-{digest}"


class RunScope:
    def __init__(self, db: Any, run_id: str):
        self.db = db
        self.run_id = require_run_id(run_id)

    @classmethod
    def scenario(cls, db: Any) -> RunScope:
        """The scope that writes scenario inputs (run_id "scenario"), e.g. for intake."""
        scope = cls.__new__(cls)
        scope.db, scope.run_id = db, SCENARIO_RUN_ID
        return scope

    def query(self, filter: Mapping | None = None) -> dict:
        """Pin a filter to this run. A filter that names any other run is refused."""
        query = dict(filter or {})
        if query.setdefault("run_id", self.run_id) != self.run_id:
            raise RunIsolationError(f"run {self.run_id!r} cannot query run_id={query['run_id']!r}")
        return query

    def find(self, collection: str, filter: Mapping | None = None, **kwargs: Any) -> list[dict]:
        return list(self.db[collection].find(self.query(filter), **kwargs))

    def find_one(self, collection: str, filter: Mapping | None = None) -> dict | None:
        return self.db[collection].find_one(self.query(filter))

    def count(self, collection: str, filter: Mapping | None = None) -> int:
        return self.db[collection].count_documents(self.query(filter))

    def insert(self, collection: str, doc: Mapping) -> None:
        """Append a new document, such as a trace entry, stamped with this run."""
        self.db[collection].insert_one(self._stamp(doc))

    def update_one(self, collection: str, filter: Mapping, update: Mapping, upsert: bool = False):
        for operator, fields in update.items():
            if any(path == "run_id" or path.startswith("run_id.") for path in fields):
                raise RunIsolationError(f"{operator} cannot change run_id")
        return self.db[collection].update_one(self.query(filter), dict(update), upsert=upsert)

    def insert_once(self, collection: str, doc: Mapping, key: str = "_id") -> bool:
        """Insert `doc` with `$setOnInsert`, at most once per value of `doc[key]` in this run.

        Returns True if this call created it; a replay changes nothing. A document `_id` that
        belongs to another run is refused rather than read or overwritten.
        """
        doc = self._stamp(doc)
        match = {key: doc[key]}
        fields = {name: value for name, value in doc.items() if name not in (key, "run_id")}
        try:
            result = self.update_one(collection, match, {"$setOnInsert": fields}, upsert=True)
        except Exception as exc:  # the driver's DuplicateKeyError; the reference store isn't imported here
            if getattr(exc, "code", None) != DUPLICATE_KEY:
                raise
            owner = self.db[collection].find_one({"_id": doc["_id"]}) if "_id" in doc else None
            if owner is not None and owner.get("run_id") != self.run_id:
                raise RunIsolationError(f"{collection}/{doc['_id']} belongs to another run") from exc
            if self.find_one(collection, match) is None:
                raise
            return False  # a concurrent writer in this run inserted it first
        return result.upserted_id is not None

    def _stamp(self, doc: Mapping) -> dict:
        if doc.get("run_id", self.run_id) != self.run_id:
            raise RunIsolationError(f"run {self.run_id!r} cannot write a document for run {doc['run_id']!r}")
        return {**doc, "run_id": self.run_id}
