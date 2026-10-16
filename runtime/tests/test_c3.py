"""C3: demo reliability. Spam suppression, escalation on later evidence, the W3 call loop, W2's real
adapters, the scenario loader and the demo command, and failures that say where they happened."""

import copy
import json
from collections import Counter
from pathlib import Path

import pytest

from calls.agent import CallAgent, result_event_id
from calls.fakes import FakeTransport
from calls.responders import ScriptedResponder
from runtime import Runtime, new_run_state
from runtime.demo import open_backend, run_demo, score
from runtime.local import LocalStore
from runtime.loop import MAX_PENDING_IDS, TickFailed, _newest_ids
from runtime.scenario import Scenario, ScenarioError, load_scenario
from schemas import SCENARIO_RUN_ID

DAY0 = "2021-09-01T20:00:00"
CALLBACK = "+1-555-0100"
PARK = {"name": "Mrs. Park", "address": "12-34 Elm St"}
PROMISE = "Visited Mrs. Park at 12-34 Elm St. Her son will bring water tomorrow."  # made h10, due h48


def event(event_id, ts, text, run_id=SCENARIO_RUN_ID, **extra):
    return {"_id": event_id, "run_id": run_id, "scenario_id": "s1", "ts": ts, "source": "visit_note", "text": text,
            **extra}


def make(*events, registered_ts=0.0):
    store = LocalStore({("run-a", "hh-park"): PARK},
                       {"hh-park": {"opt_in": True, "registered_ts": registered_ts, "language": "en", **PARK}})
    store.events.extend(events)
    return Runtime(store, store, DAY0, tick_hours=1.0, ledger=store, retrieval=store), store


def start():
    return new_run_state("run-a", 0.0, "s1")


def of_kind(store, kind):
    return sorted((p for p in store.proposals.values() if p["kind"] == kind), key=lambda p: p["ts"])


# --- proposal volume --------------------------------------------------------------------------------

def test_a_new_silence_episode_waits_while_the_last_alert_is_still_open():
    runtime, store = make(event("e-visit", 10.0, "Visited Mrs. Park at 12-34 Elm St."),
                          event("e-later", 90.0, "Checked on Mrs. Park at 12-34 Elm St, she is managing."),
                          registered_ts=10.0)
    runtime.run(start(), until_ts=200.0)  # silent past 82 (alert), contact at 90, silent again past 162
    [alert] = of_kind(store, "silence_check_in")
    assert alert["ts"] == 83.0 and alert["status"] == "pending"  # the second episode added no second alert
    [held] = [e for e in store.system_events.values() if e["action"] == "proposal_suppressed"]
    assert held["why"] == "an earlier silence alert is still open" and held["household_id"] == "hh-park"


def test_early_check_ins_wait_for_an_open_follow_up_but_a_lapse_never_does():
    runtime, store = make(event("e-1", 10.0, PROMISE),
                          event("e-2", 40.0, "Visited Mrs. Park at 12-34 Elm St. Red Cross will drop off a kit tomorrow."))
    store.promises.clear()
    open_item = {"_id": "p-open", "run_id": "run-a", "scenario_id": "s1", "household_id": "hh-park",
                 "kind": "silence_check_in", "status": "pending", "reason": "", "cited_event_ids": [], "ts": 1.0}
    store.insert_proposal(open_item)
    runtime._policies[("run-a", 1)] = {"lead_hours": 24.0}  # a policy that checks in a day early
    state = {**start(), "policy_version": 1}
    state = runtime.run(state, until_ts=60.0)
    kinds = [(p["kind"], p.get("early")) for p in store.proposals.values() if p["_id"] != "p-open"]
    assert ("check_in", False) in kinds and ("check_in", True) not in kinds  # lapse raised, early held back
    assert "proposal_suppressed" in store.actions("run-a")


def test_a_service_report_after_a_lapse_escalates_it_once():
    crew = event("e-crew", 60.0, "Con Edison field crew: 12-34 ELM ST meter room flooded.", source="crew",
                 address_raw="12-34 ELM ST")
    runtime, store = make(event("e-promise", 10.0, PROMISE), crew)
    before = runtime.run(start(), until_ts=59.0)  # check-in at the lapse (h49), crew report next
    after = runtime.tick(before)
    [escalation] = of_kind(store, "escalation")
    assert escalation["cited_event_ids"] == ["e-promise", "e-crew"] and escalation["ts"] == 60.0
    assert escalation["suggested_action"] == "visit"
    written = copy.deepcopy(store.proposals)
    assert runtime.tick(before) == after and store.proposals == written  # replay: nothing new
    store.events.append(event("e-call", 65.0, "", run_id="run-a", source="call_result", household_id="hh-park",
                              answered=False))
    runtime.run(after, until_ts=70.0)  # an unanswered call after a report-driven escalation adds nothing
    assert len(of_kind(store, "escalation")) == 1


