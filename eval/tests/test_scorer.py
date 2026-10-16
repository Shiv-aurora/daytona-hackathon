import pytest

from eval.scorer import (
    false_escalations,
    for_run,
    probe_times,
    promise_recall_by_age,
    score_needle,
    score_run,
    silent_households,
    to_days,
    to_hours,
)
from eval.tests import sample_scenario as s
from schemas import SCENARIO_RUN_ID, GoalStatus, ImpactMetrics, Score


def score(run_id, **overrides):
    return score_run(run_id, **{**s.INPUTS, **overrides})


def bucket(label, lo, hi, open_, recalled, recall):
    return {"label": label, "min_days": lo, "max_days": hi, "open": open_, "recalled": recalled, "recall": recall}


def test_relay_fixture_scores_exactly():
    assert score(s.RELAY) == {
        "run_id": s.RELAY,
        "scenario_id": s.SCENARIO,
        "as_of": 240.0,
        "needle_recall": 2 / 3,
        "impact": {"households_reached_in_time": 1, "people_reached_in_time": 2,
                   "days_warning_gained": 1.875, "false_escalations": 1},
        # Due by hour 240: pr-2, pr-3, pr-5, pr-6. On time: pr-3 (kept 80 < 90), pr-5 (p-6 at 85 < 100).
        "goal": {"promises_on_time_pct": 50.0, "silent_households": 1},
        "promise_recall": {"probe_times": [72.0, 144.0, 216.0], "open": 8, "recalled": 6, "recall": 0.75,
                           "named_not_open": 1, "by_age": [
                               bucket("0-1d", 0, 1, 2, 2, 1.0),
                               bucket("1-3d", 1, 3, 3, 3, 1.0),
                               bucket("3-7d", 3, 7, 2, 1, 0.5),
                               bucket("7-14d", 7, 14, 1, 0, 0.0),
                               bucket("14d+", 14, None, 0, 0, None),
                           ]},
        "detail": {
            "needles": [
                {"needle_id": "needle-oakes", "kind": "broken_promise", "caught": True,
                 "escalated_at": 96.0, "reached_in_time": True, "warning_days": 3.0},
                {"needle_id": "needle-vance", "kind": "cross_service_join", "caught": False,
                 "escalated_at": None, "reached_in_time": False, "warning_days": None},
                {"needle_id": "needle-ruiz", "kind": "silent_household", "caught": True,
                 "escalated_at": 192.0, "reached_in_time": False, "warning_days": 0.75},
            ],
            "false_escalation_decoy_ids": ["decoy-pell-outage"],
            "promises_due": 4,
            "promises_on_time": 2,
            "silent_household_ids": ["hh-ruiz"],
        },
    }


def test_baseline_run_in_the_same_fixture_scores_from_its_own_documents():
    result = score(s.BASELINE)
    # b-1 catches needle-vance at 110: reached (110 + 24 < 200), warning (200 - 110) / 24 = 3.75.
    assert [n["needle_id"] for n in result["detail"]["needles"] if n["caught"]] == ["needle-vance"]
    assert result["impact"] == {"households_reached_in_time": 1, "people_reached_in_time": 3,
                                "days_warning_gained": 3.75, "false_escalations": 1}
    # On time: pr-2 (b-2 cites ev-101 at 60 < 80), pr-3 (kept). hh-oakes: never heard from in this run.
    assert result["goal"] == {"promises_on_time_pct": 50.0, "silent_households": 1}
    assert result["detail"]["silent_household_ids"] == ["hh-oakes"]
    recall = result["promise_recall"]
    assert [b["recall"] for b in recall["by_age"]] == [1.0, 2 / 3, 0.5, 0.0, None]
    assert (recall["recalled"], recall["recall"], recall["named_not_open"]) == (5, 5 / 8, 1)


def test_headline_keys_match_the_shared_score_contract():
    result = score(s.RELAY)
    assert set(result) >= Score.__required_keys__
    assert set(result["impact"]) == ImpactMetrics.__required_keys__
    assert set(result["goal"]) == GoalStatus.__required_keys__


