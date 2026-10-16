"""In-memory stand-in for the slice of the reference store W2 uses, so tests and CI need no service secret.

Supported: equality filters (with array membership and dotted paths), $ne, $in, $gt/$gte/$lt/$lte,
top-level $or, the $set/$setOnInsert/$push/$max update operators, upserts, sort, limit and
unique indexes. Anything else raises NotImplementedError instead of silently diverging from the reference store.
"""

from __future__ import annotations

import copy
import itertools
import operator
from dataclasses import dataclass
from typing import Any

_MISSING = object()
_UPDATE_OPERATORS = ("$set", "$setOnInsert", "$push", "$max")
_COMPARISONS = {"$gt": operator.gt, "$gte": operator.ge, "$lt": operator.lt, "$lte": operator.le}


class DuplicateKeyError(Exception):
    code = 11000  # same code as the duplicate-key exception


class IndexConflict(Exception):
    """the reference store's IndexOptionsConflict (85) or IndexKeySpecsConflict (86)."""

    def __init__(self, code: int, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class UpdateResult:
    matched_count: int
    modified_count: int
    upserted_id: Any = None


@dataclass
class InsertOneResult:
    inserted_id: Any


def _get(doc: Any, path: str) -> Any:
    for part in path.split("."):
        if not isinstance(doc, dict) or part not in doc:
            return _MISSING
        doc = doc[part]
    return doc


def _put(doc: dict, path: str, value: Any) -> None:
    *parents, last = path.split(".")
    for part in parents:
        doc = doc.setdefault(part, {})
    doc[last] = copy.deepcopy(value)


def _equals(actual: Any, expected: Any) -> bool:
    if actual is _MISSING:
        return expected is None
    if isinstance(actual, list) and not isinstance(expected, list):
        return expected in actual
    return actual == expected


def _is_operator_doc(value: Any) -> bool:
    return isinstance(value, dict) and bool(value) and all(key.startswith("$") for key in value)


def _compare(op: str, actual: Any, operand: Any) -> bool:
    # Like the reference store, missing/null and values of another type never satisfy a range comparison.
    if actual is _MISSING or actual is None or isinstance(actual, (int, float)) != isinstance(operand, (int, float)):
        return False
    return _COMPARISONS[op](actual, operand)


def _matches(doc: dict, filter: dict) -> bool:
    for path, condition in filter.items():
        if path == "$or":
            if not any(_matches(doc, branch) for branch in condition):
                return False
            continue
        if path.startswith("$"):
            raise NotImplementedError(f"query operator {path}")
        actual = _get(doc, path)
        if not _is_operator_doc(condition):
            if not _equals(actual, condition):
                return False
            continue
        for op, operand in condition.items():
            if op == "$ne":
                ok = not _equals(actual, operand)
            elif op == "$in":
                ok = any(_equals(actual, item) for item in operand)
            elif op in _COMPARISONS:
                ok = _compare(op, actual, operand)
            else:
                raise NotImplementedError(f"query operator {op}")
            if not ok:
                return False
    return True


def _apply(doc: dict, update: dict, inserting: bool) -> None:
    paths = [path for fields in update.values() for path in fields]
    for a, b in itertools.combinations(paths, 2):
        if a == b or a.startswith(b + ".") or b.startswith(a + "."):
            raise ValueError(f"updating {a!r} and {b!r} together would conflict")
    for op, fields in update.items():
        if op not in _UPDATE_OPERATORS:
            raise NotImplementedError(f"update operator {op}")
        if op == "$setOnInsert" and not inserting:
            continue
        for path, value in fields.items():
            current = _get(doc, path)
            if op == "$push" and current is not _MISSING:
                current.append(copy.deepcopy(value))
            elif op == "$push":
                _put(doc, path, [value])
            elif op != "$max" or current is _MISSING or value > current:
                _put(doc, path, value)


def _index_value(doc: dict, path: str) -> Any:
    value = _get(doc, path)
    return None if value is _MISSING else value  # the reference store indexes a missing field as null


def _sort_key(value: Any) -> tuple:
    return (0, 0) if value is _MISSING or value is None else (1, value)


class FakeCollection:
    def __init__(self) -> None:
        self.docs: dict[Any, dict] = {}
        self.indexes: dict[str, dict] = {"_id_": {"key": [("_id", 1)]}}
        self._next_id = itertools.count(1)

    def create_index(self, keys: list, name: str | None = None, **options: Any) -> str:
        keys = list(keys)
        name = name or "_".join(f"{field}_{direction}" for field, direction in keys)
        for other_name, spec in self.indexes.items():  # the reference store's rules for existing indexes
            same_keys = spec["key"] == keys
            if other_name == name and not same_keys:
                raise IndexConflict(86, f"an index named {name!r} already exists with different keys")
            if other_name == name and {k: v for k, v in spec.items() if k != "key"} != options:
                raise IndexConflict(85, f"an index named {name!r} already exists with different options")
            if other_name == name:
                return name
            if same_keys:
                raise IndexConflict(85, f"index {other_name!r} already has these keys under a different name")
        self.indexes[name] = {"key": keys, **options}
        return name

    def index_information(self) -> dict:
        return copy.deepcopy(self.indexes)

    def find(self, filter: dict | None = None, sort: list | None = None, limit: int = 0) -> list[dict]:
        docs = [copy.deepcopy(doc) for doc in self.docs.values() if _matches(doc, filter or {})]
        for path, direction in reversed(sort or []):
            docs.sort(key=lambda doc: _sort_key(_get(doc, path)), reverse=direction < 0)
        return docs[:limit] if limit else docs  # limit=0 means no limit, as in the reference store

    def find_one(self, filter: dict | None = None) -> dict | None:
        found = self.find(filter)
        return found[0] if found else None

    def count_documents(self, filter: dict) -> int:
        return len(self.find(filter))

    def insert_one(self, doc: dict) -> InsertOneResult:
        return InsertOneResult(self._store(copy.deepcopy(dict(doc))))

    def update_one(self, filter: dict, update: dict, upsert: bool = False) -> UpdateResult:
        for doc_id, doc in self.docs.items():
            if _matches(doc, filter):
                updated = copy.deepcopy(doc)
                _apply(updated, update, inserting=False)
                if updated == doc:
                    return UpdateResult(1, 0)
                self._store(updated, replacing=doc_id)
                return UpdateResult(1, 1)
        if not upsert:
            _apply({}, update, inserting=False)  # the reference store validates the update even when nothing matches
            return UpdateResult(0, 0)
        doc: dict = {}
        for path, condition in filter.items():
            if not path.startswith("$") and not _is_operator_doc(condition):
                _put(doc, path, condition)
        _apply(doc, update, inserting=True)
        return UpdateResult(0, 0, self._store(doc))

    def _store(self, doc: dict, replacing: Any = _MISSING) -> Any:
        doc.setdefault("_id", f"fake-{next(self._next_id)}")
        for other_id, other in self.docs.items():
            if other_id == replacing:
                continue
            if other_id == doc["_id"]:
                raise DuplicateKeyError(f"duplicate _id {other_id!r}")
            for name, index in self.indexes.items():
                fields = [field for field, _ in index["key"]]
                if index.get("unique") and all(_index_value(other, f) == _index_value(doc, f) for f in fields):
                    raise DuplicateKeyError(f"duplicate key for index {name}")
        self.docs[doc["_id"]] = doc
        return doc["_id"]


class FakeDatabase:
    """Collections appear on first use, as in the reference store."""

    def __init__(self) -> None:
        self._collections: dict[str, FakeCollection] = {}

    def __getitem__(self, name: str) -> FakeCollection:
        return self._collections.setdefault(name, FakeCollection())
