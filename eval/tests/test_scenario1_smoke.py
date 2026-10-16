"""Smoke over the committed W5 Scenario 1 inputs: events exactly as committed (no household ids added),
households from the visible registry only. The truth files (households_truth.json and the rest) are
never opened here."""

import json
from pathlib import Path

from db.bootstrap import PROPOSALS, SYSTEM_EVENTS
from eval.baseline import LongContextBaseline
from eval.tests.fakes import ScriptedLLM, run_docs, shared_memory

S1 = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "s1"
RUN, UNTIL = "baseline-s1", 48.0
HERO, STRANGER = "s1_e_000376", "s1_e_000139"


def visible_events():
    with (S1 / "events.jsonl").open() as lines:  # W5: Relay-visible once `origin` is stripped
        return [{key: value for key, value in json.loads(line).items() if key != "origin"} for line in lines]


def test_the_baseline_resolves_the_real_scenario_1_hero_from_visible_hints_only():
    events, registry = visible_events(), json.loads((S1 / "registry.json").read_text())
    assert not any("household_id" in event for event in events)
    by_id = {event["_id"]: event for event in events}
    hero, stranger = by_id[HERO], by_id[STRANGER]
    assert (hero["household_ref_raw"], hero["address_raw"]) == ("Mrs. Chen", "41-22 Hollow Oak Ln"), \
        "Scenario 1 changed: re-pick Mrs. Chen's first visit note"
    assert (stranger["household_ref_raw"], stranger["address_raw"]) == ("Mrs. Miah", "88-12 Willowmere Street"), \
        "Scenario 1 changed: re-pick a visit note about someone not on file"
    # Stand-in for the run bootstrap: the households registered by the end of the window.
    on_file = {entry["household_id"]: {"name": entry["name"], "address": entry["address"]}
               for entry in registry if entry["registered_ts"] <= UNTIL}
    memory = shared_memory(events, {RUN: on_file})

    def decide(prompt):
        if not prompt.startswith(f"Current time: hour {UNTIL:g}."):
            return '{"escalations": []}'
        return json.dumps({"escalations": [
            {"name": event["household_ref_raw"], "address": event["address_raw"], "cited_event_ids": [event["_id"]],
             "reason": "needs a follow-up"} for event in (hero, stranger)]})

    llm = ScriptedLLM(decide=decide)
    baseline = LongContextBaseline(memory, llm, RUN, "s1", decision_every_hours=24.0)
    baseline.advance_to(UNTIL)

    [proposal] = run_docs(memory, PROPOSALS, RUN)
    registered = next(entry for entry in registry if entry["address"] == hero["address_raw"])  # Mei Chen
    assert (proposal["household_id"], proposal["cited_event_ids"]) == (registered["household_id"], [HERO])
    # Mrs. Miah is named in the log but is not on file, so no household is guessed for her.
    unresolved = [e for e in run_docs(memory, SYSTEM_EVENTS, RUN, module="baseline")
                  if e["action"] == "identity_unresolved"]
    assert [e["hint"] for e in unresolved] == [{"name": "Mrs. Miah", "address": "88-12 Willowmere Street"}]
    assert "name=Mrs. Chen address=41-22 Hollow Oak Ln" in llm.prompts[-1]
    assert not any(household_id in prompt for household_id in on_file for prompt in llm.prompts)

    [answer] = baseline.probe(UNTIL, [registered["household_id"]])
    assert f"- {registered['household_id']}: {registered['name']}, {registered['address']}" in llm.prompts[-1]
    assert answer["household_id"] == registered["household_id"]
