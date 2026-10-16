"""Signed post-call payload fixtures through the webhook route. Fakes only; no network."""
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from api import voice_routes
from api.demo_store import InMemoryRecoveryStore
from api.recovery import handle
from api.tests.test_voice_routes import (
    RUN,
    SECRET,
    SEED,
    FakeClient,
    make_store,
    request_state,
    start,
)

FIX = Path(__file__).parent / 'fixtures'


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('RELAY_CALLBACK_NUMBER', '+1 555 010 0199')
    monkeypatch.setenv('RELAY_LLM_SECRET', 'llm-secret')
    monkeypatch.setattr(voice_routes, 'make_client', lambda: FakeClient('CONV'))


def signed(name, conv=None, secret=SECRET):
    event = json.loads((FIX / name).read_text())
    if conv:
        event['data']['conversation_id'] = conv
    raw = json.dumps(event).encode()
    stamp = str(int(time.time()))
    sig = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    return raw, {'ElevenLabs-Signature': f't={stamp},v0={sig}'}


def post(store, name, conv=None, secret=SECRET):
    raw, headers = signed(name, conv, secret)
    return handle(store, 'POST', '/webhooks/elevenlabs', {}, raw, headers)


@pytest.mark.parametrize('name,received', [('webhook_received.json', True), ('webhook_not_received.json', False)])
def test_linked_session_outcomes(name, received):
    store, rid = make_store()
    start(store, rid)
    code, body = post(store, name, 'CONV')
    assert code == 200 and body['received'] is received
    assert request_state(store, rid)[0]['status'] != 'awaiting_verification'


def test_linked_emergency_escalates():
    store, rid = make_store()
    start(store, rid)
    code, body = post(store, 'webhook_emergency.json', 'CONV')
    assert code == 200 and body['emergency'] is True and body['received'] is None
    assert any(e['action'] == 'human_escalation' for e in store.get_board(RUN)['system_events'])


@pytest.mark.parametrize('name', ['webhook_received.json', 'webhook_not_received.json', 'webhook_emergency.json'])
def test_widget_conversation_is_unlinked_and_changes_nothing(name):
    store, rid = make_store()
    start(store, rid)  # a real session exists, but the widget conversation id is not bound to it
    before = json.dumps(store.get_board(RUN), sort_keys=True)
    code, body = post(store, name)
    assert code == 202 and body['unlinked'] is True and body['request_changed'] is False
    assert json.dumps(store.get_board(RUN), sort_keys=True) == before
    listed = handle(store, 'GET', '/webhooks/elevenlabs/unlinked')[1]['unlinked']
    assert len(listed) == 1 and listed[0]['emergency'] is (name == 'webhook_emergency.json')


def test_unlinked_dynamic_variables_never_pick_a_request():
    store = InMemoryRecoveryStore(SEED)
    assert post(store, 'webhook_received.json')[0] == 202


def test_bad_signature_rejected_before_recording():
    store, _ = make_store()
    assert post(store, 'webhook_received.json', secret='wrong')[0] == 401
    assert handle(store, 'GET', '/webhooks/elevenlabs/unlinked')[1]['unlinked'] == []
