"""LLM response cache, so a replayed tick (or CI) gets the same model answer as the first run.

Keys are the caller's hash of model + prompt, so the cache is shared across runs: the same prompt
gets the same answer, and a prompt only ever contains what its own run could see.
"""

from __future__ import annotations

from collections.abc import Mapping

from db.bootstrap import LLM_CACHE


def llm_cache_get(db, key: str) -> dict | None:
    doc = db[LLM_CACHE].find_one({"_id": key})
    return None if doc is None else doc["value"]


def llm_cache_put(db, key: str, value: Mapping) -> bool:
    """Store an answer once. The first answer wins, so a replayed or racing call can't change it."""
    if not isinstance(key, str) or not key:
        raise ValueError("an LLM cache key must be a non-empty string")
    result = db[LLM_CACHE].update_one({"_id": key}, {"$setOnInsert": {"value": dict(value)}}, upsert=True)
    return result.upserted_id is not None