# --- the W3 call loop ---------------------------------------------------------------------------------

def test_the_local_store_is_w3s_call_ledger():
    store, request = LocalStore(), {"_id": "callreq-1", "run_id": "run-a", "proposal_id": "p-1", "requested_ts": 1.0}
    assert not store.claim(request, 1.0)  # never queued, so never placed
    store.schedule_call(request)
    assert store.claim(request, 1.0) and not store.claim(request, 1.0)  # queued -> dialing, exactly once
    assert store.result("callreq-1") is None  # a crash here leaves it dialing: never redialed
    store.finish(request, {"outcome": "no_answer"})
    assert store.call_requests[("run-a", "p-1")]["status"] == "done" and not store.claim(request, 2.0)
    assert store.result("callreq-1") == {"outcome": "no_answer"}


def queued_call():
    """A lapse check-in the coordinator approved, and the call the runtime queued for it (replayed once)."""
    runtime, store = make(event("e-promise", 10.0, PROMISE))
    state = runtime.run(start(), until_ts=50.0)  # the promise lapsed at h48: one check-in
    [check_in] = of_kind(store, "check_in")
    store.decide("run-a", check_in["_id"], "approved", 50.0)  # the coordinator approves
    after = runtime.tick(state)  # h51: the call is queued for W3, a quarter hour later
    assert runtime.tick(state) == after  # a replayed tick queues nothing new
    [queued] = store.call_requests.values()
    assert queued["status"] == "queued" and queued["requested_ts"] == 51.25
    assert after["pending_call_ids"] == [queued["_id"]]
    return runtime, store, after, {key: value for key, value in queued.items() if key != "status"}


@pytest.mark.parametrize("outcome", ["completed", "no_answer", "refused_no_opt_in"])
def test_w3_places_the_queued_call_once_and_the_next_tick_reads_the_outcome(outcome):
    runtime, store, state, request = queued_call()
    if outcome == "refused_no_opt_in":
        store.registry["hh-park"]["opt_in"] = False  # withdrawn after the call was queued
    resident = FakeTransport(["Yes, my son came, thank you."], answers=outcome != "no_answer")
    agent = CallAgent(store, resident, ScriptedResponder(), CALLBACK, store)  # the store is W3's ledger too
    first = agent.start(request)
    assert first["outcome"] == outcome and agent.start(request) == first  # replay: the stored result
    assert resident.dialed == ([] if outcome == "refused_no_opt_in" else ["hh-park"])  # at most one dial
    results = [e["_id"] for e in store.events if e["source"] == "call_result"]
    assert results == ([] if outcome == "refused_no_opt_in" else [result_event_id(request["_id"])])

    state = runtime.run(state, until_ts=80.0)
    assert len(store.call_requests) == 1 and state["pending_call_ids"] == []  # read once, never re-queued
    contact = store.last_contact_by_household("run-a", "s1", 80.0).get("hh-park")
    escalations = [p["cited_event_ids"] for p in of_kind(store, "escalation")]
    if outcome == "completed":  # heard from: the silence clock resets
        assert contact == 51.25 and escalations == [] and "call_completed" in store.actions("run-a")
    elif outcome == "no_answer":  # not contact, and the lapsed promise goes to a person
        assert contact == 10.0 and escalations == [["e-promise", result_event_id(request["_id"])]]
    else:  # W3 wrote no result; the runtime drops the call for the same reason W3 refused it
        assert contact == 10.0 and escalations == [] and "call_skipped_no_opt_in" in store.actions("run-a")


def test_an_unanswered_call_escalation_is_corroborated_once_by_a_later_service_report():
    runtime, store, state, request = queued_call()  # the approved lapse check-in's call, queued for h51.25
    CallAgent(store, FakeTransport([], answers=False), ScriptedResponder(), CALLBACK, store).start(request)
    store.events += [event("e-crew", 60.0, "Con Edison field crew: 12-34 ELM ST meter room flooded.", source="crew",
                           address_raw="12-34 ELM ST"),
                     event("e-311", 70.0, "311: no heat at 12-34 Elm St.", source="311", address_raw="12-34 Elm St")]
    before = runtime.run(state, until_ts=59.0)  # h52: the unanswered call escalated the promise
    after = runtime.tick(before)  # h60: the crew report corroborates it
    written = copy.deepcopy(store.proposals)
    assert runtime.tick(before) == after and store.proposals == written  # replay: nothing new
    runtime.run(after, until_ts=80.0)  # a second service report adds nothing: two escalations at most
    call = result_event_id(request["_id"])
    first, second = of_kind(store, "escalation")
    assert first["cited_event_ids"] == ["e-promise", call] and first["trigger_source"] == "call_result"
    assert second["cited_event_ids"] == ["e-promise", call, "e-crew"] and second["ts"] == 60.0
    assert "went unanswered, and a new report says" in second["reason"]


