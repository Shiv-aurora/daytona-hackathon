"""Recovery receipt check. Injected transport and durable hooks; never dials on replay.

Context is server-owned: request, survivor, callback_number and claim_call,
get_call_result, finish_call, emit_event, escalate callbacks. claim_call must be an
atomic queued -> active compare-and-set. A crash leaves active calls for human
review rather than redialing. No LLM is needed for the demo's explicit answers.
"""
from __future__ import annotations

import re
import threading
from datetime import UTC, datetime

from calls.agent import Turn
from calls.safety import disclosure, emergency_line, safety_check
from calls.voice.bridge import sse_chunks
from eval.arize_trace import traced


def validate_context(job: dict, context: dict) -> None:
    request, survivor = context['request'], context['survivor']
    for key in ('run_id', 'disaster_id'):
        if not job.get(key) or any(record.get(key) != job[key] for record in (context, request, survivor)):
            raise ValueError(f'out-of-scope {key}')
    if request['id'] != job['request_id'] or survivor['id'] != request['survivor_id']:
        raise ValueError('request/survivor mismatch')
    if job.get('survivor_id', survivor['id']) != survivor['id']:
        raise ValueError('job/survivor mismatch')
    if not job.get('call_id'):
        raise ValueError('call_id required')


def explicit_receipt(text: str) -> bool | None:
    """Conservative, full-utterance allowlist: unknown/partial/conditional stays open."""
    answer = re.sub(r'[^\w\s\']', '', text.lower().replace('’', "'")).strip()
    if answer in {'yes', 'yes it arrived', 'yes i received it', 'i received it',
                  'i received all of it', 'yes everything arrived', 'it arrived'}:
        return True
    if answer in {'no', 'no it did not arrive', "no it didn't arrive", 'it never arrived',
                  "i didn't receive it", 'i did not receive it', 'nothing arrived'}:
        return False
    return None


class RecoverySession:
    """Same safety-first turn path for scripted, typed and ElevenLabs Custom LLM."""
    def __init__(self, job: dict, context: dict):
        validate_context(job, context)
        self.job, self.context = dict(job), context
        self.language = context['survivor'].get('language', 'en')
        self.disclosure = disclosure(self.language, context['callback_number'])
        self.question = ('Did you personally receive all the promised assistance for this request: '
                         f"{context['request']['description']}? Please say yes, no, or unsure.")
        self.result = None
        self._lock = threading.RLock()
        self._emergency_escalated = False
        self.turns = 0
        self.evidence: list[str] = []

    def event(self, action: str, details: dict | None = None) -> dict:
        event = {'id': f"{self.job['call_id']}:{action}",
                 'run_id': self.job['run_id'], 'disaster_id': self.job['disaster_id'],
                 'created_at': datetime.now(UTC).isoformat(), 'module': 'calls',
                 'action': action, 'subject_id': self.job['request_id'], 'details': details or {}}
        self.context['emit_event'](event)
        return event

    def finish(self, outcome: str, received=None, emergency=False) -> dict:
        with self._lock:
            return self._finish(outcome, received, emergency)

    def _finish(self, outcome: str, received=None, emergency=False) -> dict:
        if self.result is not None:
            return self.result
        summaries = {'verified_received': 'Survivor explicitly confirmed receipt of all promised assistance.',
                     'not_received': 'Survivor reported assistance did not arrive; human follow-up required.',
                     'unverified': 'Receipt remains unverified; human follow-up required.',
                     'no_answer': 'No survivor answer; receipt remains unverified.',
                     'failed': 'Call failed; receipt remains unverified.',
                     'refused_no_opt_in': 'No confirmed opt-in; call not started.',
                     'emergency_escalated': 'Emergency detected; immediate human escalation recorded.'}
        result = {key: self.job[key] for key in ('call_id', 'request_id', 'run_id', 'disaster_id')}
        result.update(outcome=outcome, received=received, summary=summaries[outcome],
                      evidence_ids=list(self.evidence), emergency=emergency)
        with traced('relay.follow_up.outcome', run_id=result['run_id'], disaster_id=result['disaster_id'],
                    request_id=result['request_id'], outcome=outcome, received=received,
                    emergency=emergency):
            self.event('follow_up_finished', {'outcome': outcome, 'received': received})
            self.context['finish_call'](self.job, result)
        self.result = result
        return result

    def hear(self, text: str) -> Turn:
        with self._lock:
            return self._hear(text)

    def _hear(self, text: str) -> Turn:
        if self.result:
            return Turn(emergency_line(self.language) if self.result['emergency'] else
                        'Thank you. A recovery coordinator will review the update.', end=True,
                        emergency=self.result['emergency'])
        self.turns += 1
        verdict = safety_check(text, self.language)
        evidence_id = f"{self.job['call_id']}:utterance:{self.turns}"
        self.evidence.append(evidence_id)
        if verdict['emergency']:
            self.escalate_emergency(text, evidence_id)
            self.finish('emergency_escalated', emergency=True)
            return Turn(emergency_line(self.language), end=True, emergency=True)
        received = explicit_receipt(text)
        self.event(f'utterance:{self.turns}', {'evidence_id': evidence_id, 'received': received})
        if received is not None:
            self.finish('verified_received' if received else 'not_received', received)
            return Turn('Thank you. Your update has been recorded for the recovery team.', end=True)
        self.finish('unverified')
        return Turn('Thank you. A person from the recovery team will follow up to clarify.', end=True)


    def escalate_emergency(self, text: str, evidence_id: str) -> bool:
        """Also supports late transcript recovery without changing receipt evidence."""
        with self._lock:
            verdict = safety_check(text, self.language)
            if not verdict['emergency']:
                return False
            if not self._emergency_escalated:
                # Durable hook MUST complete before speech/model/result storage.
                self.context['escalate']({
                    'id': f"{self.job['call_id']}:human-escalation", 'run_id': self.job['run_id'],
                    'disaster_id': self.job['disaster_id'], 'request_id': self.job['request_id'],
                    'call_id': self.job['call_id'], 'evidence_ids': [evidence_id],
                    'reason': verdict['reason'], 'action': 'human_escalation'})
                self.event('human_escalation', {'evidence_ids': [evidence_id]})
                self._emergency_escalated = True
            return True


