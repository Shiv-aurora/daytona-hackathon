"""W5-C2 integration: the committed Scenario 1 through the merged W1 runtime, W2 memory/db, W3 calls and W4 evaluator.

Nothing here converts or patches the fixture: events, registry and ground truth are read as committed.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

import pytest

DATA = Path(__file__).resolve().parents[1]
ROOT = DATA.parent
sys.path[:0] = [str(DATA), str(ROOT)]

import contact
import filing

from calls.agent import CallAgent
from calls.fakes import InMemoryBackend, InMemoryLedger, SpyResponder
from db.bootstrap import REGISTRY
from db.events import record_event
from db.scope import RunScope
from db.testing import open_test_database
from eval.scorer import score_run
from memory.adapter import DemoMemory
from memory.households import match_household, seed_household
from runtime.loop import Runtime
from runtime.state import new_run_state
from runtime.tests.fakes import StubCalls
from schemas import SCENARIO_RUN_ID

S1 = DATA / "scenarios" / "s1"
EVENTS = [json.loads(line) for line in (S1 / "events.jsonl").open()]
BY_ID = {e["_id"]: e for e in EVENTS}


def read(name):
    return json.loads((S1 / f"{name}.json").read_text())


META, REGISTRY_DOCS, NEEDLES, DECOYS = read("scenario"), read("registry"), read("needles"), read("decoys")
TRUTH, EVENT_TRUTH, PROMISES = read("households_truth"), read("event_truth"), read("promises")
HERO = next(n for n in NEEDLES if n["needle_id"] == "s1_n_01")
REGISTERED = {r["household_id"] for r in REGISTRY_DOCS}
UNREGISTERED_NEEDLES = [n for n in NEEDLES if n["household_id"] not in REGISTERED]

REGISTRY_IDENTITIES = {r["household_id"]: {"name": r["name"], "address": r["address"]} for r in REGISTRY_DOCS}
# Hidden-truth identities: a data-consistency check only. Reachability without hidden truth is proven by the
# visible-filing tests below.
TRUTH_IDENTITIES = {h["household_id"]: {"name": h["canonical_name"], "address": h["identity_address"]} for h in TRUTH}


def run_scenario(identities, run_id):
    """Scenario inputs + registry as committed, households seeded, then the regex-path runtime for six weeks."""
    with open_test_database() as db:
        scenario = RunScope.scenario(db)
        for event in EVENTS:
            record_event(scenario, event)
        for entry in REGISTRY_DOCS:
            db[REGISTRY].insert_one(dict(entry))
        for household_id, identity in identities.items():
            seed_household(RunScope(db, run_id), household_id, **identity)
        runtime = Runtime(DemoMemory(db), StubCalls(), META["day0"], tick_hours=6.0)
        state = runtime.run(new_run_state(run_id, 0.0, "s1"), META["end_ts"])
        trace = db["system_events"].find({"run_id": run_id})
        return {"state": state,
                "matched": {s["event_id"]: s["household_id"] for s in trace if s["action"] == "household_matched"},
                "proposals": db["proposals"].find({"run_id": run_id}),
                "promises": db["promises"].find({"run_id": run_id})}


@pytest.fixture(scope="module")
def registry_run():
    return run_scenario(REGISTRY_IDENTITIES, "run-registry")


@pytest.fixture(scope="module")
def truth_run():
    return run_scenario(TRUTH_IDENTITIES, "run-truth")


@pytest.fixture(scope="module")
def visible_filing():
    return filing.file_households(EVENTS, REGISTRY_DOCS)


def test_runtime_consumes_the_committed_scenario_as_is(registry_run):
    assert registry_run["state"]["now_ts"] >= META["end_ts"]
    wrong = {e: h for e, h in registry_run["matched"].items() if EVENT_TRUTH[e]["household_id"] != h}
    assert not wrong, f"events matched to the wrong household: {wrong}"


def test_hero_chain_resolves_and_lapses_on_main(registry_run):
    visit, _, crew = HERO["required_event_ids"]
    assert registry_run["matched"].get(visit) == registry_run["matched"].get(crew) == HERO["household_id"]
    (promise,) = [p for p in registry_run["promises"] if p["household_id"] == HERO["household_id"]]
    truth = next(p for p in PROMISES if p["source_event_id"] == visit)
    assert promise["source_event_id"] == visit and promise["due_ts"] == truth["due_ts"] == 144.0  # Tue Sep 7, end of sim day
    assert promise["status"] == "lapsed"
    lapse = [p for p in registry_run["proposals"] if p["household_id"] == HERO["household_id"]]
    assert lapse and all(visit in p["cited_event_ids"] and p["ts"] < HERO["deadline"] for p in lapse)


def test_labelled_identities_are_consistent_with_the_events(truth_run):
    """Data consistency (uses hidden truth): seeded with every intended identity, W1 matches nothing wrongly."""
    assert all(EVENT_TRUTH[e]["household_id"] == h for e, h in truth_run["matched"].items())
    for n in NEEDLES:
        hits = [BY_ID[e] for e in n["required_event_ids"] if truth_run["matched"].get(e) == n["household_id"]]
        assert len(hits) >= 2 and len({e["source"] for e in hits}) >= 2, n["needle_id"]


def test_unregistered_needles_are_fileable_from_visible_events(visible_filing):
    """No hidden truth until the last assertion: a visible named+addressed report files each household before its
    deadline, and at least two required events from two services resolve to that filing through W2's matcher."""
    resolved, filed = visible_filing
    assert sorted(n["needle_id"] for n in UNREGISTERED_NEEDLES) == [
        "s1_n_02", "s1_n_03", "s1_n_05", "s1_n_06", "s1_n_07"]
    for n in UNREGISTERED_NEEDLES:
        households = {resolved.get(e) for e in n["required_event_ids"]} - {None}
        assert len(households) == 1, (n["needle_id"], households)
        (household,) = households
        assert household in filed, n["needle_id"]
        first = BY_ID[filed[household]]
        assert first["household_ref_raw"] and first["address_raw"] and first["ts"] < n["deadline"], n["needle_id"]
        hits = [BY_ID[e] for e in n["required_event_ids"] if resolved.get(e) == household]
        assert len(hits) >= 2 and len({e["source"] for e in hits}) >= 2, n["needle_id"]
        assert all(first["ts"] <= e["ts"] < n["deadline"] for e in hits), n["needle_id"]
        # Only now consult hidden truth: the filing is the labelled household, and nobody else's events joined it.
        assert {EVENT_TRUTH[e]["household_id"] for e, h in resolved.items() if h == household} == {n["household_id"]}


