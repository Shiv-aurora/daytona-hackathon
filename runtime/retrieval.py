"""Time-safe retrieval: whatever a search backend returns, a run only ever sees its own past."""

from __future__ import annotations

from interfaces import event_visible_to_run
from runtime.ports import RetrievalPort


def retrieve(port: RetrievalPort | None, run_id: str, scenario_id: str, query: str, as_of_ts: float,
             limit: int) -> tuple[list[dict], list[str]]:
    """Events the run could have seen by `as_of_ts`, plus the ids of anything the backend leaked."""
    if port is None or not query.strip():
        return [], []
    safe, leaked = [], []
    for event in port.search_events(run_id, scenario_id, query, as_of_ts, limit):
        if _visible(event, run_id, scenario_id) and event.get("ts", float("inf")) <= as_of_ts:
            safe.append(event)
        else:
            leaked.append(str(event.get("_id")))
    return safe[:limit], leaked


def _visible(event: dict, run_id: str, scenario_id: str) -> bool:
    try:
        return event_visible_to_run(event, run_id, scenario_id)
    except KeyError:
        return False
