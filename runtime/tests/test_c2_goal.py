"""The whole goal (promises in time, nobody silent past 72h), the cross-service scan, emergencies,
and credit from W4's real evaluator."""

import json
import re

from eval.scorer import score_run
from runtime import Runtime, new_run_state
from runtime.silence import SILENT_AFTER_HOURS, silent_households
from runtime.tests.fakes import InMemoryMemory, ScriptedLLM, StubCalls, phrase_safety
from schemas import SCENARIO_RUN_ID

DAY0 = "2021-09-01T20:00:00"
PEOPLE = {
    "hh-park": {"name": "Mrs. Park", "address": "12-34 Elm St"},
    "hh-lee": {"name": "Mr. Lee", "address": "5-10 Oak St"},
    "hh-kim": {"name": "Mrs. Kim", "address": "7-70 Pine St"},
    "hh-chen": {"name": "Mrs. Chen", "address": "41-22 41st Ave"},
}
HOUSEHOLDS = {(run_id, hh): person for hh, person in PEOPLE.items()
              for run_id in ("run-a", "run-b", "relay-1", "baseline-1")}
VISIT = "Visited Mrs. Park at 12-34 Elm St. Registered her for follow-up calls."
CHEN_NOTE = ("Visited Mrs. Chen, 82, at 41-22 41st Ave. Basement flooded. Her son Wei is coming Tuesday to help "
             "clean out and take her to stay with him.")
DELAY = "Con Edison outage update: restoration on 41st Ave delayed. New estimate: Sep 13 or later."


def event(event_id, ts, text, run_id=SCENARIO_RUN_ID, **extra):
    return {"_id": event_id, "run_id": run_id, "scenario_id": "s1", "ts": ts, "source": "visit_note", "text": text,
            **extra}


def make(*events, llm=None, registry=None, tick_hours=1.0):
    registry = registry or {"hh-park": {"opt_in": True, "registered_ts": 10.0, **PEOPLE["hh-park"]}}
    memory = InMemoryMemory(HOUSEHOLDS, registry=registry)
    memory.events.extend(events)
    runtime = Runtime(memory, StubCalls(), DAY0, tick_hours=tick_hours, llm=llm, safety=phrase_safety, ledger=memory,
                      retrieval=memory)
    return runtime, memory


def start(run_id="run-a"):
    return new_run_state(run_id, 0.0, "s1")


def of_kind(memory, kind, run_id="run-a"):
    return sorted((p for p in memory.proposals.values() if p["kind"] == kind and p["run_id"] == run_id),
                  key=lambda p: p["ts"])


def field_model(risk_follow_up=True):
    """Scripted OpenRouter answers for extraction, promise decisions and the cross-service scan."""
    def respond(prompt):
        if prompt.startswith("Note written"):
            if "son Wei is coming Tuesday" in prompt:
                return json.dumps({"promises": [{"who": "son Wei", "what": "take her to stay with him",
                                                 "due_date": "2021-09-07"}], "kept_promise_ids": []})
            return json.dumps({"promises": [], "kept_promise_ids": []})
        shown = re.findall(r"- (e-[\w-]+) \(", prompt)
        if "Registered household" in prompt:
            if not risk_follow_up or "restored" in prompt:  # a reported problem that was then resolved
                return json.dumps({"follow_up": False})
            return json.dumps({"follow_up": True, "cited_event_ids": [*shown, "e-never-shown"],
                               "suggested_action": "call", "rationale": "No heat, and the meter is still flooded."})
        return json.dumps({"cited_event_ids": shown, "suggested_action": "call",
                           "rationale": "The utility delay means she is still waiting."})
    return respond


# --- the goal's second half: nobody opted in silent for more than 72 hours ----------------------------

def test_exactly_72_hours_is_not_yet_silent_but_more_is():
    entries = [{"household_id": "hh-park", "opt_in": True, "registered_ts": 10.0}]
    assert silent_households(entries, {"hh-park": 10.0}, now=10.0 + SILENT_AFTER_HOURS) == {}
    assert silent_households(entries, {"hh-park": 10.0}, now=10.0 + SILENT_AFTER_HOURS + 0.01) == {"hh-park": 10.0}

    runtime, memory = make(event("e-visit", 10.0, VISIT))
    state = runtime.run(start(), until_ts=82.0)  # exactly 72h after the visit
    assert of_kind(memory, "silence_check_in") == []
    runtime.tick(state)  # hour 83
    [proposal] = of_kind(memory, "silence_check_in")
    assert proposal["ts"] == 83.0 and proposal["status"] == "pending" and proposal["suggested_action"] == "call"
    assert proposal["cited_event_ids"] == ["e-visit"]  # evidence the run had already tied to her, and seen


