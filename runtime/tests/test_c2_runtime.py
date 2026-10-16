import json
import re

import pytest

from graph_state import GraphState
from runtime import CachedLLM, Runtime, new_run_state
from runtime.policy import LEAD_HOURS_BOUNDS
from runtime.tests.fakes import InMemoryMemory, ScriptedLLM, StubCalls, phrase_safety
from schemas import SCENARIO_RUN_ID

DAY0 = "2021-09-01T20:00:00"  # Scenario 1's day 0
CHEN_NOTE = ("Visited Mrs. Chen, 82, at 41-22 41st Ave. Basement flooded. Her son Wei is coming Tuesday to help "
             "clean out and take her to stay with him.")
SON_ARRIVED = "Back at 41-22 41st Ave: Mrs. Chen's son arrived, packing her things."
DELAY = "Con Edison outage update: restoration on 41st Ave delayed. New estimate: Sep 13 or later."
HOUSEHOLDS = {(run_id, "hh-chen"): {"name": "Mrs. Chen", "address": "41-22 41st Ave"} for run_id in ("run-a", "run-b")}


def event(event_id, ts, text, run_id=SCENARIO_RUN_ID, **extra):
    return {"_id": event_id, "run_id": run_id, "scenario_id": "s1", "ts": ts, "source": "visit_note", "text": text,
            **extra}


def chen_model(prompt):
    """Scripted OpenRouter answers: what a model would say about the Mrs. Chen notes."""
    if prompt.startswith("Note written"):
        if "son Wei is coming Tuesday" in prompt:
            return json.dumps({"promises": [{"who": "son Wei", "what": "take her to stay with him",
                                             "due_date": "2021-09-07"}], "kept_promise_ids": []})
        kept = re.findall(r"- (promise-[0-9a-f]+):", prompt) if "arrived" in prompt else []
        return json.dumps({"promises": [], "kept_promise_ids": kept})
    return json.dumps({"cited_event_ids": re.findall(r"- (e-[\w-]+) \(", prompt), "suggested_action": "call",
                       "rationale": "Crew found no one home and the power restoration slipped again."})


def make(*events, llm=None, opt_in=True, retrieval="memory"):
    memory = InMemoryMemory(HOUSEHOLDS, registry={"hh-chen": {"opt_in": opt_in}})
    memory.events.extend(events)
    runtime = Runtime(memory, StubCalls(), DAY0, tick_hours=6.0, llm=llm, safety=phrase_safety, ledger=memory,
                      retrieval=memory if retrieval == "memory" else retrieval)
    return runtime, memory


def start(run_id="run-a", ts=0.0):
    return new_run_state(run_id, ts, "s1")


def check_ins(memory):
    """Promise check-ins only (silence follow-ups are covered in test_c2_goal.py)."""
    return [p for p in memory.proposals.values() if p["kind"] == "check_in"]


def test_the_checkpoint_is_the_shared_graph_state_and_tracks_work_in_flight():
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE))
    state = runtime.run(start(), until_ts=150.0)  # "Tuesday" (hour 144) has passed
    assert set(state) == set(GraphState.__annotations__)
    [check_in] = check_ins(memory)
    assert check_in["_id"] in state["pending_proposal_ids"]
    assert state["pending_call_ids"] == [] and state["cursor_id"] == "e-chen"

    memory.proposals[check_in["_id"]]["status"] = "approved"  # the coordinator approves in the UI
    state = runtime.tick(state)
    assert check_in["_id"] not in state["pending_proposal_ids"] and len(state["pending_call_ids"]) == 1


def test_the_model_path_tracks_the_promise_the_way_a_person_would():
    followup = event("e-back", 120.0, SON_ARRIVED)
    llm = ScriptedLLM(chen_model)
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), followup, llm=llm)
    runtime.run(start(), until_ts=200.0)
    [promise] = memory.promises.values()
    assert promise["text"] == "son Wei: take her to stay with him" and promise["due_ts"] == 144.0
    assert promise["status"] == "kept" and check_ins(memory) == []  # "son arrived" kept it: no false alarm

    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), followup)  # regex fallback only
    runtime.run(start(), until_ts=200.0)
    assert [p["status"] for p in memory.promises.values()] == ["lapsed"]  # no shared words, so it lapses


def test_an_emergency_is_escalated_before_any_model_sees_the_note():
    llm = ScriptedLLM(chen_model)
    note = "Mrs. Chen at 41-22 41st Ave: neighbor says she fell, her son will come tomorrow."
    runtime, memory = make(event("e-fell", 50.0, note), llm=llm)
    runtime.run(start(), until_ts=54.0)
    [escalation] = [p for p in memory.proposals.values() if p["kind"] == "emergency"]
    assert escalation["urgent"] and escalation["queue"] == "urgent_human" and escalation["household_id"] == "hh-chen"
    assert escalation["cited_event_ids"] == ["e-fell"] and escalation["ts"] == 50.0
    assert llm.prompts == [] and "emergency_escalated" in memory.actions("run-a")
    with pytest.raises(ValueError, match="safety"):
        Runtime(memory, StubCalls(), DAY0, llm=llm)  # no model path without the emergency check


def test_bad_or_missing_model_output_falls_back_to_the_regex_path():
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), llm=ScriptedLLM(lambda prompt: "I can't help."))
    runtime.run(start(), until_ts=48.0)
    [promise] = memory.promises.values()
    assert promise["due_ts"] == 144.0 and "coming Tuesday" in promise["text"]
    assert "llm_output_rejected" in memory.actions("run-a")

    offline = CachedLLM(InMemoryMemory(), model="anthropic/claude-sonnet-5")  # no key and an empty cache
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), llm=offline)
    runtime.run(start(), until_ts=48.0)
    assert len(memory.promises) == 1 and "llm_unavailable" in memory.actions("run-a")


