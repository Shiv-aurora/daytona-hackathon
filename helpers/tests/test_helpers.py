"""Helper agents: isolation, de-identified payloads, cleanup, replay, and no authority over requests."""
import json
from types import SimpleNamespace

import pytest

from api import helper_routes
from api.demo_store import InMemoryRecoveryStore
from api.recovery import handle
from contracts.demo import InvalidInput
from helpers.daytona_client import (
    DaytonaSandboxClient,
    LocalSandboxClient,
    assert_no_contact,
    daytona_status,
)
from helpers.roles import ROLES

SEED = {
    'disasters': [{'id': 'd1'}, {'id': 'd2'}],
    'organizations': [{'id': 'o1', 'capabilities': ['food']}, {'id': 'o2', 'capabilities': ['supplies']}],
    'runs': [{'run_id': 'r1', 'disaster_id': 'd1'}, {'run_id': 'r2', 'disaster_id': 'd2'}],
    'survivors': [{'id': 's1', 'run_id': 'r1', 'disaster_id': 'd1', 'call_opt_in': True, 'language': 'en',
                   'display_name': 'Ada Private', 'phone': '+15550001111', 'email': 'ada@example.com'},
                  {'id': 's2', 'run_id': 'r2', 'disaster_id': 'd2', 'call_opt_in': False}],
}


@pytest.fixture
def store():
    s = InMemoryRecoveryStore(SEED)
    s.create_request('r1', {'survivor_id': 's1', 'category': 'food', 'description': 'x',
                            'source_report_id': 'rep', 'idempotency_key': 'k1'})
    s.create_request('r2', {'survivor_id': 's2', 'category': 'food', 'description': 'x',
                            'source_report_id': 'rep', 'idempotency_key': 'k2'})
    return s


class Recorder:
    provider = 'local'

    def __init__(self):
        self.payloads = []
        self.inner = LocalSandboxClient()

    def run(self, role, payload, timeout):
        self.payloads.append(payload)
        return self.inner.run(role, payload, timeout)


@pytest.fixture
def client():
    rec = Recorder()
    helper_routes.set_client(rec)
    yield rec
    helper_routes.set_client(None)


def spawn(store, run, **body):
    return handle(store, 'POST', f'/runs/{run}/helpers/spawn', body)


def request_id(store, run):
    return store.get_board(run)['requests'][0]['id']


def test_every_role_runs_and_records(store, client):
    rid = request_id(store, 'r1')
    for i, spec in enumerate(ROLES):
        status, body = spawn(store, 'r1', idempotency_key=f'h{i}', role=spec['role'], request_id=rid)
        assert status == 200, body
        record = body['helper_run']
        assert record['status'] == 'completed' and record['provider'] == 'local'
        assert record['run_id'] == 'r1' and record['disaster_id'] == 'd1' and record['summary']
    events = store.get_board('r1')['system_events']
    assert len([e for e in events if e['action'] == 'helper_run_saved']) == len(ROLES)


def test_follow_up_transcript_has_fixed_disclosure_and_matcher_only_suggests(store, client):
    rid = request_id(store, 'r1')
    _, body = spawn(store, 'r1', idempotency_key='f', role='follow_up', request_id=rid, scripted_answer='received')
    transcript = body['helper_run']['transcript']
    assert transcript[0]['text'].startswith('This is an automated call from Relay')
    assert transcript[-1]['text'] == 'Yes, I received it.'
    _, body = spawn(store, 'r1', idempotency_key='m', role='matcher', request_id=rid)
    proposal = body['helper_run']['proposals'][0]
    assert proposal['organization_ids'] == ['o1'] and proposal['requires_human_confirmation'] is True


def test_no_opt_in_means_no_call(store, client):
    rid = request_id(store, 'r2')
    _, body = spawn(store, 'r2', idempotency_key='f', role='follow_up', request_id=rid)
    assert body['helper_run']['transcript'] is None and 'opt-in' in body['helper_run']['summary']


def test_payloads_have_no_contact_fields(store, client):
    rid = request_id(store, 'r1')
    for i, spec in enumerate(ROLES):
        spawn(store, 'r1', idempotency_key=f'h{i}', role=spec['role'], request_id=rid)
    assert client.payloads
    for payload in client.payloads:
        text = json.dumps(payload)
        for secret in ('Ada', 'ada@example.com', '5550001111', '"s1"', 'survivor_id', 'display_name'):
            assert secret not in text
        assert_no_contact(payload)


def test_contact_guard_rejects():
    for bad in ({'phone': 'x'}, {'a': {'email': 'x'}}, {'a': ['ada@example.com']}, {'a': 'call +1 555 010 0199'}):
        with pytest.raises(ValueError):
            assert_no_contact(bad)
    assert_no_contact({'when': '2026-10-17T10:00:00Z', 'id': '12345678-1234-1234-1234-123456789012'})


def test_isolation_across_runs(store, client):
    rid1, rid2 = request_id(store, 'r1'), request_id(store, 'r2')
    status, _ = spawn(store, 'r1', idempotency_key='x', role='verifier', request_id=rid2)
    assert status == 404
    spawn(store, 'r2', idempotency_key='y', role='triage')
    assert len(handle(store, 'GET', '/runs/r1/helpers')[1]['helpers']) == 0
    assert len(handle(store, 'GET', '/runs/r2/helpers')[1]['helpers']) == 1
    assert rid1 != rid2


