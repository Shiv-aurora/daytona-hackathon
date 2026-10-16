"""Real embedded SurrealDB tests: no network, cloud or paid calls."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from contracts.demo import Conflict, InvalidInput, NotFound
from db.recovery import SurrealRecoveryStore


@pytest.fixture
def seed():
    return {
        "runs": [
            {"run_id": "r1", "disaster_id": "d1"},
            {
                "run_id": "r2",
                "disaster_id": "d2",
                "knowledge_cutoff": "2026-01-01T00:00:00Z",
            },
        ],
        "disasters": [{"id": "d1"}, {"id": "d2"}],
        "organizations": [{"id": "org", "capabilities": ["food"]}],
        "survivors": [
            {
                "id": "person",
                "run_id": "r1",
                "disaster_id": "d1",
                "display_name": "Demo survivor",
                "phone": "+15555550100",
                "contact": {"email": "private@example.test"},
                "call_opt_in": True,
            }
        ],
        "requests": [
            {
                "id": "request",
                "run_id": "r1",
                "disaster_id": "d1",
                "survivor_id": "person",
                "category": "food",
                "status": "open",
            }
        ],
        "lessons": [
            {
                "id": "past",
                "source_run_id": "r1",
                "source_disaster_id": "d1",
                "source_outcome_ids": ["v1"],
                "summary": "Confirm the handoff",
                "conditions": ["flood"],
                "recommendation": "Ask for receipt",
                "approved": True,
                "approved_at": "2025-01-01T00:00:00+00:00",
                "created_at": "2025-01-01T00:00:00Z",
            },
            {
                "id": "future",
                "source_run_id": "r1",
                "source_disaster_id": "d1",
                "source_outcome_ids": ["v1"],
                "approved": True,
                "approved_at": "2027-01-01T00:00:00Z",
                "created_at": "2025-01-01T00:00:00Z",
            },
            {
                "id": "draft",
                "source_run_id": "r1",
                "source_disaster_id": "d1",
                "approved": False,
            },
        ],
    }


@pytest.fixture
def store(seed):
    db = SurrealRecoveryStore(seed=seed)
    yield db
    db.close()


def claim(key="claim"):
    return {
        "organization_id": "org",
        "promised_at": "2026-10-16T17:00:00Z",
        "idempotency_key": key,
    }


def test_transitions_replay_and_scope(store):
    row = store.claim_request("r1", "request", claim())
    assert row["status"] == "claimed"
    assert store.claim_request("r1", "request", claim()) == row
    with pytest.raises(Conflict):
        store.claim_request("r1", "request", claim("other"))
    with pytest.raises(Conflict):
        store.claim_request(
            "r1", "request", {**claim(), "promised_at": "2026-10-17T17:00:00Z"}
        )
    with pytest.raises(NotFound):
        store.report_delivery(
            "r2", "request", {"organization_id": "org", "idempotency_key": "wrong"}
        )
    row = store.report_delivery(
        "r1", "request", {"organization_id": "org", "idempotency_key": "delivery"}
    )
    assert row["status"] == "awaiting_verification"
    payload = {
        "received": None,
        "source": "human_review",
        "idempotency_key": "no-answer",
    }
    assert (
        store.verify_request("r1", "request", payload)["request"]["status"]
        == "awaiting_verification"
    )
    payload = {"received": False, "source": "human_review", "idempotency_key": "missed"}
    assert (
        store.verify_request("r1", "request", payload)["request"]["status"]
        == "reopened"
    )
    payload = {
        "received": True,
        "source": "human_review",
        "idempotency_key": "received",
    }
    result = store.verify_request("r1", "request", payload)
    assert result["request"]["status"] == "resolved"
    assert store.verify_request("r1", "request", payload) == result
    board = store.get_board("r1")
    assert len(board["verifications"]) == 3
    assert all(
        r["run_id"] == "r1" and r["disaster_id"] == "d1" for r in board["system_events"]
    )


def test_board_privacy_and_cutoff(store):
    survivor = store.get_board("r1")["survivors"][0]
    assert "phone" not in survivor and "contact" not in survivor
    board = store.get_board("r2")
    assert board["survivors"] == []
    assert {r["id"] for r in board["lessons"]} == {"past"}


def test_restart_durable_replay_and_atomic_competing_connections(tmp_path, seed):
    endpoint = f"surrealkv://{tmp_path / 'fresh-demo'}"
    one = SurrealRecoveryStore(endpoint, seed=seed)
    with pytest.raises(Conflict, match="already open"):
        SurrealRecoveryStore(endpoint)

    def attempt(pair):
        db, key = pair
        try:
            return db.claim_request("r1", "request", claim(key))
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, [(one, "a"), (one, "b")]))
    assert sum(r is not None for r in results) == 1
    winner = "a" if results[0] else "b"
    one.close()
    reopened = SurrealRecoveryStore(endpoint)
    try:
        assert (
            reopened.claim_request("r1", "request", claim(winner))["status"]
            == "claimed"
        )
        assert len(reopened.get_board("r1")["system_events"]) == 2
    finally:
        reopened.close()


def test_seed_scope_validation_and_explicit_reset(store, seed):
    bad = deepcopy(seed)
    bad["survivors"][0]["disaster_id"] = "d2"
    with pytest.raises(InvalidInput):
        store.seed(bad, reset=True)
    store.claim_request("r1", "request", claim())
    store.seed(seed)  # normal start must not erase user interactions
    assert store.get_board("r1")["requests"][0]["status"] == "claimed"
    store.seed(seed, reset=True)
    assert store.get_board("r1")["requests"][0]["status"] == "open"


def test_cloud_is_rejected_before_connection():
    with pytest.raises(InvalidInput):
        SurrealRecoveryStore("ws://old-service.example/rpc")


def test_approval_publishes_reviewed_lesson_and_preserves_source_links(seed):
    seed["runs"][1]["knowledge_cutoff"] = "2099-01-01T00:00:00Z"
    seed["verifications"] = [
        {
            "id": "v1",
            "run_id": "r1",
            "disaster_id": "d1",
            "request_id": "request",
            "received": True,
        }
    ]
    store = SurrealRecoveryStore(seed=seed)
    try:
        lesson = store.save_lesson(
            "r1",
            {
                "summary": "Confirm receipt",
                "conditions": ["flood"],
                "recommendation": "Follow up",
                "source_outcome_ids": ["v1"],
                "idempotency_key": "draft",
            },
        )
        assert lesson["id"] not in {r["id"] for r in store.get_board("r2")["lessons"]}
        approved = store.approve_lesson(
            "r1", lesson["id"], {"idempotency_key": "approve"}
        )
        assert approved["approved"] is True
        public = next(
            r for r in store.get_board("r2")["lessons"] if r["id"] == lesson["id"]
        )
        assert public["source_outcome_ids"] == ["v1"]
        assert public["source_run_id"] == "r1"
        assert (
            store.approve_lesson("r1", lesson["id"], {"idempotency_key": "approve"})
            == approved
        )
        assert (
            len(
                [r for r in store.get_board("r2")["lessons"] if r["id"] == lesson["id"]]
            )
            == 1
        )
    finally:
        store.close()


def test_no_answer_call_cannot_confirm_receipt(store):
    store.claim_request("r1", "request", claim())
    store.report_delivery(
        "r1", "request", {"organization_id": "org", "idempotency_key": "delivery"}
    )
    for status, key in (
        ("queued", "call-queued"),
        ("active", "call-active"),
        ("completed", "call-completed"),
    ):
        store.save_call(
            "r1",
            {
                "id": "no-answer-call",
                "request_id": "request",
                "status": status,
                "outcome": "no_answer" if status == "completed" else None,
                "evidence_ids": ["evidence"] if status == "completed" else [],
                "idempotency_key": key,
            },
        )
    with pytest.raises(InvalidInput):
        store.verify_request(
            "r1",
            "request",
            {
                "received": True,
                "source": "survivor_call",
                "evidence_ids": ["evidence"],
                "idempotency_key": "false-receipt",
            },
        )
    assert store.get_board("r1")["requests"][0]["status"] == "awaiting_verification"
