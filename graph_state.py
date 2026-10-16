"""Small runtime checkpoint state.

Database records remain the source of truth for households, promises, proposals, calls and
metrics. Do not add those documents to this state.
"""

from __future__ import annotations

from typing import TypedDict


class GraphState(TypedDict):
    run_id: str
    scenario_id: str
    tick: int
    now_ts: float
    cursor_ts: float | None
    cursor_id: str | None
    pending_proposal_ids: list[str]
    pending_call_ids: list[str]
    policy_version: int
