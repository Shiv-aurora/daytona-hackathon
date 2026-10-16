"""Store selection, remote sign-in/reconnect, status and live-checker behavior. No network."""

import socket
from pathlib import Path
from typing import ClassVar

import pytest
import surrealdb

from contracts.demo import InvalidInput
from db import remote
from db.recovery import SurrealRecoveryStore
from scripts.check_surreal import run as run_check

SCHEMA = (Path(__file__).parents[1] / "recovery_schema.surql").read_text()


class FakeSurreal:
    instances: ClassVar[list] = []
    reject_signins = 2
    drop_once = False

    def __init__(self, url):
        self.url, self.calls, self.signins = url, [], []
        FakeSurreal.instances.append(self)

    def connect(self):
        self.calls.append("connect")

    def signin(self, creds):
        self.signins.append(sorted(creds))
        if len(self.signins) <= FakeSurreal.reject_signins:
            raise RuntimeError("bad password hunter2")

    def use(self, ns, db):
        self.calls.append(("use", ns, db))

    def query(self, sql, params=None):
        if FakeSurreal.drop_once and "SELECT" in sql:
            FakeSurreal.drop_once = False
            raise ConnectionError("dropped")
        self.calls.append(sql)
        return []

    def close(self):
        self.calls.append("close")


@pytest.fixture
def fake(monkeypatch):
    FakeSurreal.instances, FakeSurreal.reject_signins, FakeSurreal.drop_once = [], 2, False
    monkeypatch.setattr(surrealdb, "Surreal", FakeSurreal)
    return FakeSurreal


ENV = {"SURREAL_URL": "wss://x.example.test", "SURREAL_NAMESPACE": "n", "SURREAL_DATABASE": "d",
       "SURREAL_USERNAME": "u", "SURREAL_PASSWORD": "hunter2"}


def test_mode_selection():
    assert remote.mode_for("") == "embedded"
    assert remote.mode_for("surrealkv://.x") == "embedded"
    assert remote.mode_for("mem://") == "embedded"
    assert remote.mode_for("wss://a.surreal.cloud") == "remote"


def test_remote_factory_signs_in_by_scope_and_applies_schema(fake):
    store = SurrealRecoveryStore.from_env(env=ENV, dotenv=None)
    db = fake.instances[0]
    assert db.url == "wss://x.example.test"
    assert [len(s) for s in db.signins] == [2, 3, 4]  # root, namespace, database scope
    assert ("use", "n", "d") in db.calls and SCHEMA in db.calls
    assert store._file_lock is None


def test_remote_signin_failure_is_secret_free(fake):
    fake.reject_signins = 9
    with pytest.raises(remote.RemoteError) as err:
        SurrealRecoveryStore.from_env(env=ENV, dotenv=None)
    assert "hunter2" not in str(err.value)


def test_remote_hosts_still_rejected_without_flag(fake):
    with pytest.raises(InvalidInput):
        SurrealRecoveryStore("wss://x.example.test")
    with pytest.raises(InvalidInput):
        SurrealRecoveryStore("ws://old-service.example/rpc")


def test_dropped_remote_connection_reconnects_once(fake):
    fake.reject_signins = 0
    store = SurrealRecoveryStore.from_env(env=ENV, dotenv=None)
    fake.drop_once = True
    assert store._q("SELECT 1;") == []
    assert len(fake.instances) == 2 and "close" in fake.instances[0].calls


def test_blank_url_selects_embedded_store(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    store = SurrealRecoveryStore.from_env(env={"SURREAL_URL": ""}, dotenv=None)
    try:
        assert store._remote is False and store._file_lock is not None
        assert (tmp_path / ".relay-demo.relay-lock").exists()
    finally:
        store.close()


def test_schema_is_idempotent_on_embedded():
    store = SurrealRecoveryStore("mem://")
    store._q(SCHEMA)
    store._q(SCHEMA)
    store.seed({"runs": [{"run_id": "r", "disaster_id": "d"}], "disasters": [{"id": "d"}],
                "organizations": []})
    store._q(SCHEMA)
    assert store.list_disasters() == [{"id": "d"}]
    store.close()


def test_surreal_status(monkeypatch):
    assert remote.surreal_status({}, dotenv=None) == {"configured": False, "mode": "embedded", "reachable": None}
    assert remote.surreal_status({"SURREAL_URL": "mem://"}, dotenv=None)["reachable"] is None
    remote._PROBE["key"] = None

    def refuse(*_a, **_k):
        raise OSError("no route")

    monkeypatch.setattr(socket, "create_connection", refuse)
    status = remote.surreal_status(ENV, dotenv=None)
    assert status == {"configured": True, "mode": "remote", "reachable": False}


def test_checker_passes_on_embedded():
    lines = []
    assert run_check({"SURREAL_URL": "mem://"}, dotenv=None, out=lines.append) == 0
    assert lines[-1] == "RESULT: PASS" and not any(x.startswith("FAIL") for x in lines)


def test_checker_failures_hide_secrets(fake):
    lines = []
    fake.reject_signins = 9
    assert run_check(ENV, dotenv=None, out=lines.append) == 1
    assert lines[-1] == "RESULT: FAIL" and "hunter2" not in "\n".join(lines)
    assert run_check({"SURREAL_URL": "wss://x.test"}, dotenv=None, out=lines.append) == 1
