from datetime import date

import pytest

from db.bootstrap import EVENTS, PROPOSALS
from eval.baseline import LongContextBaseline
from eval.harness import EvalConfig, RelaySystem, run_both, run_window, score_comparison
from eval.scorer import for_run, score_run
from eval.tests import sample_scenario as s
from eval.tests.fakes import ScriptedLLM, shared_memory
from runtime import Runtime, new_run_state
from runtime.tests.fakes import StubCalls
from schemas import SCENARIO_RUN_ID

DAY0 = date(2026, 9, 28)  # a Monday, as in W1's runtime tests
CHEN = {"name": "Mei Chen", "address": "41 Orchard St"}
PROMISE = "Visit note: her landlord promised to fix the boiler by Thursday."
TRUTH = {key: s.INPUTS[key] for key in ("needles", "decoys", "promises", "registry")}


def config(relay_every=24.0, baseline_every=24.0, relay_model=None, baseline_model="test/scripted", **overrides):
    fields = {"scenario_id": s.SCENARIO, "until_ts": s.AS_OF,
              "household_ids": ("hh-oakes", "hh-pell", "hh-ruiz", "hh-vance"),
              "relay_decision_every_hours": relay_every, "baseline_decision_every_hours": baseline_every,
              "relay_model": relay_model, "baseline_model": baseline_model}
    return EvalConfig(**{**fields, **overrides})


def note(event_id, ts, text, run_id=SCENARIO_RUN_ID, scenario_id="s1", **extra):
    """W5-style: visible identity hints only; run-generated events carry their household_id."""
    return {"_id": event_id, "run_id": run_id, "scenario_id": scenario_id, "ts": ts, "source": "visit_note",
            "text": text, "household_ref_raw": "Mrs. Chen", "address_raw": CHEN["address"], **extra}


def asked(answers):
    return [(answer["probe_ts"], answer["household_id"]) for answer in answers]


def test_relay_and_baseline_run_one_window_and_probes_and_are_scored_alike():
    memory = shared_memory([
        note("ev-1", 1.0, PROMISE),  # a Monday promise "by Thursday" falls due at hour 96
        note("relay-call", 30.0, "RELAY-ONLY: the boiler is still broken", run_id="relay-1", source="call_result",
             household_id="hh-chen"),
        note("other-note", 40.0, "OTHER-SCENARIO note", scenario_id="s2"),
    ], {"relay-1": {"hh-chen": CHEN}, "baseline-1": {"hh-chen": CHEN}})
    llm = ScriptedLLM(probe=lambda prompt: '{"open_promises": {"hh-chen": ["ev-1"]}}')
    relay = RelaySystem(Runtime(memory, StubCalls(), DAY0, tick_hours=24.0), memory,
                        new_run_state("relay-1", 0.0, "s1"))
    baseline = LongContextBaseline(memory, llm, "baseline-1", "s1", decision_every_hours=24.0)
    setup = config(scenario_id="s1", until_ts=144.0, household_ids=("hh-chen",))

    answers = run_both(relay, baseline, setup)

    assert asked(answers["relay"]) == asked(answers["baseline"]) == [(72.0, "hh-chen"), (144.0, "hh-chen")]
    assert relay.now == baseline.now == 144.0
    assert [a["source_event_ids"] for a in answers["relay"]] == [["ev-1"], []]  # lapsed after hour 96
    assert [e["_id"] for e in baseline.log] == ["ev-1"]
    assert not any("RELAY-ONLY" in prompt or "OTHER-SCENARIO" in prompt for prompt in llm.prompts)

    truth = {"needles": [], "decoys": [], "registry": [{"household_id": "hh-chen", "opt_in": True}],
             "promises": [{"household_id": "hh-chen", "source_event_id": "ev-1", "made_ts": 1.0, "due_ts": 96.0}]}
    result = score_comparison(setup, relay_run_id="relay-1", baseline_run_id="baseline-1", truth=truth,
                              proposals=memory.db[PROPOSALS].find(), contacts=memory.db[EVENTS].find(),
                              probes=answers["relay"] + answers["baseline"])
    assert (result["decision_every_hours"], result["same_decision_schedule"]) == ({"relay": 24.0, "baseline": 24.0},
                                                                                  True)
    assert (result["model"], result["same_model"]) == ({"relay": None, "baseline": "test/scripted"}, False)
    relay_recall, baseline_recall = result["relay"]["promise_recall"], result["baseline"]["promise_recall"]
    assert relay_recall["recall"] == baseline_recall["recall"] == 1.0  # both named ev-1 while it was open
    # Only the baseline still named ev-1 at hour 144, after it fell due.
    assert (relay_recall["named_not_open"], baseline_recall["named_not_open"]) == (0, 1)


