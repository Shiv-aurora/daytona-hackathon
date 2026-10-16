import pytest

from db.cache import llm_cache_get, llm_cache_put
from db.events import record_event, search_events
from db.scope import RunIsolationError, RunScope, stable_id


def event(_id, ts, text, run_id="scenario", scenario_id="s1"):
    return {"_id": _id, "run_id": run_id, "scenario_id": scenario_id, "ts": ts, "source": "visit_note", "text": text}


@pytest.fixture
def stream(database):
    inputs = RunScope.scenario(database)
    record_event(inputs, event("e1", 1.0, "Landlord promised to fix the broken boiler by Thursday."))
    record_event(inputs, event("e2", 2.0, "Street flooding reported near the subway entrance."))
    record_event(inputs, event("e3", 50.0, "The boiler is still not fixed and the apartment is freezing."))
    record_event(inputs, event("s2-e1", 1.0, "Another scenario's broken boiler.", scenario_id="s2"))
    record_event(RunScope(database, "relay-1"), event("r1", 3.0, "Resident says the boiler is broken again.", "relay-1"))
    record_event(RunScope(database, "baseline-1"), event("b1", 3.0, "Baseline's own boiler note.", "baseline-1"))
    return database


def ids(events):
    return [event["_id"] for event in events]


def test_search_ranks_what_the_run_could_see(stream):
    assert ids(search_events(stream, "relay-1", "s1", "boiler broken", as_of_ts=10.0, limit=5)) == ["e1", "r1"]
    assert ids(search_events(stream, "relay-1", "s1", "boiler broken", as_of_ts=10.0, limit=1)) == ["e1"]


def test_search_never_returns_future_events(stream):
    assert "e3" not in ids(search_events(stream, "relay-1", "s1", "boiler fixed", as_of_ts=49.9, limit=10))
    assert "e3" in ids(search_events(stream, "relay-1", "s1", "boiler fixed", as_of_ts=50.0, limit=10))


def test_the_baseline_never_retrieves_relay_generated_events(stream):
    found = ids(search_events(stream, "baseline-1", "s1", "boiler broken again", as_of_ts=100.0, limit=10))
    assert "r1" not in found and {"e1", "e3", "b1"} <= set(found)
    with pytest.raises(RunIsolationError):
        search_events(stream, "scenario", "s1", "boiler", as_of_ts=100.0, limit=10)


def test_an_empty_query_or_limit_finds_nothing(stream):
    assert search_events(stream, "relay-1", "s1", "   ", as_of_ts=100.0, limit=5) == []
    assert search_events(stream, "relay-1", "s1", "boiler", as_of_ts=100.0, limit=0) == []


def test_the_first_cached_llm_answer_wins(database):
    key = stable_id("llm", "some-model", 256, '[{"role": "user", "content": "..."}]')
    assert llm_cache_get(database, key) is None
    assert llm_cache_put(database, key, {"text": "first", "prompt_tokens": 12})
    assert not llm_cache_put(database, key, {"text": "second", "prompt_tokens": 12})
    assert llm_cache_get(database, key) == {"text": "first", "prompt_tokens": 12}