# --- W2's real adapters ------------------------------------------------------------------------------

def w2_run(crash_after_tick=None, run_id="run-a"):
    """To h60 on W2-C2's adapters: DemoMemory as memory, ledger and retrieval, W2's call queue and its
    checkpoint. The coordinator approves check-ins after each saved tick. Optionally the process dies
    once after a tick's writes, before its checkpoint, and resumes from the last saved one."""
    crew = event("e-crew", 55.0, "Con Edison field crew: 12-34 ELM ST meter room flooded.", source="crew",
                 address_raw="12-34 Elm St")
    scenario = Scenario("s1", DAY0, 100.0, [event("e-promise", 10.0, PROMISE, address_raw="12-34 Elm St"), crew],
                        [{"household_id": "hh-park", "opt_in": True, "scenario_id": "s1", "registered_ts": 0.0,
                          **PARK}])
    backend = open_backend("demo", run_id, scenario)
    runtime = Runtime(backend.memory, backend.calls, DAY0, tick_hours=1.0, ledger=backend.ledger,
                      retrieval=backend.retrieval)
    state = new_run_state(run_id, 0.0, "s1")
    while state["now_ts"] < 60.0:
        after = runtime.tick(state)
        if after["tick"] == crash_after_tick:
            crash_after_tick, state = None, backend.load_state(run_id)  # restart: resume from the checkpoint
            continue
        assert backend.save_state(after)
        for proposal in backend.memory.proposals_with_status(run_id, "pending"):
            if proposal["kind"] == "check_in":
                backend.approve(run_id, proposal["_id"], after["now_ts"])  # W2's decide_proposal
        state = after
    from db.scope import RunScope

    trace = Counter(e["action"] for e in RunScope(backend.db, run_id).find("system_events"))
    return {"state": {k: v for k, v in state.items() if k != "run_id"}, "trace": trace,
            "proposals": sorted((p["kind"], p["status"], p["ts"], tuple(p["cited_event_ids"]))
                                for p in backend.proposals(run_id)),
            "calls": [(r["_id"][-6:], r["requested_ts"], r["status"]) for r in backend.call_requests(run_id)]}


@pytest.mark.parametrize("crash_after_tick", [49, 50, 55])  # the lapse check-in, the queued call, the escalation
def test_a_w2_backed_run_resumes_from_its_checkpoint_as_if_it_never_crashed(crash_after_tick):
    clean = w2_run()  # each run gets its own fresh W2 fake database
    assert w2_run(crash_after_tick) == clean
    assert [kind for kind, *_ in clean["proposals"]] == ["check_in", "escalation"]  # nothing duplicated
    assert [(ts, status) for _, ts, status in clean["calls"]] == [(50.25, "queued")]  # one call, queued once
    assert clean["state"]["tick"] == 60 and clean["state"]["cursor_id"] == "e-crew"
    assert clean["trace"]["goal_scored"] == 2  # W2's ledger is on: the daily goal review ran


# --- scenario files and the demo command ----------------------------------------------------------

def write_scenario(directory, events, registry):
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "scenario.json").write_text(json.dumps({"scenario_id": "s1", "day0": DAY0, "end_ts": 400}))
    (directory / "events.jsonl").write_text("\n".join(json.dumps(e) for e in events))
    (directory / "registry.json").write_text(json.dumps(registry))
    (directory / "needles.json").write_text("this truth file must never be read by the runtime")
    return directory


def test_the_loader_reads_only_what_relay_may_see(tmp_path):
    directory = write_scenario(tmp_path / "s1", [event("e-2", 5.0, "later", origin="synthetic"),
                                                  event("e-1", 1.0, "first", origin="real")], [])
    scenario = load_scenario(directory)
    assert [e["_id"] for e in scenario.events] == ["e-1", "e-2"] and all("origin" not in e for e in scenario.events)
    (directory / "events.jsonl").write_text(json.dumps(event("e-3", 1.0, "x", run_id="run-b")))
    with pytest.raises(ScenarioError, match="run_id"):
        load_scenario(directory)
    with pytest.raises(ScenarioError, match="missing"):
        load_scenario(tmp_path / "nowhere")


