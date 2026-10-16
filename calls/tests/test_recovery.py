import hashlib
import hmac
import json

import pytest

from calls.fakes import FakeTransport
from calls.recovery import (
    RecoveryVoiceBridge,
    explicit_receipt,
    open_follow_up,
    run_follow_up,
)
from calls.safety import disclosure, emergency_line
from calls.webhooks import handle_post_call, verify_webhook


@pytest.fixture
def state():
    job = {'call_id': 'call-1', 'request_id': 'req-1', 'run_id': 'run-a', 'disaster_id': 'flood-a'}
    results, claims, events, escalations = {}, [], [], []

    def claim(job):
        if job['call_id'] in claims:
            return False
        claims.append(job['call_id'])
        return True

    context = {'run_id': 'run-a', 'disaster_id': 'flood-a',
                   'request': {'id': 'req-1', 'survivor_id': 'survivor-1', 'description': 'food delivery',
                                'run_id': 'run-a', 'disaster_id': 'flood-a'},
                   'survivor': {'id': 'survivor-1', 'call_opt_in': True, 'language': 'en',
                                 'run_id': 'run-a', 'disaster_id': 'flood-a'},
                   'callback_number': '+12125550123', 'claim_call': claim,
                   'get_call_result': results.get,
                   'finish_call': lambda job, result: results.setdefault(job['call_id'], result),
                   'emit_event': events.append, 'escalate': escalations.append}
    return job, context, results, events, escalations


@pytest.mark.parametrize(('answer', 'received', 'outcome'), [
    ('yes', True, 'verified_received'), ('no', False, 'not_received'),
    ('only half arrived', None, 'unverified'), ('I think so', None, 'unverified'),
    ('yes but not everything arrived', None, 'unverified'),
    ('tell me how to treat an injury', None, 'unverified'),
])
def test_receipt_and_replay(state, answer, received, outcome):
    job, context, results, events, _ = state
    transport = FakeTransport([answer])
    result = run_follow_up(job, context, transport)
    assert result['received'] is received
    assert result['outcome'] == outcome
    assert set(result) == {'call_id', 'request_id', 'run_id', 'disaster_id', 'outcome',
                           'received', 'summary', 'evidence_ids', 'emergency'}
    assert result['evidence_ids'] == ['call-1:utterance:1']
    assert transport.said[0] == disclosure('en', context['callback_number'])
    assert 'food delivery' in transport.said[1]
    assert transport.hung_up
    assert results['call-1'] == result
    count = len(events)
    assert run_follow_up(job, context, transport) == result
    assert transport.dialed == ['survivor-1']
    assert len(events) == count
    assert all(e['run_id'] == 'run-a' and e['disaster_id'] == 'flood-a' for e in events)


@pytest.mark.parametrize('answers', [True, False])
def test_no_answer(state, answers):
    job, context, *_ = state
    result = run_follow_up(job, context, FakeTransport([], answers=answers))
    assert result['outcome'] == 'no_answer' and result['received'] is None


def test_no_consent(state):
    job, context, *_ = state
    context['survivor']['call_opt_in'] = False
    transport = FakeTransport(['yes'])
    assert run_follow_up(job, context, transport)['outcome'] == 'refused_no_opt_in'
    assert transport.dialed == []


@pytest.mark.parametrize('record', ['request', 'survivor'])
@pytest.mark.parametrize('key', ['run_id', 'disaster_id'])
def test_scope_before_call(state, record, key):
    job, context, *_ = state
    context[record][key] = 'other'
    transport = FakeTransport(['yes'])
    with pytest.raises(ValueError, match='out-of-scope'):
        run_follow_up(job, context, transport)
    assert transport.dialed == []


def test_emergency_first_and_fail_closed(state):
    job, context, _results, events, escalations = state
    transport = FakeTransport(["yes, but I can't breathe"])
    result = run_follow_up(job, context, transport)
    assert result['emergency'] and result['received'] is None
    assert escalations[0]['request_id'] == 'req-1'
    assert transport.said[-1] == emergency_line('en')
    assert events[1]['action'] == 'human_escalation'


