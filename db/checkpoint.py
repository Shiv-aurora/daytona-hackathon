"""Small-state bounds for the offline runtime checkpoint records."""

from __future__ import annotations

import json
from typing import Any

from db.scope import require_run_id

CHECKPOINTS = "checkpoints"
CHECKPOINT_WRITES = "checkpoint_writes"
MAX_STATE_BYTES = 32 * 1024


class StateTooLarge(ValueError):
    pass


def check_small_state(values: Any, limit: int = MAX_STATE_BYTES) -> None:
    size = len(json.dumps(values, default=str, skipkeys=True))
    if size > limit:
        raise StateTooLarge(f"graph state is {size} bytes (limit {limit}); "
                            "keep household data in the database, not in graph state")


def thread_config(run_id: str) -> dict:
    """Thread config for a run: one checkpoint thread per run_id."""
    return {"configurable": {"thread_id": require_run_id(run_id)}}