def open_follow_up(job: dict, context: dict) -> RecoverySession | dict:
    session = RecoverySession(job, context)
    previous = context['get_call_result'](job['call_id'])
    if previous is not None:
        for key in ('call_id', 'request_id', 'run_id', 'disaster_id'):
            if previous[key] != job[key]:
                raise ValueError('stored result scope mismatch')
        return previous
    if not context['claim_call'](job):
        raise ValueError('call is not queued, or attempt remains active; do not redial')
    if context['survivor'].get('call_opt_in') is not True:
        return session.finish('refused_no_opt_in')
    session.event('follow_up_started')
    return session


def run_follow_up(job: dict, context: dict, transport) -> dict:
    session = open_follow_up(job, context)
    if isinstance(session, dict):
        return session
    try:
        if not transport.dial(context['survivor']['id']):
            return session.finish('no_answer')
        transport.say(session.disclosure)
        transport.say(session.question)
        text = transport.listen()
        if text is None or not text.strip():
            return session.finish('no_answer')
        # Fail closed on escalation/storage errors. Never hide failed durable escalation.
        turn = session.hear(text)
        transport.say(turn.text)
        return session.result
    finally:
        transport.hang_up()


class RecoveryVoiceBridge:
    """Authenticated adapter for existing /v1/chat/completions route and typed fallback.

    Use open_follow_up first; server maps random session IDs to these session objects.
    No single-session fallback or client-supplied run/job identifiers are accepted.
    """
    def __init__(self, secret: str):
        if not secret:
            raise ValueError('Custom LLM bearer secret required')
        self.secret = secret
        self.sessions: dict[str, RecoverySession] = {}

    def chat_completion(self, body: dict, authorization: str):
        import hmac

        from calls.voice.bridge import SESSION_KEY, last_user_text

        if not hmac.compare_digest(authorization or '', f'Bearer {self.secret}'):
            return 401, {'error': 'unauthorized'}
        key = (body.get('elevenlabs_extra_body') or {}).get(SESSION_KEY)
        session = self.sessions.get(key)
        if session is None:
            return 404, {'error': 'unknown recovery session'}
        messages = body.get('messages') or []
        if not messages or messages[-1].get('role') != 'user':
            return 200, sse_chunks(Turn(session.question))
        return 200, sse_chunks(session.hear(last_user_text(messages)))
