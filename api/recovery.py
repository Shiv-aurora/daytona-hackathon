"""Small recovery HTTP boundary; all external services remain injected/optional."""
import json
import re
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from api import background_routes, voice_routes
from api.demo_store import timestamp
from api.helper_routes import handle_helpers
from calls.safety import emergency_line, safety_check
from contracts.demo import Conflict, InvalidInput, NotFound

# Explicit vocabulary rather than stemming: medical terms and unrelated words
# must not become needs merely because they share a substring or suffix.
NEEDS = {'food': ('food', 'meal', 'meals', 'groceries', 'water'),
         'supplies': ('supply', 'supplies', 'blanket', 'blankets', 'diaper', 'diapers', 'hygiene'),
         'transportation': ('transport', 'transportation', 'ride', 'rides', 'bus', 'buses'),
         'shelter': ('shelter', 'shelters', 'housing'),
         'repairs': ('repair', 'repairs', 'roof', 'roofs'),
         'medicine': ('medicine', 'medicines', 'medication', 'medications')}


def categories(text):
    words = set(re.findall(r'\w+', text.lower()))
    return [category for category, triggers in NEEDS.items() if words.intersection(triggers)] or ['other']


def required(body, name):
    value = body.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidInput(f'{name} is required')
    return value


def report(store, run_id, body, extract=categories):
    text = required(body, 'text')
    key = required(body, 'idempotency_key')
    board = store.get_board(run_id)
    if body.get('disaster_id') != board['disaster']['id']:
        raise NotFound('out-of-scope disaster')
    if not any(s['id'] == body.get('survivor_id') for s in board['survivors']):
        raise NotFound('unknown survivor')
    # The report fingerprint makes changed text with the same key conflict at the store.
    report_id = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    verdict = safety_check(text)
    if verdict['emergency']:
        store.emit_event(run_id, {'module': 'intake', 'action': 'human_escalation',
            'subject_id': body['survivor_id'], 'details': {'reason': verdict.get('reason'),
            'report_id': report_id}, 'idempotency_key': key + ':report'})
        return {'requests': [], 'escalated': True, 'message': emergency_line('en')}
    store.emit_event(run_id, {'module': 'intake', 'action': 'report_received',
        'subject_id': body['survivor_id'], 'details': {'report_id': report_id},
        'idempotency_key': key + ':report'})
    results = []
    for index, category in enumerate(extract(text)):
        results.append(store.create_request(run_id, {'survivor_id': body['survivor_id'],
            'disaster_id': body['disaster_id'], 'category': category,
            'description': f'{category.title()} requested in survivor report.',
            'source_report_id': report_id, 'idempotency_key': f'{key}:need:{index}'}))
    return {'requests': results}


def queue_follow_up(store, run_id, request_id, body):
    board = store.get_board(run_id)
    key = required(body, 'idempotency_key')
    previous = next((c for c in board['calls'] if c.get('queue_key') == key), None)
    if previous:
        if previous['request_id'] != request_id:
            raise Conflict('idempotency key was used for another request')
        return {'call': previous}
    request = next((r for r in board['requests'] if r['id'] == request_id), None)
    if request is None:
        raise NotFound('unknown request')
    if request['status'] not in ('awaiting_verification', 'reopened'):
        raise Conflict('follow-up requires an unresolved delivery')
    return {'call': store.save_call(run_id, {'request_id': request_id,
        'survivor_id': request['survivor_id'], 'status': 'queued',
        'provider_conversation_id': None, 'outcome': 'pending', 'summary': '',
        'evidence_ids': [], 'queue_key': key, 'idempotency_key': key})}


def decide(case, lessons_enabled=False):
    """Transparent baseline: no expected labels, medical advice, or household ranking."""
    text = case.get('report', '')
    if isinstance(text, dict):
        text = text.get('text', '')
    detected = categories(text)
    organizations = case.get('organizations', [])
    org = next((o for o in organizations if detected[0] in o.get('capabilities', [])), None)
    conditions = set(case.get('conditions', []))
    as_of = case.get('as_of')
    lessons = [lesson for lesson in case.get('lessons', []) if lessons_enabled
               and lesson.get('approved') is True and lesson.get('approved_at')
               and (not as_of or timestamp(lesson['approved_at']) <= timestamp(as_of))
               and conditions.intersection(lesson.get('conditions', []))]
    return {'categories': detected, 'organization_id': org['id'] if org else None,
            'status': ('resolved' if case.get('verification', {}).get('received') is True
                       and case.get('verification', {}).get('evidence_ids') else
                       'reopened' if case.get('verification', {}).get('received') is False
                       else 'awaiting_verification'),
            'evidence_ids': case.get('verification', {}).get('evidence_ids', []),
            'lesson_ids': [lesson['id'] for lesson in lessons],
            'recommendations': [{'lesson_id': lesson['id'], 'text': lesson['recommendation']}
                                for lesson in lessons]}


