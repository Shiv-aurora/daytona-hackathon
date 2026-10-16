"""The runtime checkpoints the shared `graph_state.GraphState`: one canonical shape.

Only the clock, the event cursor, ids of work in flight and the policy version live here.
Households, promises and proposals stay behind the memory interface, so a checkpoint stays tiny
and cannot go stale against the DB.
"""

from __future__ import annotations

from graph_state import GraphState

RuntimeState = GraphState
STATE_KEYS = frozenset(GraphState.__annotations__)
ID_LIST_KEYS = frozenset({"pending_proposal_ids", "pending_call_ids"})
_SCALARS = (str, int, float, type(None))


def new_run_state(run_id: str, start_ts: float, scenario_id: str) -> GraphState:
    return GraphState(run_id=run_id, scenario_id=scenario_id, tick=0, now_ts=float(start_ts), cursor_ts=None,
                      cursor_id=None, pending_proposal_ids=[], pending_call_ids=[], policy_version=0)


def assert_small_state(state: dict) -> None:
    """Reject anything but GraphState's fields: scalars, plus two lists of ids."""
    if set(state) != STATE_KEYS:
        raise ValueError(f"runtime state keys must be exactly {sorted(STATE_KEYS)}, got {sorted(state)}")
    bulky = sorted(key for key, value in state.items()
                   if not isinstance(value, _SCALARS)
                   and not (key in ID_LIST_KEYS and isinstance(value, list)
                            and all(isinstance(item, str) for item in value)))
    if bulky:
        raise ValueError(f"runtime state must hold only scalars and id lists; offending keys: {bulky}")
