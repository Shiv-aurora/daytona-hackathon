"""Small recovery HTTP boundary; all external services remain injected/optional."""
import json
import re
from hashlib import sha256
from urllib.parse import unquote, urlsplit

from calls.safety import emergency_line, safety_check
from contracts.demo import Conflict, InvalidInput, NotFound

NEEDS = {'food': ('food', 'meal', 'groceries', 'water'),
         'supplies': ('supplies', 'blanket', 'diaper', 'hygiene'),
         'transportation': ('transport', 'ride', 'bus'),
         'shelter': ('shelter', 'housing'), 'repairs': ('repair', 'roof'),
         'medicine': ('medicine', 'medication')}


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
    request = next((r for r in board['requests'] if r['id'] == request_id), None)
    if request is None:
        raise NotFound('unknown request')
    if request['status'] not in ('awaiting_verification', 'reopened'):
        raise Conflict('follow-up requires an unresolved delivery')
    return {'call': store.save_call(run_id, {'request_id': request_id,
        'survivor_id': request['survivor_id'], 'status': 'queued',
        'provider_conversation_id': None, 'outcome': 'pending', 'summary': '',
        'evidence_ids': [], 'idempotency_key': required(body, 'idempotency_key')})}


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
               and (not as_of or lesson['approved_at'] <= as_of)
               and conditions.intersection(lesson.get('conditions', []))]
    return {'categories': detected, 'organization_id': org['id'] if org else None,
            'status': 'awaiting_verification', 'evidence_ids': [],
            'lesson_ids': [lesson['id'] for lesson in lessons],
            'recommendations': [{'lesson_id': lesson['id'], 'text': lesson['recommendation']}
                                for lesson in lessons]}


def handle(store, method, path, body=None):
    body = body or {}
    parts = [unquote(p) for p in urlsplit(path).path.split('/') if p]
    try:
        if method == 'GET' and parts in (['disasters'], ['organizations']):
            table = parts[0]
            return 200, {table: getattr(store, 'list_' + table)()}
        if len(parts) < 3 or parts[0] != 'runs':
            return 404, {'error': 'not found'}
        run_id = parts[1]
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
    store.get_board(run_id)
    key = required(body, 'idempotency_key')
    with Path('data/demo/evaluation_cases.json').open() as stream:
        fixture = json.load(stream)
    cases = fixture if isinstance(fixture, list) else fixture['cases']
    cases = [case for case in cases if case.get('run_id') == run_id]
    if not cases:
        raise InvalidInput('no evaluation cases for this run')
    result = run_comparison(cases, decide)
    records = []
    for variant in ('without_history', 'with_history'):
        records.append(store.save_evaluation(run_id, {'experiment_id': result['experiment_id'],
            'variant': variant, 'case_count': result['case_count'], 'metrics': result[variant],
            'measured_at': result['measured_at'], 'trace_url': result.get('trace_url'),
            'idempotency_key': key + ':' + variant}))
    return {'evaluations': records}