def test_failed_durable_escalation_never_finishes_or_redials(state):
    job, context, results, *_ = state

    def fail(event):
        raise RuntimeError('storage unavailable')

    context['escalate'] = fail
    transport = FakeTransport(['chest pain'])
    with pytest.raises(RuntimeError):
        run_follow_up(job, context, transport)
    assert not results and transport.hung_up
    with pytest.raises(ValueError, match='do not redial'):
        run_follow_up(job, context, transport)
    assert len(transport.dialed) == 1


def sign(event, timestamp=1000):
    body = json.dumps(event).encode()
    digest = hmac.new(b'secret', str(timestamp).encode() + b'.' + body, hashlib.sha256).hexdigest()
    return body, f't={timestamp},v0={digest}'


@pytest.mark.parametrize('now', [1000, 2000])
def test_signature(now):
    body, signature = sign({'type': 'post_call_transcription'})
    assert verify_webhook(body, signature, 'secret', now=now)['type'] == 'post_call_transcription'
    with pytest.raises(ValueError):
        verify_webhook(body + b' ', signature, 'secret', now=now)


@pytest.mark.parametrize('now', [-1000, 3000])
def test_stale_or_future_signature(now):
    body, signature = sign({})
    with pytest.raises(ValueError, match='timestamp'):
        verify_webhook(body, signature, 'secret', now=now)


def test_webhook_completion_is_not_receipt_and_dedupes(state):
    job, context, _, events, _ = state
    session = open_follow_up(job, context)
    event = {'type': 'post_call_transcription', 'data': {'conversation_id': 'provider-1',
             'analysis': {'call_successful': 'success'}, 'dynamic_variables': {'request_id': 'other'},
             'transcript': [{'role': 'user', 'message': 'yes'}]}}
    body, signature = sign(event)
    lookup = lambda key: session if key == 'provider-1' else None
    result = handle_post_call(body, signature, 'secret', lookup, now=1000)
    assert result['received'] is None and result['request_id'] == 'req-1'
    count = len(events)
    assert handle_post_call(body, signature, 'secret', lookup, now=1000) == result
    assert len(events) == count
    with pytest.raises(LookupError):
        handle_post_call(body, signature, 'secret', lambda key: None, now=1000)


def test_browser_bridge_auth_and_safety(state):
    job, context, _, _, escalations = state
    bridge = RecoveryVoiceBridge('bridge-secret')
    bridge.sessions['opaque-server-id'] = open_follow_up(job, context)
    body = {'elevenlabs_extra_body': {'relay_session_id': 'opaque-server-id'},
            'messages': [{'role': 'user', 'content': "can't breathe"}]}
    assert bridge.chat_completion(body, '')[0] == 401
    status, chunks = bridge.chat_completion(body, 'Bearer bridge-secret')
    assert status == 200 and 'end_call' in ''.join(chunks)
    assert escalations


def test_conditional_and_negated_receipt():
    assert explicit_receipt('yes if it arrives tomorrow') is None
    assert explicit_receipt('not yes') is None
    assert explicit_receipt('it arrived at the wrong address') is None


def test_recovered_emergency_after_receipt_is_durable_and_idempotent(state):
    job, context, _, events, escalations = state
    session = open_follow_up(job, context)
    session.hear('yes')
    original = dict(session.result)
    body, signature = sign({'type': 'post_call_transcription', 'data': {
        'conversation_id': 'provider-1', 'transcript': [
            {'role': 'agent', 'message': 'chest pain'},
            {'role': 'user', 'message': "I can't breathe"}]}})
    result = handle_post_call(body, signature, 'secret', lambda key: session, now=1000)
    assert result == original and result['received'] is True
    assert len(escalations) == 1
    assert escalations[0]['run_id'] == 'run-a'
    assert escalations[0]['disaster_id'] == 'flood-a'
    count = len(events)
    handle_post_call(body, signature, 'secret', lambda key: session, now=1000)
    assert len(escalations) == 1 and len(events) == count


def test_recovered_emergency_failure_propagates_even_after_receipt(state):
    job, context, *_ = state
    session = open_follow_up(job, context)
    session.hear('yes')

    def fail(event):
        raise RuntimeError('durable escalation failed')

    context['escalate'] = fail
    body, signature = sign({'type': 'post_call_transcription', 'data': {
        'conversation_id': 'provider-1', 'transcript': [
            {'role': 'user', 'message': 'chest pain'}]}})
    with pytest.raises(RuntimeError, match='durable escalation'):
        handle_post_call(body, signature, 'secret', lambda key: session, now=1000)
