import http.client
import json
import threading
from http.server import ThreadingHTTPServer

import pytest

from api.relay import handle
from api.server import make_handler
from db.bootstrap import CALL_REQUESTS, METRICS, POLICY_CHANGES, REGISTRY, SYSTEM_EVENTS
from db.events import record_event
from db.runs import save_run_state
from db.scope import RunScope
from db.writes import insert_proposal, schedule_call
from memory.adapter import DemoMemory
from memory.startup import start_run

DAY0 = "2021-09-01T20:00:00-04:00"


def seed_run(db, run_id, marker):
    """A started run with one of everything, all tagged with `marker` so leaks are easy to spot."""
    start_run(db, run_id, "s1", DAY0, start_ts=0.0)
    run, memory = RunScope(db, run_id), DemoMemory(db)
    memory.apply_household_event(run_id, "hh-chen", {"_id": "s1_e_001", "run_id": "scenario", "ts": 10.0})
    memory.insert_promise({"_id": f"{run_id}-p", "run_id": run_id, "scenario_id": "s1", "household_id": "hh-chen",
                           "text": marker, "keywords": [], "made_ts": 10.0, "due_ts": 40.0, "status": "open",
                           "source_event_id": "s1_e_001"})
    for suffix in ("a", "b"):
        insert_proposal(run, {"_id": f"{run_id}-prop-{suffix}", "scenario_id": "s1", "household_id": "hh-chen",
                              "kind": "check_in", "status": "pending", "reason": marker, "ts": 41.0,
                              "cited_event_ids": ["s1_e_001"]})
    schedule_call(run, {"_id": f"{run_id}-call", "scenario_id": "s1", "household_id": "hh-chen",
                        "proposal_id": f"{run_id}-prop-a", "purpose": "promise_check_in", "requested_ts": 42.0})
    record_event(run, {"_id": f"{run_id}-call:result", "scenario_id": "s1", "ts": 43.0, "source": "call_result",
                       "household_id": "hh-chen", "text": marker, "answered": True})
    run.insert(METRICS, {"_id": f"{run_id}-m", "name": "promises_open", "value": 1.0, "scope": "goal", "ts": 42.0})
    run.insert(POLICY_CHANGES, {"_id": f"{run_id}-pc", "version": 1, "what_changed": marker, "params": {},
                                "metric_values": {}, "ts": 42.0})
    save_run_state(db, {"run_id": run_id, "scenario_id": "s1", "tick": 2, "now_ts": 48.0, "cursor_ts": 43.0,
                        "cursor_id": f"{run_id}-call:result", "pending_proposal_ids": [], "pending_call_ids": [],
                        "policy_version": 1})


@pytest.fixture
def relay(database):
    database[REGISTRY].insert_one({"household_id": "hh-chen", "scenario_id": "s1", "opt_in": True,
                                   "name": "Mei Chen", "address": "41-22 Hollow Oak Ln", "registered_ts": 0.0})
    database[REGISTRY].insert_one({"household_id": "hh-s2", "scenario_id": "s2", "opt_in": True})
    inputs = RunScope.scenario(database)
    record_event(inputs, {"_id": "s1_e_001", "run_id": "scenario", "scenario_id": "s1", "ts": 10.0,
                          "source": "visit_note", "text": "Visited Mrs. Chen at 41-22 Hollow Oak Ln."})
    record_event(inputs, {"_id": "s1_e_999", "run_id": "scenario", "scenario_id": "s1", "ts": 500.0,
                          "source": "visit_note", "text": "A note from the future."})
    seed_run(database, "run-a", "ALPHA")
    seed_run(database, "run-b", "BRAVO")
    return database


def test_runs_lists_every_started_run_with_its_clock(relay):
    assert handle(relay, "GET", "/runs") == (200, {"runs": [{"run_id": "run-a", "scenario_id": "s1", "now_ts": 48.0},
                                                            {"run_id": "run-b", "scenario_id": "s1", "now_ts": 48.0}]})


def test_the_console_is_strictly_run_scoped(relay):
    status, snap = handle(relay, "GET", "/runs/run-a/console")
    assert status == 200 and snap["run"] == {"run_id": "run-a", "scenario_id": "s1", "day0": DAY0, "mode": "live"}
    assert snap["now_ts"] == 48.0 and snap["start_ts"] == 0.0
    for key in ("households", "promises", "proposals", "call_requests", "system_events", "metrics", "policy_changes"):
        assert snap[key] and all(doc["run_id"] == "run-a" for doc in snap[key]), key
    assert [e["_id"] for e in snap["events"]] == ["s1_e_001", "run-a-call:result"]  # not run-b's, not the future
    assert [e["household_id"] for e in snap["registry"]] == ["hh-chen"]  # the run's own scenario and households
    assert "BRAVO" not in json.dumps(snap, default=str)


