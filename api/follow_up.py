"""Server-owned bridge from recovery calls to storage; no public evidence injection."""
from threading import RLock

from contracts.demo import NotFound

# The demo is one API process, with one serialized local execution lane.
_CALL_LOCK = RLock()


def execute_follow_up(store, run_id, call_id, transport, callback_number):
    """Explicit opt-in action. Inject ScriptedTransport for a no-network rehearsal.

    One process owns a local demo database. A crashed active job is intentionally
    left for human review, rather than risking a duplicate dial.
    """
    from calls.recovery import run_follow_up
    with _CALL_LOCK:
        board = store.get_board(run_id)
        call = next((c for c in board['calls'] if c['id'] == call_id), None)
        if call is None:
            raise NotFound('unknown call')
        request = next((r for r in board['requests'] if r['id'] == call['request_id']), None)
        if request is None:
            raise NotFound('unknown request')
        survivor = store.get_survivor(run_id, request['survivor_id'])
        job = {'call_id': call_id, 'request_id': request['id'], 'run_id': run_id,
               'disaster_id': board['disaster']['id']}

        def get_result(_):
            return call.get('recovery_result')

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
            # Persist the receipt evidence before applying its effect on the request.
            store.save_call(run_id, {**call, 'status': 'completed', 'outcome': result['outcome'],
                'summary': result['summary'], 'evidence_ids': result['evidence_ids'],
                'recovery_result': result, 'idempotency_key': call_id + ':completed'})
            if result['received'] is not None:
                store.verify_request(run_id, request['id'], {'received': result['received'],
                    'source': 'survivor_call', 'evidence_ids': result['evidence_ids'],
                    'notes': result['summary'], 'idempotency_key': call_id + ':verification'})

        context = {**job, 'request': request, 'survivor': survivor,
                   'callback_number': callback_number, 'claim_call': claim,
                   'get_call_result': get_result, 'finish_call': finish,
                   'emit_event': emit, 'escalate': escalate}
        result = run_follow_up(job, context, transport)
        # A retry after a crash between result storage and verification repairs
        # that last step idempotently, without another dial.
        if result['received'] is not None:
            store.verify_request(run_id, request['id'], {'received': result['received'],
                'source': 'survivor_call', 'evidence_ids': result['evidence_ids'],
                'notes': result['summary'], 'idempotency_key': call_id + ':verification'})
        return result