def handle(store, method, path, body=None, raw=None, headers=None):
    body = body or {}
    parts = [unquote(p) for p in urlsplit(path).path.split('/') if p]
    try:
        if (voice := voice_routes.route(store, method, path, body, raw, headers)) is not None:
            return voice
        if method == 'GET' and parts in (['disasters'], ['organizations']):
            table = parts[0]
            return 200, {table: getattr(store, 'list_' + table)()}
        if method == 'GET' and parts == ['background-311']:
            return background_routes.handle(store, path)
        if len(parts) < 3 or parts[0] != 'runs':
            return 404, {'error': 'not found'}
        run_id = parts[1]
        if parts[2] == 'helpers': return handle_helpers(store, method, run_id, parts[3:], body)
        if method == 'GET' and parts[2:] == ['board']:
            return 200, store.get_board(run_id)
        if method == 'POST' and parts[2:] == ['reports']:
            return 200, report(store, run_id, body)
        if method == 'POST' and len(parts) == 5 and parts[2] == 'requests':
            request_id, action = parts[3:]
            if action == 'follow-up':
                return 200, queue_follow_up(store, run_id, request_id, body)
            if action == 'verify':
                if body.get('source', 'human_review') != 'human_review':
                    raise InvalidInput('survivor_call evidence is server-generated only')
                return 200, store.verify_request(run_id, request_id, {**body, 'source': 'human_review'})
            fn = {'claim': store.claim_request, 'delivery': store.report_delivery}.get(action)
            if fn:
                return 200, {'request': fn(run_id, request_id, body)}
        if method == 'POST' and parts[2:] == ['lessons']:
            return 200, {'lesson': store.save_lesson(run_id, body)}
        if method == 'POST' and parts[2:] == ['evaluations', 'compare']:
            return 200, compare(store, run_id, body)
        if method == 'POST' and len(parts) == 5 and parts[2] == 'lessons' and parts[4] == 'approve':
            return 200, {'lesson': store.approve_lesson(run_id, parts[3], body)}
    except NotFound as exc:
        return 404, {'error': str(exc)}
    except Conflict as exc:
        return 409, {'error': str(exc)}
    except (InvalidInput, TypeError) as exc:
        return 400, {'error': str(exc)}
    return 404, {'error': 'not found'}


def compare(store, run_id, body):
    """Run only the synthetic fixture chosen by the server, never client labels."""
    from pathlib import Path

    from eval.recovery import run_comparison
    board = store.get_board(run_id)
    key = required(body, 'idempotency_key')
    fingerprint = sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    previous = [e for e in board['evaluations'] if e.get('invocation_key') == key]
    if previous and any(e.get('invocation_fingerprint') != fingerprint for e in previous):
        raise Conflict('idempotency key was used with another evaluation payload')
    if len(previous) == 2:
        return {'evaluations': previous}
    if previous:
        # The first immutable variant also records the full comparison. A retry
        # after a partial write reuses its UUID, timestamp, and measured results.
        result = previous[0]['comparison_result']
    else:
        with (Path(__file__).resolve().parents[1] / 'data/demo/held_out.json').open() as stream:
            fixture = json.load(stream)
        cases = fixture if isinstance(fixture, list) else fixture['cases']
        cases = [case for case in cases if case.get('disaster_id') == board['disaster']['id']]
        if not cases:
            raise InvalidInput('no evaluation cases for this run')
        result = run_comparison(cases, decide)
    records = []
    for variant in ('without_history', 'with_history'):
        records.append(store.save_evaluation(run_id, {'experiment_id': result['experiment_id'],
            'variant': variant, 'invocation_key': key, 'invocation_fingerprint': fingerprint, 'case_count': result['case_count'], 'metrics': result[variant],
            'measured_at': result['measured_at'], 'trace_url': result.get('trace_url'),
            'measurement_type': result['measurement_type'], 'limitations': result['limitations'],
            'comparison_result': result,
            'idempotency_key': key + ':' + variant}))
    return {'evaluations': records}