def test_other_runs_other_scenarios_and_unstamped_documents_never_count():
    visible = {"c-1", "c-2", "c-3", "c-4", "c-5", "c-6"}  # the Relay run's own, plus this scenario's
    own = {"proposals": for_run(s.PROPOSALS, s.RELAY), "probes": for_run(s.PROBES, s.RELAY),
           "contacts": [c for c in s.CONTACTS if c["_id"] in visible]}
    assert score(s.RELAY) == score(s.RELAY, **own)
    # The filter matters: stamped into the Relay run, the other proposals would change its score.
    leaked = score(s.RELAY, proposals=[{**p, "run_id": s.RELAY} for p in s.PROPOSALS])
    assert leaked["needle_recall"] == 1.0 and leaked["impact"]["false_escalations"] == 3


def test_scenario_contacts_count_for_every_run():
    # The scenario's visit note (c-6) is the only thing keeping hh-pell from counting as silent.
    without_visit = [c for c in s.CONTACTS if c["_id"] != "c-6"]
    assert score(s.RELAY, contacts=without_visit)["detail"]["silent_household_ids"] == ["hh-pell", "hh-ruiz"]
    assert score(s.BASELINE, contacts=without_visit)["detail"]["silent_household_ids"] == ["hh-oakes", "hh-pell"]


def test_a_run_with_no_documents_gets_no_credit():
    result = score("run-nobody")
    assert result["needle_recall"] == 0.0 and result["impact"]["false_escalations"] == 0
    assert result["detail"]["promises_on_time"] == 1  # pr-3 was kept by the family, not by any run
    assert result["detail"]["silent_household_ids"] == ["hh-oakes", "hh-ruiz"]
    assert (result["promise_recall"]["open"], result["promise_recall"]["recalled"]) == (8, 0)


def test_score_does_not_depend_on_document_order():
    reordered = {key: list(reversed(s.INPUTS[key])) for key in ("proposals", "contacts", "probes", "promises")}
    assert score(s.RELAY) == score(s.RELAY, **reordered)


NEEDLE = {"needle_id": "n", "kind": "broken_promise", "household_id": "hh-a",
          "required_event_ids": ["e1", "e2", "e3"], "deadline": 100.0, "danger_at": 120.0,
          "response_hours": 24.0, "people_at_risk": 1}


def proposal(ts, cites, household="hh-a"):
    return {"run_id": "r", "household_id": household, "ts": ts, "cited_event_ids": cites}


def test_needle_is_caught_by_two_required_citations_before_the_deadline_under_any_household_id():
    # A household the runtime filed itself has its own id, not W5's hidden one; the citations name the needle.
    filed = "filed:ev-7"
    assert score_needle(NEEDLE, [proposal(10.0, ["e1", "e2"], household=filed)])["caught"]
    assert score_needle(NEEDLE, [proposal(99.0, ["e1", "e2"])])["caught"]
    assert not score_needle(NEEDLE, [proposal(10.0, ["e1", "unrelated"], household=filed)])["caught"]
    assert not score_needle(NEEDLE, [proposal(100.0, ["e1", "e2"], household=filed)])["caught"]  # at the deadline
    assert not score_needle(NEEDLE, [proposal(10.0, ["invented-1", "invented-2"])])["caught"]


def test_needle_uses_the_earliest_qualifying_escalation():
    result = score_needle(NEEDLE, [proposal(90.0, ["e1", "e3"]), proposal(48.0, ["e2", "e3"]),
                                   proposal(20.0, ["e1"])])
    assert result["escalated_at"] == 48.0 and result["warning_days"] == 3.0


def test_help_must_land_strictly_before_danger_to_count_as_reached():
    assert not score_needle(NEEDLE, [proposal(96.0, ["e1", "e2"])])["reached_in_time"]  # 96 + 24 == 120
    assert score_needle(NEEDLE, [proposal(95.0, ["e1", "e2"])])["reached_in_time"]