def test_registered_needles_resolve_from_the_visible_registry(visible_filing):
    resolved, _ = visible_filing
    for n in (n for n in NEEDLES if n["household_id"] in REGISTERED):
        hits = [BY_ID[e] for e in n["required_event_ids"] if resolved.get(e) == n["household_id"]]
        assert len(hits) >= 2 and len({e["source"] for e in hits}) >= 2, n["needle_id"]


def test_visible_filing_keeps_needles_decoys_and_real_rows_apart(visible_filing):
    """Real 311 rows never join a household, and an identity that holds any needle or decoy household's events holds
    only that household. (Background households can merge through W2's name fallback on "Mrs. Kim"-style references
    when an address variant does not match; that matching policy is W2's, reported in the PR.)"""
    resolved, _ = visible_filing
    owners = defaultdict(set)
    for event_id, household in resolved.items():
        owners[household].add(EVENT_TRUTH[event_id]["household_id"])
    assert not any(None in o for o in owners.values()), "a real 311 row resolved to a household"
    scored = {n["household_id"] for n in NEEDLES} | {d["household_id"] for d in DECOYS}
    mixed = {h: o for h, o in owners.items() if o & scored and len(o) > 1}
    assert not mixed, f"a needle/decoy identity collected another household's events: {mixed}"
    by_decoy = {d["decoy_id"]: d for d in DECOYS}
    wang_cellar = {resolved[e] for e in next(n for n in NEEDLES if n["needle_id"] == "s1_n_07")["required_event_ids"]
                   if e in resolved}
    assert not wang_cellar & {resolved.get(e) for e in by_decoy["s1_d_09"]["event_ids"]}, "Wang 3F joined the cellar"
    gonzalez = [{resolved.get(e) for e in by_decoy[d]["event_ids"]} - {None} for d in ("s1_d_10", "s1_d_11")]
    assert not gonzalez[0] & gonzalez[1], "the two Gonzalez units merged"


