import json

import pytest

from db.bootstrap import PROPOSALS, SYSTEM_EVENTS
from eval.baseline import LongContextBaseline, render_event
from eval.tests.fakes import LeakyEvents, ScriptedLLM, run_docs, shared_memory
from runtime.llm import CachedLLM
from runtime.tests.fakes import InMemoryMemory
from runtime.tests.fakes import ScriptedLLM as W1ScriptedLLM
from schemas import SCENARIO_RUN_ID, PromiseProbe, Proposal

SCENARIO, BASELINE = "scn-1", "baseline-1"
CHEN = {"name": "Mei Chen", "address": "41-22 Hollow Oak Ln"}
HOUSEHOLDS = {"hh-chen": CHEN,
              "hh-reyes-1": {"name": "Hector Reyes", "address": "92-47 Thistlewick Rd"},
              "hh-reyes-2": {"name": "Hector Reyes", "address": "75-37 Starling Hollow St"}}


def event(event_id, ts, text, name=None, address=None, run_id=SCENARIO_RUN_ID, scenario_id=SCENARIO):
    """Shaped like W5's scenario events: visible identity hints, never a household_id."""
    return {"_id": event_id, "run_id": run_id, "scenario_id": scenario_id, "ts": ts, "source": "visit_note",
            "text": text, "household_ref_raw": name, "address_raw": address}


INPUTS = [event("ev-1", 5.0, "Her son promised to bring groceries by Friday.", **CHEN),
          event("ev-2", 30.0, "Still no groceries; the fridge is empty.", **CHEN)]
RELAY_CALL = event("relay-call", 10.0, "RELAY-ONLY call transcript", run_id="relay-1")
OTHER_SCENARIO = event("other-note", 12.0, "OTHER-SCENARIO note", scenario_id="scn-2")
OWN = event("own-1", 20.0, "a note the baseline run generated", run_id=BASELINE)


def make(events=INPUTS, llm=None, every=24.0, **options):
    memory, llm = shared_memory(events, {BASELINE: HOUSEHOLDS}), llm or ScriptedLLM()
    return LongContextBaseline(memory, llm, BASELINE, SCENARIO, decision_every_hours=every, **options), memory, llm


def escalate(*items):
    return lambda prompt: json.dumps({"escalations": list(items)})


def traced(memory, action):
    return [e for e in run_docs(memory, SYSTEM_EVENTS, BASELINE, module="baseline") if e["action"] == action]


def test_baseline_reads_scenario_inputs_and_its_own_events_never_another_runs():
    baseline, _, llm = make([*INPUTS, RELAY_CALL, OTHER_SCENARIO, OWN])
    baseline.advance_to(48.0)
    assert [e["_id"] for e in baseline.log] == ["ev-1", "own-1", "ev-2"]
    prompts = "\n".join(llm.prompts)
    assert "[ev-1]" in prompts and "[own-1]" in prompts
    assert "relay-call" not in prompts and "RELAY-ONLY" not in prompts and "OTHER-SCENARIO" not in prompts


@pytest.mark.parametrize("leak", [RELAY_CALL, OTHER_SCENARIO, event("ev-future", 500.0, "has not happened yet")])
def test_baseline_refuses_whatever_a_broken_port_leaks(leak):
    llm = ScriptedLLM()
    baseline = LongContextBaseline(LeakyEvents([leak]), llm, BASELINE, SCENARIO, decision_every_hours=24.0)
    with pytest.raises(RuntimeError, match="isolation"):
        baseline.advance_to(24.0)
    assert llm.prompts == [] and baseline.log == []


def test_the_decision_cadence_has_no_default_and_is_followed_exactly():
    with pytest.raises(TypeError):
        LongContextBaseline(shared_memory([], {}), ScriptedLLM(), BASELINE, SCENARIO)  # no silent default cadence
    for every, hours in ((24.0, (24, 48, 72)), (12.0, (12, 24, 36, 48, 60, 72))):
        baseline, _, llm = make(every=every)
        baseline.advance_to(72.0)
        assert [p.split("\n", 1)[0] for p in llm.prompts] == [f"Current time: hour {h}." for h in hours]
    with pytest.raises(ValueError):
        baseline.advance_to(71.0)


def test_the_log_shows_visible_identity_hints_and_no_household_id():
    assert render_event(INPUTS[0]) == ("[ev-1] h5 source=visit_note name=Mei Chen address=41-22 Hollow Oak Ln: "
                                       "Her son promised to bring groceries by Friday.")


