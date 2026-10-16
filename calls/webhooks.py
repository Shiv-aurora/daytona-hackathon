"""ElevenLabs post-call authentication and server-side conversation mapping.

Provider completion is not survivor receipt. Receipt evidence comes from the live
RecoverySession question/turn path, not provider-generated analysis or summary.
See https://elevenlabs.io/docs/eleven-agents/workflows/post-call-webhooks and
https://github.com/elevenlabs/elevenlabs-python/blob/main/src/elevenlabs/webhooks_custom.py
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from calls.safety import safety_check


def verify_webhook(raw_body: bytes, signature: str, secret: str, *, now=None) -> dict:
    """Authenticate exact bytes and bound both stale and future timestamps to 30m."""
    if not secret:
        raise ValueError('webhook secret required')
    parts = [part.strip().partition('=') for part in (signature or '').split(',')]
    fields = {key: value for key, separator, value in parts if separator}
    try:
        timestamp = int(fields['t'])
        digest = fields['v0']
    except (KeyError, ValueError) as exc:
        raise ValueError('invalid webhook signature') from exc
    if abs((time.time() if now is None else now) - timestamp) > 1800:
        raise ValueError('webhook timestamp outside tolerance')
    expected = hmac.new(secret.encode(), fields['t'].encode() + b'.' + raw_body,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, digest):
        raise ValueError('invalid webhook signature')
    event = json.loads(raw_body)
    if not isinstance(event, dict):
        raise TypeError('invalid webhook event')
    return event


def handle_post_call(raw_body: bytes, signature: str, secret: str, lookup_session, *, now=None) -> dict:
    """lookup_session(conversation_id) returns a SERVER-bound RecoverySession.

    This is a defensive completion path, not a replacement for live emergency
    handling. Unknown conversations fail closed; dynamic_variables never choose a
    request or scope. finish_call and escalation hooks must insert once by ID.
    """
    event = verify_webhook(raw_body, signature, secret, now=now)
    if event.get('type') != 'post_call_transcription':
        raise ValueError('unsupported webhook type')
    data = event.get('data') or {}
    conversation_id = data.get('conversation_id')
    if not isinstance(conversation_id, str) or not conversation_id:
        raise ValueError('missing provider conversation_id')
    session = lookup_session(conversation_id)
    if session is None:
        raise LookupError('unknown provider conversation')
    # Still detect an emergency if the live stream was interrupted; never send
    # provider summaries through a model or treat analysis success as receipt.
    for turn in data.get('transcript') or []:
        text = turn.get('message') or ''
        if turn.get('role') == 'user' and safety_check(text, session.language)['emergency']:
            session.escalate_emergency(text, f"{session.job['call_id']}:recovered-emergency")
            if session.result is None:
                return session.finish('emergency_escalated', emergency=True)
    # A recovered emergency escalates independently of immutable prior receipt evidence.
    return session.result if session.result is not None else session.finish('unverified')
