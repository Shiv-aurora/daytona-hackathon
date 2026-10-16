"""ElevenLabs live routes: consent-checked voice sessions, signed post-call webhook, Scribe intake.

Everything is server-owned: the client only receives an opaque session id, and a provider
conversation id is bound to a session by the server (from the signed-URL response), never by the
browser or by webhook dynamic variables. A call or delivery never resolves a request; only an
explicit survivor answer or human verification does. Registered with one line in api.recovery.handle.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import os
import secrets
import threading
import weakref
from email import policy
from email.parser import BytesParser
from urllib.parse import unquote, urlsplit

from calls.elevenlabs import (
    ElevenLabsClient,
    ElevenLabsError,
    elevenlabs_status,
    fake_transcribe,
)
from calls.recovery import (
    RecoverySession,
    RecoveryVoiceBridge,
    explicit_receipt,
    open_follow_up,
)
from calls.safety import emergency_line, safety_check
from calls.webhooks import verify_webhook
from contracts.demo import Conflict, InvalidInput, NotFound

MAX_AUDIO_BYTES = 25 * 1024 * 1024
FAKE_CALLBACK = '+1 555-0100'  # only used with the offline fake provider, never for a live call
_SERVICES: weakref.WeakKeyDictionary = weakref.WeakKeyDictionary()
_SERVICES_LOCK = threading.Lock()


def make_client():
    """Injection point for tests; returns None when ELEVENLABS_API_KEY is blank."""
    return ElevenLabsClient.from_env()


class VoiceService:
    """In-process opaque-session registry (a restart drops live sessions; humans review those)."""
    def __init__(self, store):
        self.store, self.lock = store, threading.RLock()
        self.by_session: dict[str, dict] = {}
        self.by_conversation: dict[str, str] = {}
        self.by_key: dict[tuple, str] = {}
        self.bridge: RecoveryVoiceBridge | None = None
        self.bridge_secret = ''

    def custom_llm(self, secret: str) -> RecoveryVoiceBridge:
        if self.bridge is None or self.bridge_secret != secret:
            self.bridge, self.bridge_secret = RecoveryVoiceBridge(secret), secret
            self.bridge.sessions = {sid: e['session'] for sid, e in self.by_session.items()}
        return self.bridge


def service_for(store) -> VoiceService:
    with _SERVICES_LOCK:
        if store not in _SERVICES:
            _SERVICES[store] = VoiceService(store)
        return _SERVICES[store]


def _header(headers, name):
    if headers is None:
        return ''
    getter = getattr(headers, 'get', None)
    value = getter(name) if getter else None
    if value is None and isinstance(headers, dict):
        value = next((v for k, v in headers.items() if k.lower() == name.lower()), None)
    return value or ''


def route(store, method, path, body=None, raw=None, headers=None):
    """Return (status, payload) for a voice route, or None when the path is not ours."""
    try:
        return _route(store, method, path, body, raw, headers)
    except ProviderUnavailable as exc:
        return 503, {'error': str(exc)}


def _health(store):
    import os

    from db.remote import surreal_status
    from helpers.daytona_client import daytona_status

    eleven, daytona, surreal = elevenlabs_status(), daytona_status(), surreal_status()
    kind = 'surreal' if 'surreal' in type(store).__name__.lower() else 'memory'
    return {
        'ok': True,
        'store': kind,
        'live': {
            'elevenlabs': bool(eleven['configured'] and eleven['agent_configured']),
            'arize': bool((os.environ.get('ARIZE_API_KEY') or '').strip()),
            'surreal': bool(surreal['configured']),
            'daytona': bool(daytona['configured']),
        },
        'elevenlabs': eleven,
        'daytona': daytona,
        'surreal': surreal,
    }


def _route(store, method, path, body, raw, headers):
    parts = [unquote(p) for p in urlsplit(path).path.split('/') if p]
    if method == 'GET' and parts == ['health']:
        return 200, _health(store)
    if method != 'POST':
        return None
    if parts == ['webhooks', 'elevenlabs']:
        return webhook(store, raw, _header(headers, 'ElevenLabs-Signature'))
    if parts == ['v1', 'chat', 'completions']:
        return custom_llm(store, body or {}, _header(headers, 'Authorization'))
    if len(parts) == 5 and parts[0] == 'runs' and parts[2] == 'requests' and parts[4] == 'voice-session':
        return 200, start_session(store, parts[1], parts[3], body or {})
    if len(parts) == 4 and parts[0] == 'runs' and parts[2:] == ['intake', 'transcribe']:
        return 200, transcribe(store, parts[1], body or {}, raw, _header(headers, 'Content-Type'))
    return None


# ---- browser voice session -------------------------------------------------------------------

def _context(store, run_id, call, request, survivor, callback_number):
    call_id = call['id']

    def claim(_):
        if call['status'] != 'queued':
            return False
        store.save_call(run_id, {**call, 'status': 'active', 'idempotency_key': call_id + ':active'})
        return True

    def emit(event):
        store.emit_event(run_id, {**event, 'idempotency_key': event['id']})

    def escalate(event):
        store.emit_event(run_id, {'module': 'calls', 'action': 'human_escalation',
            'subject_id': request['id'], 'details': {'call_id': call_id,
            'evidence_ids': event['evidence_ids'], 'reason': event['reason']},
            'idempotency_key': call_id + ':immediate-escalation'})

    def finish(_, result):
        # Persist receipt evidence first; only an explicit answer ever verifies a request.
        store.save_call(run_id, {**call, 'status': 'completed', 'outcome': result['outcome'],
            'summary': result['summary'], 'evidence_ids': result['evidence_ids'],
            'recovery_result': result, 'idempotency_key': call_id + ':completed'})
        if result['received'] is not None:
            store.verify_request(run_id, request['id'], {'received': result['received'],
                'source': 'survivor_call', 'evidence_ids': result['evidence_ids'],
                'notes': result['summary'], 'idempotency_key': call_id + ':verification'})

    return {'run_id': run_id, 'disaster_id': request['disaster_id'], 'request': request,
            'survivor': survivor, 'callback_number': callback_number, 'claim_call': claim,
            'get_call_result': lambda _: call.get('recovery_result'), 'finish_call': finish,
            'emit_event': emit, 'escalate': escalate}


def start_session(store, run_id, request_id, body):
    from api.recovery import queue_follow_up, required
    key = required(body, 'idempotency_key')
    service = service_for(store)
    with service.lock:
        known = service.by_key.get((run_id, key))
        if known:
            entry = service.by_session[known]
            if entry['request_id'] != request_id:
                raise Conflict('idempotency key was used for another request')
            return dict(entry['public'])
        board = store.get_board(run_id)
        request = next((r for r in board['requests'] if r['id'] == request_id), None)
        if request is None:
            raise NotFound('unknown request')
        if request['status'] not in ('awaiting_verification', 'reopened'):
            raise Conflict('voice follow-up requires an unresolved delivery')
        survivor = store.get_survivor(run_id, request['survivor_id'])
        if survivor.get('call_opt_in') is not True:
            raise Conflict('confirmed survivor call opt-in is required')
        if any(c['request_id'] == request_id and c['status'] == 'active' and c.get('queue_key') != key
               for c in board['calls']):
            raise Conflict('a follow-up for this request is already active')
        client = make_client()
        callback = os.environ.get('RELAY_CALLBACK_NUMBER', '').strip() or (None if client else FAKE_CALLBACK)
        if not callback:
            raise ProviderUnavailable('RELAY_CALLBACK_NUMBER is not configured')
        call = queue_follow_up(store, run_id, request_id, {'idempotency_key': key})['call']
        if call['status'] != 'queued':
            raise Conflict('this follow-up was already started and its session is no longer available')
        provider = {'signed_url': None, 'conversation_id': None}
        if client:
            try:
                provider = client.signed_url()
            except ElevenLabsError as exc:
                raise ProviderUnavailable(str(exc)) from None
        job = {'call_id': call['id'], 'request_id': request_id, 'run_id': run_id,
               'disaster_id': board['disaster']['id']}
        session = open_follow_up(job, _context(store, run_id, call, request, survivor, callback))
        if isinstance(session, dict):
            raise Conflict('follow-up was refused: ' + session['outcome'])
        sid = secrets.token_urlsafe(24)
        public = {'session_id': sid, 'provider': 'elevenlabs' if client else 'fake',
                  'live': bool(client), 'run_id': run_id, 'disaster_id': job['disaster_id'],
                  'request_id': request_id, 'call_id': call['id'],
                  'signed_url': provider['signed_url'], 'conversation_id': provider['conversation_id'],
                  'custom_llm_extra_body': {'relay_session_id': sid},
                  'disclosure': session.disclosure, 'question': session.question}
        service.by_session[sid] = {'session': session, 'run_id': run_id, 'request_id': request_id,
                                   'public': public, 'conversation_id': provider['conversation_id']}
        service.by_key[(run_id, key)] = sid
        if provider['conversation_id']:
            service.by_conversation[provider['conversation_id']] = sid
        if service.bridge is not None:
            service.bridge.sessions[sid] = session
        return dict(public)


class ProviderUnavailable(Exception):
    """Provider or configuration problem; route() maps it to a secret-free HTTP 503."""


# ---- Custom LLM (safety-first turn path for the live agent) ----------------------------------

def custom_llm(store, body, authorization):
    secret = os.environ.get('RELAY_LLM_SECRET', '').strip()
    if not secret:
        return 503, {'error': 'RELAY_LLM_SECRET is not configured'}
    service = service_for(store)
    with service.lock:
        status, chunks = service.custom_llm(secret).chat_completion(body, authorization)
    return (status, {'_sse': ''.join(chunks)}) if status == 200 else (status, chunks)


# ---- signed post-call webhook ----------------------------------------------------------------

def webhook(store, raw, signature):
    secret = os.environ.get('ELEVENLABS_WEBHOOK_SECRET', '').strip()
    if not secret:
        return 503, {'error': 'ELEVENLABS_WEBHOOK_SECRET is not configured'}
    if not isinstance(raw, (bytes, bytearray)) or not raw:
        return 400, {'error': 'empty body'}
    try:
        event = verify_webhook(bytes(raw), signature, secret)
    except (ValueError, TypeError):
        return 401, {'error': 'invalid webhook signature'}
    kind = event.get('type')
    if kind not in ('post_call_transcription', 'call_initiation_failure'):
        return 200, {'ignored': kind}
    data = event.get('data') or {}
    conversation_id = data.get('conversation_id')
    service = service_for(store)
    with service.lock:
        sid = service.by_conversation.get(conversation_id) if isinstance(conversation_id, str) else None
        entry = service.by_session.get(sid) if sid else None
        if entry is None:
            return 404, {'error': 'unknown provider conversation'}  # fail closed
        result = apply_outcome(entry['session'], kind, data, conversation_id)
    return 200, {'call_id': result['call_id'], 'request_id': result['request_id'],
                 'run_id': result['run_id'], 'disaster_id': result['disaster_id'],
                 'outcome': result['outcome'], 'received': result['received'],
                 'emergency': result['emergency'], 'evidence_ids': result['evidence_ids']}


def apply_outcome(session: RecoverySession, kind: str, data: dict, conversation_id: str) -> dict:
    """Map a provider payload to the call/verification record. Emergency always wins."""
    turns = data.get('transcript') or []
    user_texts = [t.get('message') for t in turns
                  if isinstance(t, dict) and t.get('role') == 'user' and isinstance(t.get('message'), str)
                  and t['message'].strip()]
    # Emergency check first, before any other mapping, even after an earlier result.
    for text in user_texts:
        if safety_check(text, session.language)['emergency']:
            session.escalate_emergency(text, f"{session.job['call_id']}:recovered-emergency")
            if session.result is None:
                session.finish('emergency_escalated', emergency=True)
            break
    if session.result is None:
        if kind == 'call_initiation_failure':
            reason = str(data.get('failure_reason') or '').lower()
            session.finish('no_answer' if reason in ('busy', 'no-answer', 'no_answer') else 'failed')
        elif not user_texts:
            session.finish('no_answer')
        else:
            answers = {explicit_receipt(t) for t in user_texts} - {None}
            if len(answers) == 1:
                decisive = next(t for t in reversed(user_texts) if explicit_receipt(t) is not None)
                session.hear(decisive)
            else:  # unclear or contradictory answers never verify anything
                session.finish('unverified')
    if not getattr(session, 'webhook_logged', False):  # replays must not re-emit a different event body
        session.webhook_logged = True
        session.event('provider_webhook_processed', {'conversation_id': conversation_id, 'type': kind})
    return session.result


# ---- Scribe speech-to-text for intake --------------------------------------------------------

def _audio_from_request(body, raw, content_type):
    if content_type.lower().startswith('multipart/form-data'):
        message = BytesParser(policy=policy.HTTP).parsebytes(
            b'Content-Type: ' + content_type.encode() + b'\r\nMIME-Version: 1.0\r\n\r\n' + (raw or b''))
        for part in message.iter_parts():
            if part.get_param('name', header='content-disposition') == 'file':
                return part.get_payload(decode=True) or b'', part.get_filename() or 'audio', \
                    part.get_content_type()
        raise InvalidInput('multipart upload needs a "file" part')
    encoded = body.get('audio_base64')
    if not isinstance(encoded, str) or not encoded:
        raise InvalidInput('audio_base64 or a multipart "file" is required')
    try:
        data = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError):
        raise InvalidInput('audio_base64 is not valid base64') from None
    return data, str(body.get('filename') or 'audio'), str(body.get('content_type') or 'application/octet-stream')


def transcribe(store, run_id, body, raw, content_type):
    store.get_board(run_id)  # run scope check (NotFound -> 404)
    audio, filename, mime = _audio_from_request(body, raw, content_type or '')
    if not audio:
        raise InvalidInput('audio is empty')
    if len(audio) > MAX_AUDIO_BYTES:
        raise InvalidInput('audio exceeds 25 MB')
    client = make_client()
    try:
        result = client.transcribe(audio, filename, mime) if client else fake_transcribe(audio, filename)
    except ElevenLabsError as exc:
        raise ProviderUnavailable(str(exc)) from None
    verdict = safety_check(result['text'])
    digest = hashlib.sha256(audio).hexdigest()
    store.emit_event(run_id, {'module': 'intake', 'action': 'audio_transcribed', 'subject_id': digest[:16],
        'details': {'provider': result['provider'], 'bytes': len(audio), 'segments': len(result['segments']),
                    'emergency': bool(verdict['emergency'])}, 'idempotency_key': 'transcribe:' + digest})
    result = {**result, 'emergency': bool(verdict['emergency'])}
    if verdict['emergency']:
        store.emit_event(run_id, {'module': 'intake', 'action': 'human_escalation', 'subject_id': digest[:16],
            'details': {'reason': verdict.get('reason'), 'source': 'transcript'},
            'idempotency_key': 'transcribe:' + digest + ':escalation'})
        result['message'] = emergency_line('en')
    return result