HERO = {"household_id": "hh-chen", "opt_in": True, "registered_ts": 42.0, "scenario_id": "s1", "name": "Mei Chen",
        "address": "41-22 Hollow Oak Ln Bsmt", "language": "zh"}
HERO_EVENTS = [event("e-note", 42.6, "Visited Mrs. Chen, 82, at 41-22 Hollow Oak Ln. Her son Wei is coming Tuesday "
                     "to help clean out.", address_raw="41-22 Hollow Oak Ln", household_ref_raw="Mrs. Chen"),
               event("e-crew", 303.0, "Con Edison field crew: 4122 HOLLOW OAK LN meter room flooded. No one "
                     "answered.", source="crew", address_raw="4122 HOLLOW OAK LN")]


def test_the_demo_fast_forwards_to_the_heros_escalation(tmp_path):
    lines = []
    summary = run_demo(write_scenario(tmp_path / "s1", HERO_EVENTS, [HERO]), say=lines.append)
    steps = [s["what"] for s in summary["hero_chain"]]
    assert steps[0] == "promise recorded" and "check_in proposed" in steps
    assert "coordinator approves (simulated for the demo)" in steps and "call request queued for W3" in steps
    assert steps[-1] == "escalation proposed" and summary["hero_escalated"] and summary["ended_at_ts"] == 303.0
    assert summary["calls_queued"] == 1 and summary["call_outcomes"] == {}  # no contact truth: nobody to dial
    assert summary["model"] is False  # no key: the regex path ran


def test_the_demo_places_queued_calls_with_w3_and_reads_the_result_next_tick(tmp_path):
    residents = []

    def unanswered(request):  # stands in for W5's scripted resident
        residents.append(FakeTransport([], answers=False))
        return residents[-1]

    summary = run_demo(write_scenario(tmp_path / "s1", HERO_EVENTS, [HERO]), residents=unanswered,
                       say=lambda *_: None)
    chain = [(s["ts"], s["what"]) for s in summary["hero_chain"]]
    assert chain[-4:] == [(146.0, "call request queued for W3"), (146.25, "W3 call outcome: no_answer"),
                          (147.0, "runtime read the call result"), (146.25, "escalation proposed")]
    assert summary["call_outcomes"] == {"no_answer": 1} and [r.dialed for r in residents] == [["hh-chen"]]
    [escalation] = [p for p in summary["_proposals"] if p["kind"] == "escalation"]
    assert escalation["cited_event_ids"][-1].endswith(":result") and summary["ended_at_ts"] == 147.0


def test_the_demo_uses_w5s_scripted_residents_when_the_scenario_ships_contact_truth(tmp_path):
    pytest.importorskip("data.contact", reason="W5-C2's call simulator is not on this branch yet")
    directory = write_scenario(tmp_path / "s1", HERO_EVENTS, [HERO])
    (directory / "contact_truth.json").write_text(json.dumps({"scenario_id": "s1", "households": [
        {"household_id": "hh-chen", "no_answer": [{"from_ts": 145.5, "until_ts": 493.0}], "script": []}]}))
    summary = run_demo(directory, say=lambda *_: None)
    assert summary["call_outcomes"] == {"no_answer": 1} and summary["ended_at_ts"] == 147.0


