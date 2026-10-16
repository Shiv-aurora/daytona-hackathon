"""The demo HTTP workflow against a genuine local SurrealDB, without provider calls."""

import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from api.server import make_handler
from db.recovery import SurrealRecoveryStore

SEED = Path(__file__).resolve().parents[1] / "data/demo/seed.json"
RUN = "demo-current"


@pytest.fixture
def service():
    store = SurrealRecoveryStore(seed=json.loads(SEED.read_text()))
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(None, recovery_store=store))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(path, body=None):
        request = Request(
            f"http://127.0.0.1:{server.server_port}{path}",
            data=json.dumps(body).encode() if body is not None else None,
            headers={"Content-Type": "application/json"},
        )
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            return response.status, json.load(response)

    yield call, store
    server.shutdown()
    thread.join(timeout=5)
    server.server_close()
    store.close()


def test_http_report_to_verified_receipt_and_measured_history(service):
    call, _ = service
    status, result = call(f"/runs/{RUN}/reports", {
        "disaster_id": "demo-storm-2026", "survivor_id": "current-survivor-1",
        "text": "We need food and blankets", "idempotency_key": "integration-report",
    })
    assert status == 200
    assert {request["category"] for request in result["requests"]} == {"food", "supplies"}
    request_id = next(request["id"] for request in result["requests"] if request["category"] == "food")
    base = f"/runs/{RUN}/requests/{request_id}"

    def delivery(attempt):
        assert call(base + "/claim", {
            "organization_id": "demo-food", "promised_at": "2026-10-17T12:00:00Z",
            "idempotency_key": f"integration-claim-{attempt}",
        })[0] == 200
        code, reported = call(base + "/delivery", {
            "organization_id": "demo-food", "notes": "Organization reports delivery",
            "idempotency_key": f"integration-delivery-{attempt}",
        })
        assert code == 200
        assert reported["request"]["status"] == "awaiting_verification"

    delivery(1)
    assert call(base + "/verify", {
        "received": True, "source": "survivor_call", "evidence_ids": ["invented-call"],
        "notes": "Forged provider result", "idempotency_key": "forged-receipt",
    })[0] == 400
    code, failed = call(base + "/verify", {
        "received": False, "source": "human_review", "evidence_ids": [],
        "notes": "Coordinator confirmed the delivery did not arrive",
        "idempotency_key": "integration-not-received",
    })
    assert code == 200
    assert failed["request"]["status"] == "reopened"

    delivery(2)
    payload = {
        "received": True, "source": "human_review", "evidence_ids": [],
        "notes": "Coordinator verified receipt", "idempotency_key": "integration-received",
    }
    code, verified = call(base + "/verify", payload)
    assert code == 200
    assert verified["request"]["status"] == "resolved"
    assert call(base + "/verify", payload) == (200, verified)
    assert call(base + "/verify", {**payload, "received": False})[0] == 409
    assert call(f"/runs/demo-history/requests/{request_id}/verify", payload)[0] == 404

    code, board = call(f"/runs/{RUN}/board")
    assert code == 200
    assert "lesson-confirm-handoff" in {lesson["id"] for lesson in board["lessons"]}
    assert len([v for v in board["verifications"] if v["request_id"] == request_id]) == 2
    assert all(event["run_id"] == RUN for event in board["system_events"])
    assert "phone" not in json.dumps(board).lower()

    code, comparison = call(f"/runs/{RUN}/evaluations/compare", {"idempotency_key": "integration-eval"})
    assert code == 200
    assert {row["variant"] for row in comparison["evaluations"]} == {"without_history", "with_history"}
    assert all(row["case_count"] == 3 for row in comparison["evaluations"])
    assert call(f"/runs/{RUN}/evaluations/compare", {"idempotency_key": "integration-eval"}) == (200, comparison)


def test_persistent_store_keeps_replay_ledger_after_restart(tmp_path):
    endpoint = f"surrealkv://{tmp_path / 'recovery'}"
    payload = {
        "survivor_id": "current-survivor-1", "category": "supplies",
        "description": "A new blanket request", "source_report_id": "restart-report",
        "idempotency_key": "restart-request",
    }
    store = SurrealRecoveryStore(endpoint, seed=json.loads(SEED.read_text()))
    try:
        request = store.create_request(RUN, payload)
    finally:
        store.close()
    reopened = SurrealRecoveryStore(endpoint)
    try:
        assert reopened.create_request(RUN, payload) == request
        board = reopened.get_board(RUN)
        assert len([row for row in board["requests"] if row["id"] == request["id"]]) == 1
    finally:
        reopened.close()