class SteppedSystem:
    """Moves its clock in fixed steps, like a runtime with some tick length."""

    def __init__(self, step, answer_as="run-x", model=None):
        self.run_id, self.now, self.decision_every_hours = "run-x", 0.0, step
        self.answer_as, self.model = answer_as, model

    def advance_to(self, ts):
        while self.now < ts:
            self.now += self.decision_every_hours

    def probe(self, ts, household_ids):
        return [{"run_id": self.answer_as, "probe_ts": ts, "household_id": household_id, "source_event_ids": []}
                for household_id in household_ids]


def test_a_system_must_decide_as_often_and_with_the_model_the_config_declares():
    relay, baseline = SteppedSystem(1.0), SteppedSystem(24.0, model="test/scripted")
    assert set(run_both(relay, baseline, config(relay_every=1.0))) == {"relay", "baseline"}
    with pytest.raises(ValueError, match="declares 24h"):
        run_both(relay, baseline, config(relay_every=24.0))  # Relay really ticks hourly
    with pytest.raises(ValueError, match="declares 24h and 'other/model'"):
        run_both(relay, baseline, config(relay_every=1.0, baseline_model="other/model"))


def test_every_result_states_each_systems_cadence_and_model():
    result = score_comparison(config(relay_every=1.0, relay_model="m/one", baseline_model="m/one"),
                              relay_run_id=s.RELAY, baseline_run_id=s.BASELINE, truth=TRUTH,
                              proposals=s.PROPOSALS, contacts=s.CONTACTS, probes=s.PROBES)
    assert result["decision_every_hours"] == {"relay": 1.0, "baseline": 24.0}
    assert result["same_decision_schedule"] is False and result["same_model"] is True
    assert result["probe_times"] == [72.0, 144.0, 216.0]


def mirrored(docs):
    """The Relay run's documents plus an exact copy under the baseline's run_id; shared ones kept."""
    return ([doc for doc in docs if doc.get("run_id") != s.BASELINE]
            + [{**doc, "run_id": s.BASELINE} for doc in for_run(docs, s.RELAY)])


def test_identical_behaviour_gets_an_identical_score():
    result = score_comparison(config(), relay_run_id=s.RELAY, baseline_run_id=s.BASELINE, truth=TRUTH,
                              proposals=mirrored(s.PROPOSALS), contacts=mirrored(s.CONTACTS),
                              probes=mirrored(s.PROBES))
    assert {**result["baseline"], "run_id": s.RELAY} == result["relay"]


def test_the_score_does_not_depend_on_which_run_is_called_relay():
    pool = {"truth": TRUTH, "proposals": s.PROPOSALS, "contacts": s.CONTACTS, "probes": s.PROBES}
    straight = score_comparison(config(), relay_run_id=s.RELAY, baseline_run_id=s.BASELINE, **pool)
    swapped = score_comparison(config(), relay_run_id=s.BASELINE, baseline_run_id=s.RELAY, **pool)
    assert straight["relay"] == swapped["baseline"] and straight["baseline"] == swapped["relay"]
    assert straight["relay"] == score_run(s.RELAY, **s.INPUTS)  # the scorer W4-C1's tests pin down


@pytest.mark.parametrize("relay_id, baseline_id", [("run-a", "run-a"), (SCENARIO_RUN_ID, "run-b"), ("", "run-b")])
def test_comparison_needs_two_distinct_real_runs(relay_id, baseline_id):
    with pytest.raises(ValueError):
        score_comparison(config(), relay_run_id=relay_id, baseline_run_id=baseline_id, truth=TRUTH,
                         proposals=[], contacts=[], probes=[])


def test_comparison_needs_the_whole_truth():
    without_needles = {key: value for key, value in TRUTH.items() if key != "needles"}
    with pytest.raises(ValueError):
        score_comparison(config(), relay_run_id="run-a", baseline_run_id="run-b", truth=without_needles,
                         proposals=[], contacts=[], probes=[])


def test_every_system_must_stop_exactly_at_each_probe_and_answer_as_itself():
    assert len(run_window(SteppedSystem(24.0), config())) == 3 * 4  # probes at hours 72, 144, 216
    with pytest.raises(ValueError, match="divide"):
        run_window(SteppedSystem(10.0), config())  # would probe at hour 80, having seen 8 more hours
    with pytest.raises(ValueError):
        run_window(SteppedSystem(24.0, answer_as="run-y"), config())
