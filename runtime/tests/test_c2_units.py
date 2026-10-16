import io
import json
from datetime import date

import pytest

from runtime.clock import SimClock
from runtime.extract import extract
from runtime.goals import goal_metrics
from runtime.llm import (
    CachedLLM,
    LLMResponse,
    LLMUnavailable,
    OpenRouterClient,
    TokenLedger,
)
from runtime.llm_paths import parse_decision, parse_extraction
from runtime.policy import LEAD_HOURS_BOUNDS, review
from runtime.retrieval import retrieve
from runtime.tests.fakes import InMemoryMemory, ScriptedLLM

STORM = SimClock("2021-09-01T20:00:00")  # Scenario 1's day 0: the storm, 20:00 New York time
FRI_1436 = 42.6  # when the Mrs. Chen visit note was written
CHEN_NOTE = ("Visited Mrs. Chen, 82, at 41-22 41st Ave. Lives alone, speaks mostly Mandarin. Basement flooded, "
             "no power since Wednesday night. Her son Wei is coming Tuesday to help clean out and take her to "
             "stay with him. Registered her for follow-up calls.")


def test_the_clock_dates_deadlines_like_the_scenario_ground_truth():
    assert STORM.at(FRI_1436).isoformat() == "2021-09-03T14:36:00"  # scenario wall-clock time, no zone
    assert STORM.end_of_day(date(2021, 9, 7)) == 144.0  # "Tuesday" in the Mrs. Chen note
    assert STORM.end_of_day(date(2021, 9, 4)) == 72.0
    assert SimClock(date(2026, 9, 28)).end_of_day(date(2026, 10, 1)) == 96.0  # midnight day 0: end of that day


def test_scenario_phrasings_are_extracted_without_a_model():
    found = extract(CHEN_NOTE, FRI_1436, STORM)
    assert found.household_ref == {"address": "41-22 41st Ave", "name": "Mrs Chen"}
    [promise] = found.promises  # "since Wednesday night" looks back and is not a deadline
    assert promise.due_ts == 144.0 and "son Wei is coming Tuesday" in promise.text
    friday_1559, sunday_0959 = 43.992, 85.992
    assert [p.due_ts for p in extract("Red Cross will deliver a battery unit Saturday.", friday_1559, STORM).promises] == [72.0]
    assert [p.due_ts for p in extract("Red Cross will bring meals this afternoon.", sunday_0959, STORM).promises] == [96.0]
    assert [p.due_ts for p in extract("FEMA inspection is set for Sep 17.", 300.0, STORM).promises] == [384.0]

    plumber = extract("Landlord told them a plumber is coming Tuesday.", FRI_1436, STORM).promises[0].keywords
    repaired = extract("HPD reinspection at 31-27 90 ST BSMT: plumbing repaired.", 150.0, STORM).fulfilments[0]
    assert plumber & repaired == {"plumb"}  # "plumber" and "plumbing" meet
    assert extract("Neighbor says his daughter picked him up.", 150.0, STORM).fulfilments


class FakeHTTPResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_openrouter_request_and_usage_without_the_network():
    sent = {}

    def opener(request, timeout):
        sent.update(url=request.full_url, auth=request.get_header("Authorization"), body=json.loads(request.data))
        return FakeHTTPResponse(json.dumps({"model": "anthropic/claude-sonnet-5", "usage": {"prompt_tokens": 42, "cost": 0.00042,
                                "completion_tokens": 7}, "choices": [{"message": {"content": "{}"}}]}).encode())

    messages = [{"role": "user", "content": "hi"}]
    response = OpenRouterClient("test-key", opener=opener).complete(messages, max_tokens=50)
    assert response == LLMResponse("{}", "anthropic/claude-sonnet-5", 42, 7, 0.00042)
    assert sent == {"url": "https://openrouter.ai/api/v1/chat/completions", "auth": "Bearer test-key",
                    "body": {"model": "anthropic/claude-sonnet-5", "messages": messages, "max_tokens": 50,
                             "temperature": 0, "usage": {"include": True}}}
    assert OpenRouterClient.from_env({}) is None  # no key, no client: CI never calls out
    configured = OpenRouterClient.from_env({"OPENROUTER_API_KEY": "k", "OPENROUTER_MODEL": "anthropic/claude-haiku-4.5"})
    assert configured.model == "anthropic/claude-haiku-4.5"


def test_the_cache_makes_answers_deterministic_and_cache_only_mode_never_calls_out():
    cache, live = InMemoryMemory(), ScriptedLLM(lambda prompt: '{"answer": 1}')
    messages = [{"role": "user", "content": "same prompt"}]
    first, second = CachedLLM(cache, live).complete(messages, 100), CachedLLM(cache, live).complete(messages, 100)
    assert (first.cached, second.cached, first.text == second.text, len(live.prompts)) == (False, True, True, 1)
    frozen = CachedLLM(cache, model=live.model)  # a filled cache and no client: what CI and demos replay
    assert frozen.complete(messages, 100).text == first.text
    with pytest.raises(LLMUnavailable):
        frozen.complete([{"role": "user", "content": "a prompt nobody cached"}], 100)