def test_needle_that_cannot_be_caught_is_rejected():
    with pytest.raises(ValueError):
        score_needle({**NEEDLE, "required_event_ids": ["e1"]}, [])


def test_decoy_citation_is_one_false_escalation_per_proposal():
    decoys = [{"decoy_id": "d1", "household_id": "hh-a", "event_ids": ["d-e1", "d-e2"]}]
    proposals = [proposal(10.0, ["d-e1", "d-e2"]), proposal(20.0, ["e1", "e2"])]
    assert false_escalations(decoys, proposals) == {"count": 1, "decoy_ids": ["d1"]}


def test_silence_counts_only_households_strictly_opted_in():
    registry = [{"household_id": "a", "opt_in": True}, {"household_id": "b", "opt_in": True},
                {"household_id": "c", "opt_in": "yes"}, {"household_id": "d", "opt_in": True}]
    contacts = [{"household_id": "a", "ts": 28.0}, {"household_id": "b", "ts": 27.0}]
    # At hour 100: a heard 72h ago, b 73h ago, c not opted in, d never heard from.
    assert silent_households(registry, contacts, 100.0) == ["b", "d"]


def truth(source, household, made, due, kept=None):
    promise = {"household_id": household, "source_event_id": source, "made_ts": made, "due_ts": due}
    if kept is not None:
        promise.update(status="kept", status_ts=kept)
    return promise


def test_probes_ask_only_about_promises_open_at_that_moment():
    promises = [truth("e1", "a", 0.0, 200.0), truth("e2", "a", 0.0, 200.0, kept=72.0),
                truth("e3", "a", 0.0, 72.0), truth("e4", "b", 0.0, 200.0)]
    probes = [{"probe_ts": 72.0, "household_id": "a", "source_event_ids": ["e1", "e2"]},
              {"probe_ts": 50.0, "household_id": "b", "source_event_ids": ["e4"]}]  # off schedule
    result = promise_recall_by_age(promises, probes, as_of=100.0)
    # One probe, at hour 72. e2 was kept at 72 and e3 fell due at 72, so only e1 and e4 are open.
    # a names e1 (recalled) and e2 (not open); b gave no answer at 72, so e4 is a miss.
    assert (result["open"], result["recalled"], result["named_not_open"]) == (2, 1, 1)


def test_promise_age_buckets_include_their_lower_edge():
    promises = [truth("e1", "a", 48.0, 500.0), truth("e2", "a", 72.0, 500.0)]
    probes = [{"probe_ts": 72.0, "household_id": "a", "source_event_ids": ["e1"]}]
    by_age = promise_recall_by_age(promises, probes, as_of=72.0)["by_age"]
    assert by_age[0] == bucket("0-1d", 0, 1, 1, 0, 0.0)
    assert by_age[1] == bucket("1-3d", 1, 3, 1, 1, 1.0)


def test_probe_schedule_and_hour_day_conversion():
    assert probe_times(240.0) == [72.0, 144.0, 216.0]
    assert probe_times(72.0) == [72.0] and probe_times(71.5) == []
    assert to_days(36.0) == 1.5 and to_hours(3) == 72


def test_scoring_emits_one_replay_safe_system_event():
    first, again = [], []
    score(s.RELAY, emit=first.append)
    score(s.RELAY, emit=again.append)
    [event] = first
    assert event["_id"].startswith("sev-") and first == again
    assert {key: event[key] for key in ("run_id", "module", "action", "ts", "false_escalations")} == {
        "run_id": s.RELAY, "module": "eval", "action": "run_scored", "ts": 240.0, "false_escalations": 1}


@pytest.mark.parametrize("run_id", ["", SCENARIO_RUN_ID])
def test_only_a_real_run_can_be_scored(run_id):
    with pytest.raises(ValueError):
        score(run_id)