def test_decisions_cite_only_time_safe_evidence_and_calls_need_opt_in():
    delay = event("e-delay", 100.0, DELAY, source="utility")
    future = event("e-future", 400.0, "Con Edison: power restored on 41st Ave.", source="utility")
    other_run = event("e-other", 90.0, "Relay call to 41-22 41st Ave: no answer.", run_id="run-b",
                      source="call_result")

    class LeakyIndex:  # a search backend that ignores both the run and the clock
        def __init__(self):
            self.cutoffs = []

        def search_events(self, run_id, scenario_id, query, as_of_ts, limit):
            self.cutoffs.append(as_of_ts)
            return [delay, future, other_run]

    llm, index = ScriptedLLM(chen_model), LeakyIndex()
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), delay, future, other_run, llm=llm, opt_in=False,
                           retrieval=index)
    runtime.run(start(), until_ts=150.0)
    [proposal] = memory.proposals.values()
    assert proposal["cited_event_ids"] == ["e-chen", "e-delay"]  # never the future or another run's event
    assert proposal["suggested_action"] == "visit"  # the model said call, but there is no opt-in
    assert proposal["rationale"].startswith("Crew found no one home")
    assert index.cutoffs == [150.0]  # the request carried the simulated-time cutoff
    [filtered] = [e for e in memory.system_events.values() if e["action"] == "retrieval_filtered"]
    assert filtered["dropped_event_ids"] == ["e-future", "e-other"]
    assert not any("e-future" in prompt or "e-other" in prompt for prompt in llm.prompts)


def test_missed_promises_move_the_policy_and_later_check_ins_come_early():
    runtime, memory = make(
        event("e-1", 1.0, "Mrs. Chen at 41-22 41st Ave: her son will bring water tomorrow."),
        event("e-2", 2.0, "Mrs. Chen at 41-22 41st Ave: Red Cross will drop off a cleaning kit tomorrow."),
        event("e-3", 40.0, "Mrs. Chen at 41-22 41st Ave: the super will fix the boiler within 20 hours."),
    )
    before = runtime.run(start(), until_ts=18.0)
    after = runtime.tick(before)  # hour 24: the first daily review, with two promises missed
    assert runtime.tick(before) == after and len(memory.policy_changes) == 1  # a replay changes nothing
    [first] = memory.policy_changes.values()
    assert first["what_changed"] == "lead_hours 0 -> 12 (promises_on_time_pct 0 < 90)" and first["ts"] == 24.0
    assert first["metric_values"]["promises_due"] == 2.0 and first["metric_values"]["promises_on_time_pct"] == 0.0
    assert after["policy_version"] == 1

    state = runtime.run(after, until_ts=36.0)  # hour 30: both missed promises got their check-ins
    for proposal in memory.proposals_with_status("run-a", "pending"):
        memory.decide("run-a", proposal["_id"], "approved", 36.0)  # the coordinator takes them on
    state = runtime.run(state, until_ts=72.0)
    [early] = [p for p in memory.proposals.values() if p["early"]]
    assert early["ts"] < early["due_ts"] == 60.0  # the boiler promise got a check-in before it fell due
    changes = memory.policy_changes.values()
    assert state["policy_version"] == len(changes)
    assert all(LEAD_HOURS_BOUNDS[0] <= c["params"]["lead_hours"] <= LEAD_HOURS_BOUNDS[1] for c in changes)
    goal = [m for m in memory.metrics.values() if m["scope"] == "goal" and m["name"] == "promises_on_time_pct"]
    assert [m["ts"] for m in goal] == [24.0, 48.0, 72.0]


def run_chen(llm):
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), event("e-delay", 100.0, DELAY, source="utility"),
                           llm=llm)
    state = runtime.run(start(), until_ts=160.0)
    return state, memory.promises, memory.proposals


def test_a_frozen_model_cache_replays_the_run_identically_without_a_model():
    cache, live = InMemoryMemory(), ScriptedLLM(chen_model)
    first = run_chen(CachedLLM(cache, live))
    calls = len(live.prompts)
    replay = run_chen(CachedLLM(cache, model=live.model))  # cache only: no client, no network
    assert replay == first and len(live.prompts) == calls
    [proposal] = [p for p in first[2].values() if p["kind"] == "check_in"]
    assert proposal["cited_event_ids"] == ["e-chen", "e-delay"]


def test_tokens_are_accounted_per_tick_and_cached_answers_cost_nothing():
    llm = ScriptedLLM(chen_model, prompt_tokens=120, completion_tokens=30)
    runtime, memory = make(event("e-chen", 42.6, CHEN_NOTE), llm=CachedLLM(InMemoryMemory(), llm))
    runtime.tick(start(ts=40.0))  # reads the note: one live model call
    runtime.tick(start(ts=40.0))  # replayed: served from the cache
    usage = {m["name"]: m["value"] for m in memory.metrics.values() if m["scope"] == "tick"}
    assert usage == {"llm_calls": 1.0, "llm_cached_calls": 0.0, "llm_prompt_tokens": 120.0,
                     "llm_completion_tokens": 30.0, "llm_cost_usd": 0.0}
    [call] = [e for e in memory.system_events.values() if e["action"] == "llm_call"]
    assert (call["prompt_tokens"], call["cached"], len(llm.prompts)) == (120, False, 1)