def test_idempotent_replay_runs_once(store, client):
    first = spawn(store, 'r1', idempotency_key='same', role='triage')[1]
    second = spawn(store, 'r1', idempotency_key='same', role='triage')[1]
    assert first == second and len(client.payloads) == 1
    assert spawn(store, 'r1', idempotency_key='same', role='intake')[0] == 409


def test_helper_cannot_resolve_request(store, client):
    rid = request_id(store, 'r1')
    before = store.get_board('r1')['requests']
    for i, spec in enumerate(ROLES):
        spawn(store, 'r1', idempotency_key=f'h{i}', role=spec['role'], request_id=rid, scripted_answer='received')
    board = store.get_board('r1')
    assert board['requests'] == before and board['verifications'] == [] and board['calls'] == []


def test_bad_input(store, client):
    assert spawn(store, 'r1', idempotency_key='a', role='boss')[0] == 400
    assert spawn(store, 'r1', idempotency_key='a', role='matcher')[0] == 400
    assert spawn(store, 'r1', role='triage')[0] == 400
    assert spawn(store, 'r1', idempotency_key='a', role='triage', scripted_answer='x')[0] == 400


def test_runner_failure_and_timeout_are_recorded(store):
    class Boom:
        provider = 'local'

        def __init__(self, exc):
            self.exc = exc

        def run(self, *a):
            raise self.exc

    for exc, status in ((TimeoutError(), 'timeout'), (RuntimeError('secret detail'), 'failed')):
        helper_routes.set_client(Boom(exc))
        try:
            record = spawn(store, 'r1', idempotency_key=status, role='triage')[1]['helper_run']
        finally:
            helper_routes.set_client(None)
        assert record['status'] == status and 'secret' not in record['summary']


def test_local_client_timeout(monkeypatch):
    import helpers.scripts  # noqa: F401
    from helpers import roles
    monkeypatch.setattr('helpers.daytona_client.script_source', lambda role: 'import time\ntime.sleep(5)\n')
    with pytest.raises(Exception) as err:
        LocalSandboxClient().run('triage', {'requests': []}, 0.5)
    assert 'Timeout' in type(err.value).__name__
    assert roles.BY_ROLE


class FakeSandbox:
    def __init__(self, behavior):
        self.id = 'sbx-1'
        self.process = SimpleNamespace(code_run=behavior)


class FakeDaytona:
    def __init__(self, behavior):
        self.behavior, self.created, self.deleted = behavior, [], []

    def create(self, params=None, timeout=None):
        sandbox = FakeSandbox(self.behavior)
        self.created.append(sandbox)
        return sandbox

    def delete(self, sandbox):
        self.deleted.append(sandbox)


def test_daytona_client_deletes_sandbox_on_success_and_error():
    ok = FakeDaytona(lambda code, timeout=None: SimpleNamespace(result='{"summary": "s"}\n', exit_code=0))
    result = DaytonaSandboxClient(ok).run('triage', {'requests': []}, 5)
    assert result == {'stdout': '{"summary": "s"}\n', 'exit_code': 0, 'sandbox_id': 'sbx-1'}
    assert ok.deleted == ok.created and len(ok.created) == 1

    def explode(code, timeout=None):
        raise RuntimeError('boom')

    bad = FakeDaytona(explode)
    client = DaytonaSandboxClient(bad, max_concurrency=1)
    with pytest.raises(RuntimeError):
        client.run('triage', {'requests': []}, 5)
    assert bad.deleted == bad.created and len(bad.created) == 1
    with pytest.raises(RuntimeError):  # the concurrency slot was released
        client.run('triage', {'requests': []}, 5)


def test_daytona_client_refuses_contact_before_creating_sandbox():
    fake = FakeDaytona(lambda *a, **k: None)
    with pytest.raises(ValueError):
        DaytonaSandboxClient(fake).run('triage', {'requests': [], 'phone': '1'}, 5)
    assert fake.created == []


def test_daytona_status_has_no_network():
    assert daytona_status({}) == {'configured': False, 'provider': 'local'}
    assert daytona_status({'DAYTONA_API_KEY': 'k'}) == {'configured': True, 'provider': 'daytona'}


def test_helper_runs_persist_in_surreal(client):
    pytest.importorskip('surrealdb')
    from db.recovery import SurrealRecoveryStore
    surreal = SurrealRecoveryStore('mem://', seed=SEED)
    try:
        surreal.create_request('r1', {'survivor_id': 's1', 'category': 'food', 'description': 'x',
                                      'source_report_id': 'rep', 'idempotency_key': 'k1'})
        first = spawn(surreal, 'r1', idempotency_key='p', role='triage')[1]
        assert spawn(surreal, 'r1', idempotency_key='p', role='triage')[1] == first
        assert len(handle(surreal, 'GET', '/runs/r1/helpers')[1]['helpers']) == 1
        assert handle(surreal, 'GET', '/runs/r2/helpers')[1]['helpers'] == []
    finally:
        surreal.close()


def test_invalid_input_type():
    with pytest.raises(InvalidInput):
        helper_routes.spawn(InMemoryRecoveryStore(SEED), 'r1', {})
