import copy
from datetime import date

import pytest

from runtime import Runtime, assert_small_state, new_run_state
from runtime.loop import TickFailed
from runtime.state import STATE_KEYS
from runtime.tests.fakes import InMemoryMemory, StubCalls
from schemas import SCENARIO_RUN_ID

DAY = 24.0
DAY0 = date(2026, 9, 28)  # a Monday; simulated hour 0 is its midnight
START = 10.0  # the run starts Monday 10:00, so daily ticks land at 10:00
PROMISE = "Visit note: Mrs. Chen at 41 Orchard St. Her landlord promised to fix the boiler by Thursday."
FIXED = "Mrs. Chen at 41 Orchard St: the boiler was fixed."
CHEN = {"name": "Mrs. Chen", "address": "41 Orchard St"}
HOUSEHOLDS = {
    **{(run_id, "hh-chen"): CHEN for run_id in ("run-a", "run-b", "relay-1", "baseline-1")},
    ("run-a", "hh-alvarez"): {"name": "Mr. Alvarez", "address": "9 Pike St"},
}


def event(event_id, ts, text, run_id=SCENARIO_RUN_ID, scenario_id="s1", **extra):
    """A scenario input by default; pass the active run_id for a run-generated event."""
    return {"_id": event_id, "run_id": run_id, "scenario_id": scenario_id, "ts": ts, "source": "visit_note",
            "text": text, **extra}


def make(*events, opt_in=True):
    memory = InMemoryMemory(HOUSEHOLDS, registry={"hh-chen": {"opt_in": opt_in}})
    memory.events.extend(events)
    calls = StubCalls()
    return Runtime(memory, calls, DAY0, tick_hours=DAY), memory, calls


def snapshot(memory):
    return copy.deepcopy((memory.promises, memory.proposals, memory.system_events))


def consumed(memory, run_id):
    """Ids of the events a run applied to a household, i.e. the events it actually consumed."""
    return {event_id for rid, _, event_id in memory.applied if rid == run_id}


def test_lapsed_promise_becomes_exactly_one_proposal():
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE))
    state = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 3 * DAY)  # Thu 10:00
    [promise] = memory.promises.values()
    assert promise["household_id"] == "hh-chen" and promise["status"] == "open"
    assert memory.proposals == {}  # "by Thursday" has not passed yet

    state = runtime.run(state, until_ts=START + 10 * DAY)  # the deadline passes on Friday's tick
    [proposal] = memory.proposals.values()
    assert proposal["household_id"] == "hh-chen" and proposal["kind"] == "check_in"
    assert proposal["status"] == "pending" and proposal["promise_id"] == promise["_id"]
    assert proposal["cited_event_ids"] == ["ev-1"] and proposal["ts"] == START + 4 * DAY
    assert promise["status"] == "lapsed"
    actions = memory.actions("run-a")
    assert actions.count("promise_created") == 1 and actions.count("proposal_created") == 1
    assert state["tick"] == 10 and state["cursor_id"] == "ev-1"


def test_replaying_a_tick_does_not_duplicate_the_proposal():
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE))
    before = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 3 * DAY)
    after = runtime.tick(before)  # the tick where the deadline passes
    assert len(memory.proposals) == 1
    written = snapshot(memory)

    assert runtime.tick(before) == after  # same tick replayed from its checkpointed starting state
    runtime.tick(new_run_state("run-a", START, "s1"))  # replay the tick that ingested the promise too
    assert snapshot(memory) == written


def test_crash_between_proposal_and_status_write_is_healed_by_replay(monkeypatch):
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE))
    before = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 3 * DAY)

    def crash(*args):
        raise ConnectionError("simulated crash before the status write")

    monkeypatch.setattr(memory, "set_promise_status", crash)
    with pytest.raises(TickFailed, match="watching promises") as failure:
        runtime.tick(before)
    assert isinstance(failure.value.__cause__, ConnectionError)
    assert len(memory.proposals) == 1  # the proposal landed; the checkpoint never advanced
    monkeypatch.undo()

    runtime.tick(before)
    [promise] = memory.promises.values()
    assert len(memory.proposals) == 1 and promise["status"] == "lapsed"


def test_kept_promise_never_lapses_but_a_denial_does_not_count():
    kept = "Mrs. Chen at 41 Orchard St: the boiler was fixed this morning."
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE), event("ev-2", START + DAY + 1, kept))
    runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 7 * DAY)
    assert [p["status"] for p in memory.promises.values()] == ["kept"] and memory.proposals == {}

    denied = "Mrs. Chen says the landlord still hasn't fixed the boiler."
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE), event("ev-2", START + DAY + 1, denied))
    runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 7 * DAY)
    assert [p["status"] for p in memory.promises.values()] == ["lapsed"] and len(memory.proposals) == 1


def test_unknown_household_creates_nothing_and_is_traced():
    runtime, memory, _ = make(event("ev-9", START + 1, "Mr. Nobody at 7 Elm St promised to call by Friday."))
    runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 7 * DAY)
    assert memory.promises == {} and memory.proposals == {}
    assert "household_unmatched" in memory.actions("run-a")