def test_namesakes_and_decoys_never_resolve_to_another_household():
    with open_test_database() as db:
        scope = RunScope(db, "run-ids")
        for household_id, identity in TRUTH_IDENTITIES.items():
            seed_household(scope, household_id, **identity)
        cases = [(d["household_id"], e) for d in DECOYS for e in d["event_ids"] + d["resolution_event_ids"]]
        cases += [(n["household_id"], e) for n in NEEDLES for e in n["required_event_ids"]]
        for household_id, event_id in cases:
            assert match_household(scope, filing.visible_hint(BY_ID[event_id])) in (household_id, None), event_id


def test_cross_service_needles_join_across_services(visible_filing):
    resolved, _ = visible_filing
    for n in (n for n in NEEDLES if n["kind"] == "cross_service_join"):
        hits = [BY_ID[e] for e in n["required_event_ids"] if resolved.get(e)]
        assert len({resolved[e["_id"]] for e in hits}) == 1, n["needle_id"]
        assert len({e["source"] for e in hits}) >= 2 and len({e["household_ref_raw"] for e in hits}) >= 2, n["needle_id"]


def call(truth, request_ts, household_id, run_id, *, queued=True):
    """One W3-C2 call: W1 -> W2 `schedule_call` queues the request, then W3 claims and places it."""
    backend = InMemoryBackend(registry={r["household_id"]: r for r in REGISTRY_DOCS})
    ledger = InMemoryLedger()
    request = {"_id": f"call-{run_id}-{household_id}-{request_ts}", "run_id": run_id, "scenario_id": "s1",
               "household_id": household_id, "proposal_id": "p", "purpose": "follow_up", "requested_ts": request_ts}
    if queued:
        assert ledger.queue(request)
    agent = CallAgent(backend, contact.ScriptedResident(truth, request_ts), SpyResponder(), META["callback_number"],
                      ledger)
    return agent.start(request), list(backend.events.values())


def test_w3_turns_contact_truth_into_run_scoped_call_results():
    truth = contact.load(S1 / "contact_truth.json")
    hero = HERO["household_id"]
    result, events = call(truth, 150.0, hero, "run-a")  # the Wednesday follow-up after the promise lapses
    assert result["outcome"] == "no_answer" and not result["answered"]
    result, events = call(truth, 500.0, hero, "run-a")  # Sep 22: she answers
    assert result["outcome"] == "completed" and "My son never came" in result["text"]
    assert events and all(e["run_id"] == "run-a" != SCENARIO_RUN_ID and e["source"] == "call_result" for e in events)
    for n in (n for n in NEEDLES if n["kind"] == "silent_household"):
        (window,) = truth[n["household_id"]]["no_answer"]
        assert call(truth, window["from_ts"], n["household_id"], "run-a")[0]["outcome"] == "no_answer"
        assert call(truth, n["deadline"], n["household_id"], "run-a")[0]["outcome"] == "no_answer"


def test_an_unqueued_request_is_never_placed():
    truth = contact.load(S1 / "contact_truth.json")
    result, events = call(truth, 500.0, HERO["household_id"], "run-a", queued=False)
    assert result["outcome"] == "failed" and not result["answered"] and not events


def test_baseline_and_relay_hear_the_same_residents():
    truth = contact.load(S1 / "contact_truth.json")
    for household_id in sorted(truth)[:20] + [HERO["household_id"]]:
        for ts in (24.0, 150.0, 300.0, 500.0):
            baseline, _ = call(truth, ts, household_id, "run-baseline")
            relay, _ = call(truth, ts, household_id, "run-relay")
            assert (baseline["outcome"], baseline.get("text")) == (relay["outcome"], relay.get("text"))


def test_w4_scores_the_real_scenario_files_directly():
    run_id = "run-w4"
    proposals = [{"_id": f"x-{n['needle_id']}", "run_id": run_id, "household_id": n["household_id"],
                  "ts": n["deadline"] - 1, "cited_event_ids": n["required_event_ids"][:2]} for n in NEEDLES]
    proposals.append({"_id": "x-decoy", "run_id": run_id, "household_id": DECOYS[0]["household_id"],
                      "ts": 10.0, "cited_event_ids": DECOYS[0]["event_ids"]})
    score = score_run(run_id, scenario_id="s1", proposals=proposals, needles=NEEDLES, decoys=DECOYS, promises=PROMISES,
                      registry=REGISTRY_DOCS, contacts=EVENTS, probes=[], as_of=META["end_ts"])
    assert score["needle_recall"] == 1.0 and score["impact"]["false_escalations"] == 1
    assert Counter(r["kind"] for r in score["detail"]["needles"]) == Counter(n["kind"] for n in NEEDLES)