def test_escalations_resolve_through_match_household_and_namesakes_are_never_guessed():
    llm = ScriptedLLM(decide=escalate(
        {**CHEN, "cited_event_ids": ["ev-1"], "reason": "no food"},
        {"name": "Hector Reyes", "cited_event_ids": ["ev-2"]},  # two people share the exact name: ambiguous without a dwelling
        {"name": "Nobody On File", "cited_event_ids": ["ev-1"]}))
    baseline, memory, llm = make(llm=llm)
    baseline.advance_to(24.0)
    [proposal] = run_docs(memory, PROPOSALS, BASELINE)
    assert proposal["household_id"] == "hh-chen"
    assert not any(household_id in "\n".join(llm.prompts) for household_id in HOUSEHOLDS)
    assert [e["hint"]["name"] for e in traced(memory, "identity_unresolved")] == ["Hector Reyes", "Nobody On File"]


def test_escalations_become_proposals_in_the_shared_format():
    llm = ScriptedLLM(decide=escalate({**CHEN, "cited_event_ids": ["ev-2", "ev-1", "ev-invented"], "reason": "x"}))
    baseline, memory, llm = make(llm=llm)
    baseline.advance_to(72.0)
    # Hour 24 has read only ev-1; ev-2 arrives at hour 30. Invented ids cite nothing. The same reply
    # at hour 72 matches the hour-48 proposal, so it is not written twice.
    proposals = run_docs(memory, PROPOSALS, BASELINE)
    assert [(p["ts"], p["cited_event_ids"]) for p in proposals] == [(24.0, ["ev-1"]), (48.0, ["ev-1", "ev-2"])]
    assert set(proposals[0]) >= Proposal.__required_keys__
    assert {(p["household_id"], p["scenario_id"], p["kind"], p["status"]) for p in proposals} == {
        ("hh-chen", SCENARIO, "escalation", "pending")}
    assert "- Mei Chen, 41-22 Hollow Oak Ln at hour 24, citing ev-1" in llm.prompts[1]  # shown what it raised
    assert len(traced(memory, "proposal_created")) == 2 and len(traced(memory, "baseline_decided")) == 3


def test_an_unparsable_reply_is_no_escalation_and_is_traced():
    baseline, memory, _ = make(llm=ScriptedLLM(decide=lambda prompt: "I cannot help with that."))
    baseline.advance_to(24.0)
    [decided] = traced(memory, "baseline_decided")
    assert run_docs(memory, PROPOSALS, BASELINE) == [] and decided["unparsable"] is True


def test_probes_pair_each_opaque_household_id_with_its_visible_identity():
    reply = '{"open_promises": {"hh-chen": ["ev-1", "ev-invented"], "hh-other": ["ev-2"]}}'
    baseline, _, llm = make(llm=ScriptedLLM(probe=lambda prompt: reply))
    baseline.advance_to(72.0)
    probes = baseline.probe(72.0, ["hh-chen", "hh-unknown"])
    assert "- hh-chen: Mei Chen, 41-22 Hollow Oak Ln\n- hh-unknown: (no name or address on file)" in llm.prompts[-1]
    assert probes == [
        {"run_id": BASELINE, "probe_ts": 72.0, "household_id": "hh-chen", "source_event_ids": ["ev-1"]},
        {"run_id": BASELINE, "probe_ts": 72.0, "household_id": "hh-unknown", "source_event_ids": []},
    ]
    assert set(probes[0]) == PromiseProbe.__required_keys__
    with pytest.raises(ValueError):
        baseline.probe(48.0, ["hh-chen"])  # a probe must be taken at the baseline's current time


def test_a_context_limit_keeps_the_newest_events_and_traces_the_drop():
    baseline, memory, llm = make(max_context_chars=len(render_event(INPUTS[1])) + 1)
    baseline.advance_to(48.0)
    assert "[ev-2]" in llm.prompts[-1] and "[ev-1]" not in llm.prompts[-1]
    at_48 = [e for e in traced(memory, "baseline_decided") if e["ts"] == 48.0]
    assert at_48[0]["events_dropped"] == 1 and at_48[0]["events_in_context"] == 1


def test_the_baseline_runs_on_w1s_llm_client_and_cache_and_replays_without_a_model():
    reply = json.dumps({"escalations": [{**CHEN, "cited_event_ids": ["ev-1"]}]})
    cache = InMemoryMemory()  # W1's stand-in for the LLM cache port
    live = CachedLLM(cache, W1ScriptedLLM(lambda prompt: reply))
    first, first_memory, _ = make(llm=live)
    first.advance_to(48.0)
    replay, replay_memory, _ = make(llm=CachedLLM(cache, model=live.model))  # cache only: no model at all
    replay.advance_to(48.0)
    assert run_docs(first_memory, PROPOSALS, BASELINE) == run_docs(replay_memory, PROPOSALS, BASELINE) != []
    first_call, replayed_call = traced(first_memory, "baseline_decided")[0], traced(replay_memory, "baseline_decided")[0]
    assert (first_call["model"], first_call["prompt_tokens"], first_call["cached"]) == ("test/scripted", 120, False)
    assert replayed_call["cached"] is True
