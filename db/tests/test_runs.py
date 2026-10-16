import pytest

from db.checkpoint import StateTooLarge
from db.events import LateEventError, record_event
from db.runs import load_run_state, run_cursor, save_run_state
from db.scope import RunIsolationError, RunScope


def state(tick, cursor_ts=None, cursor_id=None, run_id="run-a"):
    """A graph_state.GraphState after `tick` completed ticks."""
    return {"run_id": run_id, "scenario_id": "s1", "tick": tick, "now_ts": 10.0 + 24 * tick, "cursor_ts": cursor_ts,
            "cursor_id": cursor_id, "pending_proposal_ids": [], "pending_call_ids": [], "policy_version": 0}


def test_resume_starts_from_the_last_saved_tick(database):
    assert load_run_state(database, "run-a") is None and run_cursor(database, "run-a") is None
    assert save_run_state(database, state(1, 20.0, "s1_e_002"))
    assert save_run_state(database, state(2, 40.0, "s1_e_005"))
    assert load_run_state(database, "run-a") == state(2, 40.0, "s1_e_005")
    assert run_cursor(database, "run-a") == (40.0, "s1_e_005")


def test_a_stale_writer_cannot_rewind_the_cursor(database):
    assert save_run_state(database, state(2, 40.0, "s1_e_005"))
    # The process that crashed comes back and saves the tick it finished before crashing.
    assert not save_run_state(database, state(1, 20.0, "s1_e_002"))
    assert not save_run_state(database, state(2, 40.0, "s1_e_005"))  # re-saving the same tick is a no-op
    assert run_cursor(database, "run-a") == (40.0, "s1_e_005")


def test_run_states_are_isolated_and_small(database):
    assert save_run_state(database, state(3, 60.0, "s1_e_009", run_id="run-a"))
    assert load_run_state(database, "run-b") is None
    assert save_run_state(database, state(1, 20.0, "s1_e_002", run_id="run-b"))
    assert run_cursor(database, "run-a") == (60.0, "s1_e_009")
    with pytest.raises(RunIsolationError):
        save_run_state(database, state(4, run_id="scenario"))
    with pytest.raises(StateTooLarge):
        save_run_state(database, {**state(4), "households": ["x" * 40_000]})


def test_a_run_event_behind_the_cursor_is_refused_not_silently_lost(database):
    run = RunScope(database, "run-a")
    save_run_state(database, state(2, 40.0, "s1_e_005"))
    result = {"_id": "call-1:result", "run_id": "run-a", "scenario_id": "s1", "ts": 40.0,
              "source": "call_result", "text": "Resident answered."}
    with pytest.raises(LateEventError):  # (40.0, "call-1:result") sorts before the cursor: never read
        record_event(run, result)
    assert record_event(run, {**result, "ts": 40.5})
    assert not record_event(run, {**result, "ts": 40.5})  # replaying the write is a no-op...
    save_run_state(database, state(3, 40.5, "call-1:result"))
    assert not record_event(run, {**result, "ts": 40.5})  # ...even after the cursor has passed it
    assert record_event(RunScope.scenario(database), {**result, "_id": "s1_e_003", "run_id": "scenario"})