def test_the_final_w2_stack_places_the_call_and_a_stopped_run_continues(tmp_path, monkeypatch):
    from db.fakes import FakeDatabase
    from db.scope import RunScope

    shared = FakeDatabase()
    monkeypatch.setattr("db.fakes.FakeDatabase", lambda: shared)  # both invocations use one database
    directory = write_scenario(tmp_path / "s1", HERO_EVENTS, [HERO])

    def run(until_ts=None):
        return run_demo(directory, store="demo", until_ts=until_ts, stop_at_escalation=False,
                        residents=lambda request: FakeTransport([], answers=False), say=lambda *_: None)

    assert run(until_ts=100.0)["ended_at_ts"] == 100.0  # the run stops; its checkpoint is saved
    summary = run()  # the same command continues from h100 to the end
    steps = [(s["ts"], s["what"]) for s in summary["hero_chain"]]
    assert steps[0] == (100.0, "continuing from the saved checkpoint") and summary["ended_at_ts"] == 400.0
    assert steps[-5:] == [(146.0, "call request queued for W3"), (146.25, "W3 call outcome: no_answer"),
                          (147.0, "runtime read the call result"), (146.25, "escalation proposed"),
                          (303.0, "escalation proposed")]
    run_scope = RunScope(shared, "relay-demo")
    [call] = run_scope.find("call_requests")  # W2's DemoCallLedger: queued -> dialing -> done
    assert call["status"] == "done" and summary["call_outcomes"] == {"no_answer": 1}
    [result] = run_scope.find("events", {"source": "call_result"})  # written by W3 through DemoCallBackend
    assert result["_id"] == f"{call['_id']}:result" and result["run_id"] == "relay-demo"
    escalations = sorted((p for p in summary["_proposals"] if p["kind"] == "escalation"), key=lambda p: p["ts"])
    assert [p["cited_event_ids"] for p in escalations] == [["e-note", result["_id"]],
                                                           ["e-note", result["_id"], "e-crew"]]
    [approval] = run_scope.find("system_events", {"action": "proposal_decided"})
    assert approval["module"] == "demo" and approval["reason"] == "Simulated coordinator approval for the demo"
    state = shared["run_state"].find_one({"_id": "relay-demo"})  # how the recorded snapshot reader finds a run
    assert state["now_ts"] == 400.0 and state["scenario_id"] == "s1" and run_scope.find("runs")


REAL_S1 = Path(__file__).resolve().parents[2] / "data" / "scenarios" / "s1"


@pytest.mark.skipif(not (REAL_S1 / "events.jsonl").is_file(), reason="W5's Scenario 1 is not in this checkout")
def test_real_scenario_1_runs_end_to_end_places_the_heros_call_and_catches_her():
    summary = run_demo(REAL_S1, until_ts=1032.0, stop_at_escalation=False, say=lambda *_: None)
    assert summary["ended_at_ts"] == 1032.0 and summary["hero_escalated"]
    # W5's frozen Mrs. Chen chain; her scripted phone goes unanswered from h145.5.
    assert [(s["ts"], s["what"]) for s in summary["hero_chain"]] == [
        (42.6, "promise recorded"), (116.0, "silence_check_in proposed"), (145.0, "check_in proposed"),
        (145.0, "coordinator approves (simulated for the demo)"), (146.0, "call request queued for W3"),
        (146.25, "W3 call outcome: no_answer"), (147.0, "runtime read the call result"),
        (146.25, "escalation proposed"), (303.0, "escalation proposed")]
    hero = sorted((p for p in summary["_proposals"] if p["household_id"] == summary["hero_household_id"]),
                  key=lambda p: p["ts"])
    call = "callreq-1853077c31a0b9fd:result"
    assert [p["cited_event_ids"] for p in hero if p["kind"] == "check_in"] == [["s1_e_000376"]]  # due h144
    assert [p["cited_event_ids"] for p in hero if p["kind"] == "escalation"] == [
        ["s1_e_000376", call], ["s1_e_000376", call, "s1_e_001073"]]  # then corroborated by the crew report
    assert summary["calls_queued"] == 1 and summary["call_outcomes"] == {"no_answer": 1}  # dialed once
    registered = len(json.loads((REAL_S1 / "registry.json").read_text()))
    assert summary["proposals_by_kind"]["silence_check_in"] <= registered  # at most one open alert each
    assert sum(summary["proposals_by_kind"].values()) <= 2 * registered
    result = score(REAL_S1, summary)  # truth is read here, by the evaluator, never by the runtime
    caught = {n["needle_id"] for n in result["detail"]["needles"] if n["caught"]}
    assert {"s1_n_01", "s1_n_08", "s1_n_09", "s1_n_10"} <= caught  # Mrs. Chen, and every silent household


# --- failures and state size ----------------------------------------------------------------------

def test_a_failing_port_reports_where_the_tick_stopped():
    runtime, store = make(event("e-promise", 10.0, PROMISE))

    def unavailable(*args, **kwargs):
        raise ConnectionError("sandbox unreachable")

    store.registry_entries = unavailable
    with pytest.raises(TickFailed, match=r"tick 1 \(hour 1\) failed while watching silence: ConnectionError"):
        runtime.tick(start())


def test_the_checkpoint_keeps_only_the_newest_pending_ids():
    proposals = [{"_id": f"p-{n:04d}", "ts": float(n)} for n in range(MAX_PENDING_IDS + 50)]
    kept = _newest_ids(proposals)
    assert len(kept) == MAX_PENDING_IDS and kept[0] == "p-0050" and kept[-1] == f"p-{MAX_PENDING_IDS + 49:04d}"
