import pytest

from db.bootstrap import EVENTS
from db.events import events_after, record_event
from db.scope import RunIsolationError, RunScope
from interfaces import event_visible_to_run


def event(_id, ts, run_id="scenario", scenario_id="s1", **fields):
    return {"_id": _id, "run_id": run_id, "scenario_id": scenario_id, "ts": ts, "source": "311",
            "text": f"event {_id}", **fields}


def ids(events):
    return [event["_id"] for event in events]


@pytest.fixture
def stream(database):
    """Scenario inputs for s1 and s2, plus one generated event each for a Relay and a baseline run."""
    inputs = RunScope.scenario(database)
    for doc in (event("s1_e_001", 1.0), event("s1_e_002", 2.0), event("s1_e_003", 2.0),
                event("s1_e_004", 30.0), event("s2_e_001", 1.5, scenario_id="s2")):
        assert record_event(inputs, doc)
    assert record_event(RunScope(database, "relay-1"),
                        event("relay-1:call-1:result", 2.5, run_id="relay-1", source="call_result"))
    assert record_event(RunScope(database, "baseline-1"), event("baseline-1:note-1", 2.5, run_id="baseline-1"))
    return database


def test_a_run_sees_its_scenario_inputs_plus_its_own_events(stream):
    events = events_after(stream, "relay-1", "s1", None, until_ts=10.0, limit=100)
    assert ids(events) == ["s1_e_001", "s1_e_002", "s1_e_003", "relay-1:call-1:result"]
    assert all(event_visible_to_run(event, "relay-1", "s1") for event in events)


def test_the_baseline_never_sees_relay_generated_events(stream):
    events = events_after(stream, "baseline-1", "s1", None, until_ts=10.0, limit=100)
    assert ids(events) == ["s1_e_001", "s1_e_002", "s1_e_003", "baseline-1:note-1"]


def test_another_runs_events_are_neither_visible_nor_writable(stream):
    other = RunScope(stream, "relay-2")
    assert ids(events_after(stream, "relay-2", "s1", None, 10.0, 100)) == ["s1_e_001", "s1_e_002", "s1_e_003"]
    with pytest.raises(RunIsolationError):  # stamped for another run
        record_event(other, event("relay-2:note", 3.0, run_id="relay-1"))
    with pytest.raises(RunIsolationError):  # reusing another run's event _id
        record_event(other, event("relay-1:call-1:result", 3.0, run_id="relay-2"))
    with pytest.raises(RunIsolationError):  # a run can't publish scenario inputs
        record_event(other, event("s1_e_999", 3.0))
    with pytest.raises(RunIsolationError):  # and "scenario" is not a run to read as
        events_after(stream, "scenario", "s1", None, 10.0, 100)


def test_the_cursor_resumes_after_ties_in_ts_then_id_order(stream):
    first = events_after(stream, "relay-1", "s1", None, until_ts=10.0, limit=2)
    assert ids(first) == ["s1_e_001", "s1_e_002"]
    cursor = (first[-1]["ts"], first[-1]["_id"])  # s1_e_003 has the same ts as the cursor
    assert ids(events_after(stream, "relay-1", "s1", cursor, until_ts=10.0, limit=100)) == [
        "s1_e_003", "relay-1:call-1:result"]


def test_future_events_stay_hidden_until_their_time(stream):
    cursor = (2.5, "relay-1:call-1:result")
    assert events_after(stream, "relay-1", "s1", cursor, until_ts=29.9, limit=100) == []
    assert ids(events_after(stream, "relay-1", "s1", cursor, until_ts=30.0, limit=100)) == ["s1_e_004"]


def test_recording_an_event_twice_stores_it_once(database):
    inputs = RunScope.scenario(database)
    assert record_event(inputs, event("s1_e_001", 1.0))
    assert not record_event(inputs, event("s1_e_001", 1.0, text="edited"))
    [stored] = database[EVENTS].find({"_id": "s1_e_001"})
    assert stored["text"] == "event s1_e_001" and stored["run_id"] == "scenario"


def test_events_use_the_shared_schema_id(database):
    with pytest.raises(ValueError):
        record_event(RunScope(database, "relay-1"), {"event_id": "e1", "scenario_id": "s1", "ts": 1.0})