def test_households_without_opt_in_never_get_a_silence_proposal():
    registry = {"hh-park": {"opt_in": False, "registered_ts": 10.0, **PEOPLE["hh-park"]}}
    runtime, memory = make(event("e-visit", 10.0, VISIT), registry=registry)
    runtime.run(start(), until_ts=300.0)
    assert of_kind(memory, "silence_check_in") == []


def test_another_runs_contacts_cannot_suppress_the_alert():
    run_b_visit = event("e-b-visit", 50.0, "Visited Mrs. Park at 12-34 Elm St, she is fine.", run_id="run-b")
    runtime, memory = make(event("e-visit", 10.0, VISIT), run_b_visit)
    runtime.run(start("run-b"), until_ts=100.0)  # run-b heard from her at hour 50
    runtime.run(start("run-a"), until_ts=100.0)
    assert [p["ts"] for p in of_kind(memory, "silence_check_in", "run-a")] == [83.0]
    assert of_kind(memory, "silence_check_in", "run-b") == []  # 50 + 72 = 122 is still ahead for run-b


def test_replaying_a_tick_does_not_duplicate_the_silence_proposal():
    runtime, memory = make(event("e-visit", 10.0, VISIT))
    before = runtime.run(start(), until_ts=82.0)
    after = runtime.tick(before)
    assert runtime.tick(before) == after and len(of_kind(memory, "silence_check_in")) == 1
    runtime.run(after, until_ts=140.0)  # the same episode keeps its single follow-up
    assert len(of_kind(memory, "silence_check_in")) == 1


def test_a_later_contact_resets_the_clock_and_a_new_silence_is_a_new_episode():
    runtime, memory = make(event("e-visit", 10.0, VISIT),
                           event("e-later", 60.0, "Checked on Mrs. Park at 12-34 Elm St, she is managing."),
                           event("e-third", 150.0, "Dropped by Mrs. Park at 12-34 Elm St with water."))
    runtime.run(start(), until_ts=132.0)  # exactly 72h after the hour-60 contact
    assert of_kind(memory, "silence_check_in") == []
    state = runtime.run(start(), until_ts=140.0)
    [first] = of_kind(memory, "silence_check_in")
    assert first["ts"] == 133.0
    memory.decide("run-a", first["_id"], "approved", 140.0)  # the coordinator acts on the first alert
    runtime.run(state, until_ts=240.0)
    first, second = of_kind(memory, "silence_check_in")
    assert second["ts"] == 223.0 and first["_id"] != second["_id"]  # contact at 150, silent again past 222


# --- the cross-service scan ------------------------------------------------------------------------

def test_cross_service_scan_needs_two_services_a_model_yes_and_cites_only_what_it_showed():
    registry = {hh: {"opt_in": True, "registered_ts": 0.0, **PEOPLE[hh]} for hh in ("hh-park", "hh-lee", "hh-kim")}
    events = [
        event("e-311", 20.0, "311 call: no heat and no hot water at 12-34 Elm St, elderly resident.", source="311"),
        event("e-crew", 30.0, "Con Edison field crew: 12-34 Elm St meter room flooded, service not reconnected.",
              source="crew"),
        event("e-lee-311", 20.0, "311 call: no power at 5-10 Oak St.", source="311"),  # the resolved decoy
        event("e-lee-fixed", 30.0, "Con Edison: power restored on Oak St.", source="utility"),
        event("e-kim-1", 20.0, "311 call: street flooding outside 7-70 Pine St.", source="311"),  # one service only
        event("e-kim-2", 30.0, "311 call: sewer backup at 7-70 Pine St.", source="311"),
    ]
    llm = ScriptedLLM(field_model())
    runtime, memory = make(*events, llm=llm, registry=registry)
    runtime.run(start(), until_ts=48.0)  # hour 48: the first daily scan that can see both of Mrs. Park's reports

    [risk] = of_kind(memory, "cross_service_check_in")
    assert risk["household_id"] == "hh-park" and risk["ts"] == 48.0 and risk["status"] == "pending"
    assert risk["cited_event_ids"] == ["e-311", "e-crew"]  # "e-never-shown" was dropped
    scans = [prompt for prompt in llm.prompts if "Registered household" in prompt]
    assert any("Oak St" in prompt for prompt in scans)  # the decoy was asked about and declined
    assert not any("Pine St" in prompt for prompt in scans)  # a single service never reaches the model
    # Daily, and each search is cut off at the scan's own time: at hour 24 the crew report (hour 30)
    # did not exist yet, so Mrs. Park had one service and the model was not asked about her.
    assert [s["as_of_ts"] for s in memory.searches if s["query"] == "Mrs. Park 12-34 Elm St"] == [24.0, 48.0]
    assert sum("Elm St" in prompt for prompt in scans) == 1