@pytest.mark.parametrize("opt_in", [True, False])
def test_approved_proposal_schedules_one_call_only_with_opt_in(opt_in):
    runtime, memory, calls = make(event("ev-1", START + 1, PROMISE), opt_in=opt_in)
    state = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 4 * DAY)
    [proposal] = memory.proposals.values()
    assert calls.requests == {}  # nothing is queued before a human approves

    proposal["status"] = "approved"  # the UI's Approve button, persisted by W2
    after = runtime.tick(state)
    runtime.tick(state)  # replay
    runtime.tick(after)  # a later tick
    if opt_in:
        [request] = calls.requests.values()
        assert request["household_id"] == "hh-chen" and request["proposal_id"] == proposal["_id"]
    else:
        assert calls.requests == {} and "call_skipped_no_opt_in" in memory.actions("run-a")


def test_run_consumes_matching_scenario_inputs():
    other_scenario = event("ev-s2", START + 1, PROMISE, scenario_id="s2")
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE), other_scenario)
    state = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + DAY)
    assert consumed(memory, "run-a") == {"ev-1"} and state["cursor_id"] == "ev-1"
    [promise] = memory.promises.values()
    assert promise["run_id"] == "run-a" and promise["source_event_id"] == "ev-1"


def test_run_consumes_its_own_generated_events():
    runtime, memory, _ = make(event("ev-a", START + 1, PROMISE, run_id="run-a"))
    state = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + DAY)
    assert consumed(memory, "run-a") == {"ev-a"} and state["cursor_id"] == "ev-a"
    [promise] = memory.promises.values()
    assert promise["run_id"] == "run-a" and promise["source_event_id"] == "ev-a"


def test_run_never_sees_another_runs_generated_events():
    runtime, memory, _ = make(event("ev-b", START + 1, PROMISE, run_id="run-b"))
    state = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 7 * DAY)
    assert consumed(memory, "run-a") == set() and state["cursor_id"] is None
    assert memory.promises == {} and memory.proposals == {}


def test_baseline_never_sees_relay_generated_events():
    relay_call = event("ev-call", START + 2, "resident: the boiler is fixed", run_id="relay-1",
                       source="call_result", household_id="hh-chen")
    relay_note = event("ev-note", START + 3, FIXED, run_id="relay-1")
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE), relay_call, relay_note)
    for run_id in ("relay-1", "baseline-1"):
        runtime.run(new_run_state(run_id, START, "s1"), until_ts=START + 7 * DAY)

    assert consumed(memory, "relay-1") == {"ev-1", "ev-call", "ev-note"}
    assert consumed(memory, "baseline-1") == {"ev-1"}  # the shared scenario input only
    # Relay's own note kept its promise; the baseline never saw that note, so its copy lapsed.
    assert {p["run_id"]: p["status"] for p in memory.promises.values()} == {
        "relay-1": "kept", "baseline-1": "lapsed"}
    assert {p["run_id"] for p in memory.proposals.values()} == {"baseline-1"}


def test_future_events_wait_for_the_time_cursor():
    later_input = event("ev-late", START + 2 * DAY + 1, FIXED)
    later_own = event("ev-late-own", START + 2 * DAY + 2, "Mrs. Chen at 41 Orchard St: checked in by phone.",
                      run_id="run-a")
    runtime, memory, _ = make(event("ev-1", START + 1, PROMISE), later_input, later_own)
    state = runtime.tick(new_run_state("run-a", START, "s1"))  # clock: Tuesday 10:00
    assert consumed(memory, "run-a") == {"ev-1"} and state["cursor_id"] == "ev-1"
    state = runtime.tick(state)  # Wednesday 10:00: both later events are still in the future
    assert consumed(memory, "run-a") == {"ev-1"} and state["cursor_id"] == "ev-1"
    state = runtime.tick(state)  # Thursday 10:00
    assert consumed(memory, "run-a") == {"ev-1", "ev-late", "ev-late-own"}
    assert state["cursor_id"] == "ev-late-own"


@pytest.mark.parametrize("leaked", [
    event("ev-b", START + 1, PROMISE, run_id="run-b"),  # another run's generated event
    event("ev-s2", START + 1, PROMISE, scenario_id="s2"),  # another scenario's input
])
def test_an_event_from_another_run_is_refused(leaked):
    class LeakyMemory(InMemoryMemory):
        def events_after(self, run_id, scenario_id, after, until_ts, limit):
            return [e for e in self.events if e["ts"] <= until_ts]  # ignores run and scenario

    memory = LeakyMemory(HOUSEHOLDS)
    memory.events.append(leaked)
    with pytest.raises(RuntimeError, match="run isolation"):
        Runtime(memory, StubCalls(), DAY0, tick_hours=DAY).tick(new_run_state("run-a", START, "s1"))
    assert memory.promises == {} and memory.applied == set()


def test_state_stays_small_and_household_free():
    runtime, _, _ = make(event("ev-1", START + 1, PROMISE))
    state = runtime.run(new_run_state("run-a", START, "s1"), until_ts=START + 7 * DAY)
    assert set(state) == STATE_KEYS
    assert_small_state(state)
    assert "hh-chen" not in repr(state) and "boiler" not in repr(state)
    with pytest.raises(ValueError):
        runtime.tick({**state, "households": {"hh-chen": {"name": "Mrs. Chen"}}})
    with pytest.raises(ValueError):
        runtime.tick({**state, "scenario_id": {"household": "hh-chen"}})
    with pytest.raises(ValueError):
        runtime.tick({**state, "scenario_id": None})  # a run must know which scenario it reads
