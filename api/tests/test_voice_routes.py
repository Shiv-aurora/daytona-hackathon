"""ElevenLabs live routes against fakes only: no network, no real call, no real key."""
import base64
import hashlib
import hmac
import json
import time
from pathlib import Path

import pytest

from api import voice_routes
from api.demo_store import InMemoryRecoveryStore
from api.recovery import handle
from calls.elevenlabs import (
    ElevenLabsClient,
    ElevenLabsError,
    elevenlabs_status,
    segments_from_words,
)

SEED = json.loads((Path(__file__).resolve().parents[2] / 'data/demo/seed.json').read_text())
RUN, SECRET = 'demo-current', 'whsec-test'


class FakeClient:
    def __init__(self, conversation_id='conv-1'):
        self.conversation_id = conversation_id

    def signed_url(self):
        return {'signed_url': 'wss://example.invalid/signed', 'conversation_id': self.conversation_id}

    def transcribe(self, audio, filename, mime):
        return {'provider': 'elevenlabs', 'text': 'we need food', 'language': 'en',
                'segments': [{'speaker': 'speaker_0', 'start': 0.0, 'end': 1.0, 'text': 'we need food'}]}


@pytest.fixture
def env(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_WEBHOOK_SECRET', SECRET)
    monkeypatch.setenv('RELAY_CALLBACK_NUMBER', '+1 555 010 0199')
    monkeypatch.setenv('RELAY_LLM_SECRET', 'llm-secret')
    monkeypatch.setattr(voice_routes, 'make_client', lambda: FakeClient())


def make_store(survivor='current-survivor-1', category='food'):
    store = InMemoryRecoveryStore(SEED)
    row = store.create_request(RUN, {'survivor_id': survivor, 'category': category,
        'description': 'Food delivery', 'source_report_id': 'r', 'idempotency_key': 'c-' + survivor})
    store.claim_request(RUN, row['id'], {'organization_id': 'demo-food', 'promised_at': '2026-10-17T12:00:00Z',
                                          'idempotency_key': 'cl-' + survivor})
    store.report_delivery(RUN, row['id'], {'organization_id': 'demo-food', 'idempotency_key': 'd-' + survivor})
    return store, row['id']


def start(store, rid, key='k1', run=RUN):
    return handle(store, 'POST', f'/runs/{run}/requests/{rid}/voice-session', {'idempotency_key': key})


def post_event(store, conv, turns, kind='post_call_transcription', secret=SECRET, ts=None, extra=None):
    raw = json.dumps({'type': kind, 'data': {'conversation_id': conv, 'transcript':
        [{'role': r, 'message': m} for r, m in turns], **(extra or {})}}).encode()
    stamp = str(int(ts if ts is not None else time.time()))
    sig = hmac.new(secret.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
    return handle(store, 'POST', '/webhooks/elevenlabs', {}, raw, {'ElevenLabs-Signature': f't={stamp},v0={sig}'}), raw


def mine(rows, rid, key='request_id'):
    return [r for r in rows if r.get(key) == rid]


def escalations(store, rid):
    return [e for e in store.get_board(RUN)['system_events']
            if e['action'] == 'human_escalation' and e['subject_id'] == rid]


def request_state(store, rid):
    board = store.get_board(RUN)
    return next(r for r in board['requests'] if r['id'] == rid), board


def test_session_is_opaque_and_secret_free(env):
    store, rid = make_store()
    status, body = start(store, rid)
    assert status == 200 and body['provider'] == 'elevenlabs' and body['signed_url']
    assert body['session_id'] not in (rid, body['call_id']) and 'api_key' not in json.dumps(body).lower()
    assert request_state(store, rid)[0]['status'] == 'awaiting_verification'


def test_session_idempotent_and_key_bound_to_request(env):
    store, rid = make_store()
    first = start(store, rid)[1]
    assert start(store, rid)[1]['session_id'] == first['session_id']
    assert len(mine(store.get_board(RUN)['calls'], rid)) == 1
    assert start(store, 'another-request', key='k1')[0] == 409


def test_opt_in_refusal_and_state_guard(env):
    store, rid = make_store('current-survivor-3')
    assert start(store, rid)[0] == 409 and mine(store.get_board(RUN)['calls'], rid) == []
    open_store = InMemoryRecoveryStore(SEED)
    row = open_store.create_request(RUN, {'survivor_id': 'current-survivor-1', 'category': 'food',
        'description': 'x', 'source_report_id': 'r', 'idempotency_key': 'z'})
    assert start(open_store, row['id'])[0] == 409  # not awaiting verification


def test_unknown_run_is_isolated(env):
    store, rid = make_store()
    assert start(store, rid, run='demo-history')[0] == 404


@pytest.mark.parametrize('bad', ['', 'v0=abc', 't=1,v0=00'])
def test_webhook_rejects_bad_signature(env, bad):
    store, rid = make_store()
    start(store, rid)
    raw = b'{"type":"post_call_transcription","data":{"conversation_id":"conv-1"}}'
    assert handle(store, 'POST', '/webhooks/elevenlabs', {}, raw, {'ElevenLabs-Signature': bad})[0] == 401


def test_webhook_rejects_wrong_secret_stale_and_tampered(env):
    store, rid = make_store()
    start(store, rid)
    assert post_event(store, 'conv-1', [('user', 'yes')], secret='other')[0][0] == 401
    assert post_event(store, 'conv-1', [('user', 'yes')], ts=time.time() - 7200)[0][0] == 401
    raw = b'{"type":"post_call_transcription","data":{"conversation_id":"conv-1"}}'
    bad = {'ElevenLabs-Signature': f't={int(time.time())},v0={"a" * 64}'}
    assert handle(store, 'POST', '/webhooks/elevenlabs', {}, raw + b' ', bad)[0] == 401
    assert request_state(store, rid)[0]['status'] == 'awaiting_verification'


def test_webhook_requires_configured_secret(monkeypatch):
    store, _ = make_store()
    monkeypatch.delenv('ELEVENLABS_WEBHOOK_SECRET', raising=False)
    assert handle(store, 'POST', '/webhooks/elevenlabs', {}, b'{}', {})[0] == 503


def test_unknown_conversation_fails_closed(env):
    store, rid = make_store()
    start(store, rid)
    (status, _), _ = post_event(store, 'someone-elses', [('user', 'yes')])
    assert status == 404 and request_state(store, rid)[0]['status'] == 'awaiting_verification'


def test_received_outcome_verifies_with_evidence_and_replays(env):
    store, rid = make_store()
    start(store, rid)
    (status, out), _ = post_event(store, 'conv-1', [('agent', 'Did it arrive?'), ('user', 'Yes, it arrived.')])
    assert status == 200 and out['outcome'] == 'verified_received' and out['evidence_ids']
    request, board = request_state(store, rid)
    assert request['status'] == 'resolved' and len(mine(board['verifications'], rid)) == 1
    verification = mine(board['verifications'], rid)[0]
    assert verification['source'] == 'survivor_call' and verification['evidence_ids'] == out['evidence_ids']
    assert board['system_events'] and all(
        e['run_id'] == RUN and e['disaster_id'] == 'demo-storm-2026' for e in board['system_events'])
    (again, out2), _ = post_event(store, 'conv-1', [('user', 'Yes, it arrived.')])
    assert again == 200 and out2['outcome'] == 'verified_received'
    assert len(mine(store.get_board(RUN)['verifications'], rid)) == 1


@pytest.mark.parametrize('turns,outcome,status', [
    ([('user', 'No, it did not arrive')], 'not_received', 'reopened'),
    ([('user', 'maybe tomorrow')], 'unverified', 'awaiting_verification'),
    ([('user', 'yes'), ('user', 'no')], 'unverified', 'awaiting_verification'),
    ([('agent', 'Hello?')], 'no_answer', 'awaiting_verification')])
def test_outcome_mapping(env, turns, outcome, status):
    store, rid = make_store()
    start(store, rid)
    (code, out), _ = post_event(store, 'conv-1', turns)
    assert code == 200 and out['outcome'] == outcome and request_state(store, rid)[0]['status'] == status


@pytest.mark.parametrize('reason,outcome', [('no-answer', 'no_answer'), ('unknown', 'failed')])
def test_failure_event_mapping(env, reason, outcome):
    store, rid = make_store()
    start(store, rid)
    (_, out), _ = post_event(store, 'conv-1', [], kind='call_initiation_failure', extra={'failure_reason': reason})
    assert out['outcome'] == outcome and request_state(store, rid)[0]['status'] == 'awaiting_verification'


def test_emergency_overrides_any_answer(env):
    store, rid = make_store()
    start(store, rid)
    (status, out), _ = post_event(store, 'conv-1', [('user', 'yes it arrived'), ('user', "I can't breathe")])
    assert status == 200 and out['outcome'] == 'emergency_escalated' and out['emergency'] is True
    request, board = request_state(store, rid)
    assert request['status'] == 'awaiting_verification' and mine(board['verifications'], rid) == []
    assert escalations(store, rid)


def test_emergency_after_live_result_still_escalates(env):
    store, rid = make_store()
    session = start(store, rid)[1]
    status, _ = handle(store, 'POST', '/v1/chat/completions',
                       {'messages': [{'role': 'user', 'content': 'yes it arrived'}],
                        'elevenlabs_extra_body': {'relay_session_id': session['session_id']}},
                       None, {'Authorization': 'Bearer llm-secret'})
    assert status == 200 and request_state(store, rid)[0]['status'] == 'resolved'
    assert escalations(store, rid) == []
    turns = [('user', 'yes it arrived'), ('user', 'chest pain now')]
    post_event(store, 'conv-1', turns)
    count = len(escalations(store, rid))
    assert count >= 1
    post_event(store, 'conv-1', turns)
    assert len(escalations(store, rid)) == count


def test_custom_llm_requires_bearer_secret_and_session(env):
    store, rid = make_store()
    session = start(store, rid)[1]
    body = {'messages': [{'role': 'user', 'content': 'yes'}],
            'elevenlabs_extra_body': {'relay_session_id': session['session_id']}}
    assert handle(store, 'POST', '/v1/chat/completions', body, None, {'Authorization': 'Bearer no'})[0] == 401
    unknown = {**body, 'elevenlabs_extra_body': {'relay_session_id': 'x'}}
    assert handle(store, 'POST', '/v1/chat/completions', unknown, None, {'Authorization': 'Bearer llm-secret'})[0] == 404


def test_public_verify_stays_human_review(env):
    store, rid = make_store()
    start(store, rid)
    assert handle(store, 'POST', f'/runs/{RUN}/requests/{rid}/verify',
                  {'received': True, 'source': 'survivor_call', 'evidence_ids': ['x'],
                   'idempotency_key': 'v'})[0] == 400


def test_sessions_do_not_cross_stores(env):
    store_a, rid_a = make_store()
    store_b, rid_b = make_store()
    start(store_a, rid_a)
    (status, _), _ = post_event(store_b, 'conv-1', [('user', 'yes')])
    assert status == 404 and request_state(store_b, rid_b)[0]['status'] == 'awaiting_verification'


def test_stt_fake_when_no_key(monkeypatch):
    monkeypatch.setattr(voice_routes, 'make_client', lambda: None)
    store, _ = make_store()
    audio = base64.b64encode(b'RIFFfake').decode()
    status, out = handle(store, 'POST', f'/runs/{RUN}/intake/transcribe', {'audio_base64': audio})
    assert status == 200 and out['provider'] == 'fake' and out['live'] is False
    assert out['segments'][0].keys() >= {'speaker', 'start', 'end', 'text'}
    assert any(e['action'] == 'audio_transcribed' for e in store.get_board(RUN)['system_events'])


def test_stt_multipart_live_path_and_validation(env):
    store, _ = make_store()
    boundary = 'XBOUND'
    raw = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n'
           f'Content-Type: audio/wav\r\n\r\n').encode() + b'AUDIO' + f'\r\n--{boundary}--\r\n'.encode()
    status, out = handle(store, 'POST', f'/runs/{RUN}/intake/transcribe', {}, raw,
                         {'Content-Type': f'multipart/form-data; boundary={boundary}'})
    assert status == 200 and out['provider'] == 'elevenlabs' and out['text'] == 'we need food'
    assert handle(store, 'POST', f'/runs/{RUN}/intake/transcribe', {'audio_base64': '!!'})[0] == 400
    assert handle(store, 'POST', '/runs/nope/intake/transcribe', {'audio_base64': 'QQ=='})[0] == 404


def test_stt_emergency_transcript_escalates(monkeypatch):
    class Scary(FakeClient):
        def transcribe(self, *args):
            return {'provider': 'elevenlabs', 'text': 'I fell and cannot get up', 'segments': []}
    monkeypatch.setattr(voice_routes, 'make_client', lambda: Scary())
    store, _ = make_store()
    status, out = handle(store, 'POST', f'/runs/{RUN}/intake/transcribe', {'audio_base64': 'QQ=='})
    assert status == 200 and out['emergency'] is True
    assert any(e['action'] == 'human_escalation' for e in store.get_board(RUN)['system_events'])


def test_health_status_has_no_network_or_secrets(monkeypatch):
    monkeypatch.setenv('ELEVENLABS_API_KEY', 'sk-secret')
    monkeypatch.delenv('ELEVENLABS_AGENT_ID', raising=False)
    assert elevenlabs_status() == {'configured': True, 'agent_configured': False}
    status, body = handle(make_store()[0], 'GET', '/health')
    assert status == 200 and 'sk-secret' not in json.dumps(body)


def test_client_errors_are_secret_free_and_words_group_by_speaker():
    def transport(method, url, headers, body, timeout):
        return 401, b'{"detail":"bad key sk-secret"}'
    client = ElevenLabsClient('sk-secret', 'agent', transport)
    with pytest.raises(ElevenLabsError) as error:
        client.subscription()
    assert 'sk-secret' not in str(error.value) and error.value.status == 401
    words = [{'text': 'Hi', 'start': 0, 'end': 1, 'speaker_id': 's0'},
             {'text': ' ', 'type': 'spacing', 'speaker_id': 's0'},
             {'text': 'there', 'start': 1, 'end': 2, 'speaker_id': 's0'},
             {'text': 'No', 'start': 2, 'end': 3, 'speaker_id': 's1'}]
    assert segments_from_words(words) == [{'speaker': 's0', 'start': 0, 'end': 2, 'text': 'Hi there'},
                                          {'speaker': 's1', 'start': 2, 'end': 3, 'text': 'No'}]


def test_http_server_passes_exact_webhook_bytes_and_multipart(env):
    import threading
    from http.server import ThreadingHTTPServer
    from urllib.error import HTTPError
    from urllib.request import Request, urlopen

    from api.server import make_handler
    store, rid = make_store()
    server = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(None, recovery_store=store))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{server.server_port}'

    def send(path, data, headers):
        try:
            with urlopen(Request(base + path, data=data, headers=headers), timeout=10) as response:
                return response.status, response.read()
        except HTTPError as error:
            return error.code, error.read()
    try:
        start(store, rid)
        raw = json.dumps({'type': 'post_call_transcription', 'data': {'conversation_id': 'conv-1',
            'transcript': [{'role': 'user', 'message': 'yes it arrived'}]}}, indent=2).encode()
        stamp = str(int(time.time()))
        sig = hmac.new(SECRET.encode(), stamp.encode() + b'.' + raw, hashlib.sha256).hexdigest()
        header = {'ElevenLabs-Signature': f't={stamp},v0={sig}'}
        assert send('/webhooks/elevenlabs', raw + b' ', header)[0] == 401
        assert send('/webhooks/elevenlabs', raw, header)[0] == 200
        boundary = 'B'
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="a.wav"\r\n\r\n').encode() \
            + b'AUDIO' + f'\r\n--{boundary}--\r\n'.encode()
        status, payload = send(f'/runs/{RUN}/intake/transcribe', body,
                               {'Content-Type': f'multipart/form-data; boundary={boundary}'})
        assert status == 200 and json.loads(payload)['provider'] == 'elevenlabs'
    finally:
        server.shutdown()
        server.server_close()