def test_a_household_the_run_has_heard_from_is_scanned_even_if_not_registered():
    events = [
        event("e-lee-visit", 10.0, "Visited Mr. Lee at 5-10 Oak St, lives alone in the basement."),
        event("e-lee-311", 20.0, "311 call: no heat at 5-10 Oak St, basement flooded.", source="311"),
        event("e-lee-crew", 30.0, "Con Edison field crew: 5-10 Oak St panel flooded, not reconnected.", source="crew"),
    ]
    runtime, memory = make(*events, llm=ScriptedLLM(field_model()))  # the registry only lists Mrs. Park
    runtime.run(start(), until_ts=48.0)
    [risk] = of_kind(memory, "cross_service_check_in")
    assert risk["household_id"] == "hh-lee" and risk["suggested_action"] == "visit"  # not registered: no opt-in
    assert len(risk["cited_event_ids"]) >= 2 and "e-never-shown" not in risk["cited_event_ids"]


# --- emergencies ------------------------------------------------------------------------------------

def test_emergencies_use_w3s_shape_and_only_for_a_matched_household():
    background = event("e-gas", 5.0, "311 complaint: gas leak reported near 99 Unknown Ave.", source="311")
    urgent = event("e-fell", 20.0, "Mrs. Park at 12-34 Elm St: neighbor says she fell.")
    llm = ScriptedLLM(field_model())
    runtime, memory = make(background, urgent, llm=llm)
    runtime.run(start(), until_ts=21.0)
    [emergency] = of_kind(memory, "emergency")
    assert (emergency["status"], emergency["queue"], emergency["urgent"], emergency["household_id"]) == (
        "pending", "urgent_human", True, "hh-park")
    assert emergency["cited_event_ids"] == ["e-fell"]  # the unmatched background record raised nothing
    assert not any("fell" in prompt for prompt in llm.prompts)


# --- credit from the real evaluator ------------------------------------------------------------------

def test_runtime_proposals_earn_credit_from_the_real_evaluator():
    e_visit = event("e-visit", 10.0, VISIT)
    e_crew = event("e-park-crew", 30.0, "Con Edison field crew: 12-34 Elm St meter room flooded. No one answered.",
                   source="crew")
    e_chen = event("e-chen", 42.6, CHEN_NOTE)
    e_delay = event("e-delay", 100.0, DELAY, source="utility")
    registry = {"hh-park": {"opt_in": True, "registered_ts": 10.0, **PEOPLE["hh-park"]},
                "hh-chen": {"opt_in": True, "registered_ts": 42.6, **PEOPLE["hh-chen"]}}
    runtime, memory = make(e_visit, e_crew, e_chen, e_delay, llm=ScriptedLLM(field_model(risk_follow_up=False)),
                           registry=registry)
    runtime.run(start(), until_ts=200.0)

    needles = [
        {"needle_id": "n-chen", "kind": "broken_promise", "household_id": "hh-chen", "people_at_risk": 1,
         "required_event_ids": ["e-chen", "e-delay", "e-not-yet"], "deadline": 528.0, "danger_at": 600.0,
         "response_hours": 24.0},
        {"needle_id": "n-park", "kind": "silent_household", "household_id": "hh-park", "people_at_risk": 1,
         "required_event_ids": ["e-visit", "e-park-crew"], "deadline": 168.0, "danger_at": 240.0,
         "response_hours": 24.0},
    ]
    score = score_run(
        "run-a", scenario_id="s1", proposals=list(memory.proposals.values()), needles=needles, decoys=[],
        promises=[{"household_id": "hh-chen", "source_event_id": "e-chen", "made_ts": 42.6, "due_ts": 144.0}],
        registry=[{"household_id": hh, "opt_in": True} for hh in registry],
        contacts=[{**e_visit, "household_id": "hh-park"}, {**e_chen, "household_id": "hh-chen"}],
        probes=[], as_of=200.0)
    assert score["needle_recall"] == 1.0 and score["impact"]["false_escalations"] == 0
    caught = {result["needle_id"]: result["escalated_at"] for result in score["detail"]["needles"]}
    # Mrs. Chen is caught by her silence alert at hour 115, which cites her note and the utility delay on her
    # street (both seen by then); Mrs. Park by her silence alert citing her visit and the crew report.
    assert caught == {"n-chen": 115.0, "n-park": 83.0}
