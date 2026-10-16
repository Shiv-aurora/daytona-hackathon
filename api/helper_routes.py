"""AI helper agents: small sandboxed jobs that only propose; humans and consent-checked paths decide.

POST /runs/{run}/helpers/spawn  {idempotency_key, role, request_id?, scripted_answer?}
GET  /runs/{run}/helpers
"""
import json
import os
from threading import RLock

from api.demo_store import now
from calls.safety import disclosure
from contracts.demo import Conflict, InvalidInput, NotFound
from helpers.daytona_client import default_client
from helpers.roles import BY_ROLE

TIMEOUT_SECONDS = 20
ANSWERS = ('received', 'not_received', 'unsure')
# Fictional demo number, used only if RELAY_CALLBACK_NUMBER is unset.
DEMO_CALLBACK = '+1 555 010 0199'
_SPAWN_LOCK = RLock()
_client = None


def set_client(client):
    """Tests inject a fake sandbox client; None restores env-based selection."""
    global _client
    _client = client


def get_client():
    return _client or default_client()


def build_payload(board, role, request_id, answer):
    """De-identified work payload: ids, categories, statuses, capabilities. No survivor fields."""
    spec = BY_ROLE[role]
    requests = [{k: r.get(k) for k in ('id', 'category', 'status', 'due_at', 'organization_id')}
                for r in board['requests']]
    payload = {'role': role, 'run_id': board['run_id'], 'disaster_id': board['disaster']['id']}
    if not spec['needs_request']:
        payload['requests'] = requests
        return payload
    request = next((r for r in requests if r['id'] == request_id), None)
    if request is None:
        raise NotFound('unknown request')
    payload['request'] = request
    if role == 'matcher':
        payload['organizations'] = [{'id': o['id'], 'capabilities': o['capabilities']}
                                    for o in board['organizations']]
    elif role == 'verifier':
        payload['verifications'] = [{'id': v['id'], 'received': v.get('received'), 'source': v.get('source')}
                                    for v in board['verifications'] if v.get('request_id') == request_id]
    else:  # follow_up
        full = next(r for r in board['requests'] if r['id'] == request_id)
        survivor = next((s for s in board['survivors'] if s['id'] == full['survivor_id']), {})
        payload['call_opt_in'] = survivor.get('call_opt_in') is True
        payload['scripted_answer'] = answer
        number = os.environ.get('RELAY_CALLBACK_NUMBER') or DEMO_CALLBACK
        payload['disclosure'] = disclosure(survivor.get('language') or 'en', number)
    return payload


def execute(role, payload):
    """Run in the sandbox; any failure becomes a recorded status, never an unhandled error."""
    client = get_client()
    started = now()
    out = {'status': 'failed', 'provider': client.provider, 'sandbox_id': None,
           'started_at': started, 'summary': '', 'transcript': None, 'proposals': []}
    try:
        result = client.run(role, payload, TIMEOUT_SECONDS)
        out['sandbox_id'] = result.get('sandbox_id')
        lines = (result.get('stdout') or '').strip().splitlines()
        if result.get('exit_code') != 0 or not lines:
            out['summary'] = 'Helper exited with an error.'
        else:
            parsed = json.loads(lines[-1])
            out.update(status='completed', summary=str(parsed.get('summary', ''))[:500],
                       transcript=parsed.get('transcript'), proposals=parsed.get('proposals') or [])
    except TimeoutError:
        out.update(status='timeout', summary='Helper timed out.')
    except Exception as exc:  # noqa: BLE001 - record the failure type only, never details
        out['summary'] = f'Helper failed: {type(exc).__name__}.'
    out['finished_at'] = now()
    return out


def spawn(store, run_id, body):
    key = body.get('idempotency_key')
    if not isinstance(key, str) or not key.strip():
        raise InvalidInput('idempotency_key is required')
    role = body.get('role')
    if role not in BY_ROLE:
        raise InvalidInput('role must be one of: ' + ', '.join(BY_ROLE))
    request_id = body.get('request_id')
    answer = body.get('scripted_answer', 'unsure')
    if answer not in ANSWERS:
        raise InvalidInput('scripted_answer must be one of: ' + ', '.join(ANSWERS))
    if BY_ROLE[role]['needs_request'] and not isinstance(request_id, str):
        raise InvalidInput('request_id is required for this role')
    with _SPAWN_LOCK:
        previous = next((h for h in store.list_helper_runs(run_id) if h.get('spawn_key') == key), None)
        if previous:
            if previous['role'] != role or previous.get('request_id') != request_id:
                raise Conflict('idempotency key was used for another helper')
            return {'helper_run': previous}
        board = store.get_board(run_id)
        payload = build_payload(board, role, request_id, answer)
        outcome = execute(role, payload)
        record = {'role': role, 'request_id': request_id, 'spawn_key': key, **outcome,
                  'idempotency_key': 'helper:' + key}
        return {'helper_run': store.save_helper_run(run_id, record)}


def handle_helpers(store, method, run_id, parts, body):
    if method == 'POST' and parts == ['spawn']:
        return 200, spawn(store, run_id, body or {})
    if method == 'GET' and parts == []:
        return 200, {'helpers': store.list_helper_runs(run_id)}
    raise NotFound('not found')