def test_token_ledger_counts_only_live_calls():
    ledger = TokenLedger()
    ledger.add(LLMResponse("x", "m", 100, 20, 0.002))
    ledger.add(LLMResponse("x", "m", 100, 20, 0.002, cached=True))
    assert ledger.as_metrics() == {"llm_calls": 1.0, "llm_cached_calls": 1.0, "llm_prompt_tokens": 100.0,
                                   "llm_completion_tokens": 20.0, "llm_cost_usd": 0.002}


def test_model_output_is_validated_before_use():
    reply = ('Sure! {"promises": [{"who": "son Wei", "what": "take her to stay with him", "due_date": "2021-09-07"},'
             ' {"who": "x", "what": "y", "due_date": "2030-01-01"}], "kept_promise_ids": ["p-open", "p-invented"]}')
    found = parse_extraction(reply, FRI_1436, STORM, {"p-open"})
    assert [(p.text, p.due_ts) for p in found.promises] == [("son Wei: take her to stay with him", 144.0)]
    assert found.kept_promise_ids == ("p-open",)  # ids the model was never shown are ignored
    assert parse_extraction("not json", FRI_1436, STORM, set()) is None
    assert parse_extraction('{"promises": "oops"}', FRI_1436, STORM, set()) is None

    decision = parse_decision('{"cited_event_ids": ["e1", "e-unseen", "e1"], "suggested_action": "visit", '
                              '"rationale": "Crew found no one home."}', {"e1", "e2"})
    assert decision.cited_event_ids == ("e1",) and decision.suggested_action == "visit"
    assert parse_decision('{"cited_event_ids": [], "suggested_action": "evacuate"}', {"e1"}) is None


def indexed(event_id, ts, run_id="scenario", scenario_id="s1"):
    return {"_id": event_id, "run_id": run_id, "scenario_id": scenario_id, "ts": ts, "source": "crew",
            "text": "boiler"}


def test_retrieval_drops_future_and_other_run_results_whatever_the_backend_returns():
    class LeakyIndex:
        def search_events(self, run_id, scenario_id, query, as_of_ts, limit):
            return [indexed("ok", 10.0), indexed("future", 99.0), indexed("other-run", 5.0, run_id="run-b"),
                    indexed("other-scenario", 5.0, scenario_id="s2")]

    safe, leaked = retrieve(LeakyIndex(), "run-a", "s1", "boiler", as_of_ts=50.0, limit=5)
    assert [e["_id"] for e in safe] == ["ok"] and leaked == ["future", "other-run", "other-scenario"]
    assert retrieve(None, "run-a", "s1", "boiler", 50.0, 5) == ([], [])


def test_goal_metrics_count_promises_met_before_they_fall_due():
    promises = [
        {"_id": "kept-in-time", "due_ts": 50.0, "status": "kept", "status_ts": 40.0},
        {"_id": "escalated-in-time", "due_ts": 60.0, "status": "lapsed", "status_ts": 61.0},
        {"_id": "missed", "due_ts": 70.0, "status": "lapsed", "status_ts": 71.0},
        {"_id": "not-due-yet", "due_ts": 500.0, "status": "open"},
    ]
    proposals = [{"promise_id": "escalated-in-time", "ts": 55.0}, {"promise_id": "missed", "ts": 71.0}]
    metrics = goal_metrics(promises, proposals, now=100.0)
    assert (metrics["promises_due"], metrics["promises_met"], metrics["promises_open"]) == (3.0, 2.0, 1.0)
    assert metrics["promises_on_time_pct"] == pytest.approx(200 / 3)
    assert (metrics["early_checkins"], metrics["unneeded_checkin_pct"]) == (1.0, 0.0)
    assert goal_metrics([], [], now=10.0)["promises_on_time_pct"] is None  # nothing due: undefined, not 100


def test_policy_moves_one_step_at_a_time_and_never_leaves_its_bounds():
    missing = {"promises_due": 4.0, "promises_on_time_pct": 25.0, "early_checkins": 0.0, "unneeded_checkin_pct": 0.0}
    policy, seen = {"lead_hours": 0.0}, []
    while (change := review(policy, missing)) is not None:
        policy = change[0]
        seen.append(policy["lead_hours"])
    assert seen == [12.0, 24.0, 36.0, 48.0] and policy["lead_hours"] == LEAD_HOURS_BOUNDS[1]
    overcautious = {"promises_due": 4.0, "promises_on_time_pct": 100.0, "early_checkins": 4.0, "unneeded_checkin_pct": 75.0}
    assert review({"lead_hours": 12.0}, overcautious)[0] == {"lead_hours": 0.0}
    assert review({"lead_hours": 0.0}, overcautious) is None  # already at the floor
    assert review({"lead_hours": 0.0}, {**missing, "promises_due": 1.0}) is None  # one promise is not a trend