def test_decisions_are_forward_only_and_validated(relay):
    status, proposal = handle(relay, "POST", "/runs/run-a/proposals/run-a-prop-a/decision", {"status": "approved"})
    assert status == 200 and proposal["status"] == "approved" and proposal["status_ts"] == 48.0
    assert handle(relay, "POST", "/runs/run-a/proposals/run-a-prop-a/decision", {"status": "dismissed",
                                                                                  "reason": "x"})[0] == 409
    assert handle(relay, "POST", "/runs/run-a/proposals/run-a-prop-b/decision", {"status": "dismissed"})[0] == 400
    assert handle(relay, "POST", "/runs/run-a/proposals/run-a-prop-b/decision", {"status": "maybe"})[0] == 400
    status, dismissed = handle(relay, "POST", "/runs/run-a/proposals/run-a-prop-b/decision",
                               {"status": "dismissed", "reason": " Son took her in "})
    assert status == 200 and dismissed["decision_reason"] == "Son took her in"
    decisions = handle(relay, "GET", "/runs/run-a/console")[1]["decisions"]
    assert decisions == {"run-a-prop-a": {"status": "approved", "ts": 48.0, "reason": None},
                         "run-a-prop-b": {"status": "dismissed", "ts": 48.0, "reason": "Son took her in"}}
    # Another run's proposal can't be decided through this run, and unknown runs are 404.
    assert handle(relay, "POST", "/runs/run-a/proposals/run-b-prop-a/decision", {"status": "approved"})[0] == 404
    assert handle(relay, "POST", "/runs/nope/proposals/run-a-prop-a/decision", {"status": "approved"})[0] == 404
    assert handle(relay, "GET", "/runs/run-b/console")[1]["decisions"] == {}


def test_escalation_is_idempotent_and_run_scoped(relay):
    status, proposal = handle(relay, "POST", "/runs/run-a/calls/run-a-call/escalate")
    assert status == 200 and proposal["_id"] == "run-a-call:human" and proposal["urgent"]
    assert proposal["status"] == "pending" and proposal["cited_event_ids"] == ["run-a-call:result"]
    assert handle(relay, "POST", "/runs/run-a/calls/run-a-call/escalate") == (200, proposal)
    assert handle(relay, "POST", "/runs/run-a/calls/run-b-call/escalate")[0] == 404
    assert RunScope(relay, "run-a").count(SYSTEM_EVENTS, {"action": "human_escalation_requested"}) == 1
    assert RunScope(relay, "run-b").count(CALL_REQUESTS) == 1


def test_bad_paths_and_the_scenario_pseudo_run(relay):
    assert handle(relay, "GET", "/runs/run-a/nope")[0] == 404
    assert handle(relay, "GET", "/runs/scenario/console")[0] in (400, 404)
    status, body = handle(relay, "GET", "/health")
    assert status == 200 and body["ok"] is True and body["daytona"]["provider"] in ("daytona", "local")


def test_the_http_server_speaks_json_with_cors(relay):
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(relay, "https://console.example"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        def request(method, path, body=None, raw=None):
            connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
            data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
            connection.request(method, path, body=data, headers={"Content-Type": "application/json"})
            response = connection.getresponse()
            payload = response.read()
            return response.status, dict(response.getheaders()), json.loads(payload) if payload else None

        status, headers, _ = request("OPTIONS", "/runs/run-a/proposals/run-a-prop-a/decision")
        assert status == 204 and headers["Access-Control-Allow-Origin"] == "https://console.example"
        assert "POST" in headers["Access-Control-Allow-Methods"]
        status, _, body = request("GET", "/runs")
        assert status == 200 and [run["run_id"] for run in body["runs"]] == ["run-a", "run-b"]
        assert request("POST", "/runs/run-a/proposals/run-a-prop-a/decision", raw=b"{not json")[0] == 400
        status, _, body = request("POST", "/runs/run-a/proposals/run-a-prop-a/decision", {"status": "approved"})
        assert status == 200 and body["status"] == "approved"
    finally:
        server.shutdown()
