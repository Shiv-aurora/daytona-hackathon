"""Recovery contract behavior, concurrency, consent, isolation, and evidence."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy

import pytest

from api.demo_store import InMemoryRecoveryStore
from api.recovery import handle, report
from contracts.demo import Conflict, InvalidInput, NotFound


@pytest.fixture
def store():
    return InMemoryRecoveryStore({
        'disasters': [{'id': 'd1'}, {'id': 'd2'}],
        'organizations': [{'id': 'o1', 'capabilities': ['food', 'supplies']},
                          {'id': 'o2', 'capabilities': ['food']}],
        'runs': [{'run_id': 'r1', 'disaster_id': 'd1'}, {'run_id': 'r2', 'disaster_id': 'd2'}],
        'survivors': [{'id': 's1', 'run_id': 'r1', 'disaster_id': 'd1', 'call_opt_in': True,
                       'display_name': 'Demo Person', 'phone': '+15550000000', 'email': 'private@example.com'},
                      {'id': 's2', 'run_id': 'r2', 'disaster_id': 'd2', 'call_opt_in': False}]})


def submit(store):
    body = {'disaster_id': 'd1', 'text': 'Need food and supplies', 'survivor_id': 's1', 'idempotency_key': 'report1'}
    return report(store, 'r1', body), body


def delivery(store, request_id):
    store.claim_request('r1', request_id, {'organization_id': 'o1', 'promised_at': '2026-10-17T10:00:00Z',
                                          'idempotency_key': 'claim1'})
    return store.report_delivery('r1', request_id, {'organization_id': 'o1', 'notes': 'at doorstep',
                                                  'idempotency_key': 'delivery1'})


def test_full_story_and_replay(store):
    result, body = submit(store)
    assert len(result['requests']) == 2
    assert report(store, 'r1', body) == result
    request_id = result['requests'][0]['id']
    assert delivery(store, request_id)['status'] == 'awaiting_verification'
    verification = store.verify_request('r1', request_id, {'received': False, 'source': 'human_review',
                                                        'idempotency_key': 'verify1'})
    assert verification['request']['status'] == 'reopened'
    receipt = store.verify_request('r1', request_id, {'received': True, 'source': 'human_review',
                                                   'idempotency_key': 'verify2'})
    lesson = store.save_lesson('r1', {'summary': 'Verify handoffs', 'conditions': ['flood'],
             'recommendation': 'Confirm receipt before closing.',
             'source_outcome_ids': [verification['verification']['id'], receipt['verification']['id']],
             'idempotency_key': 'lesson1'})
    assert not store.get_board('r2')['lessons']
    store.approve_lesson('r1', lesson['id'], {'idempotency_key': 'approve1'})
    assert store.get_board('r2')['lessons'][0]['id'] == lesson['id']
    assert any(e['action'] == 'human_escalation' for e in store.get_board('r1')['system_events'])
    assert store.get_board('r1')['survivors'][0].keys().isdisjoint({'phone', 'email'})


def test_concurrent_claim_single_winner_and_replay_payload_conflict(store):
    result, body = submit(store)
    request_id = result['requests'][0]['id']
    def claim(org):
        try:
            return store.claim_request('r1', request_id, {'organization_id': org,
                 'promised_at': '2026-10-17T10:00:00Z', 'idempotency_key': org})['status']
        except Conflict:
            return 'conflict'
    with ThreadPoolExecutor(max_workers=2) as pool:
        assert sorted(pool.map(claim, ['o1', 'o2'])) == ['claimed', 'conflict']
    with pytest.raises(Conflict):
        report(store, 'r1', {**body, 'text': 'Need food only'})
    assert len(store.get_board('r1')['requests']) == 2


def test_emergency_before_extraction_and_event_replay(store):
    body = {'disaster_id': 'd1', 'text': "I can't breathe", 'survivor_id': 's1', 'idempotency_key': 'emergency1'}
    def forbidden(_):
        pytest.fail('model called on emergency')
    assert report(store, 'r1', body, forbidden)['escalated']
    assert report(store, 'r1', body, forbidden)['escalated']
    events = store.get_board('r1')['system_events']
    assert len(events) == 1 and events[0]['action'] == 'human_escalation'
    assert not store.get_board('r1')['requests']


def test_foreign_scope_forged_receipt_and_opt_in(store):
    result, _ = submit(store)
    request_id = result['requests'][0]['id']
    with pytest.raises(NotFound):
        store.claim_request('r2', request_id, {'idempotency_key': 'x'})
    delivery(store, request_id)
    status, _ = handle(store, 'POST', f'/runs/r1/requests/{request_id}/verify',
                       {'received': True, 'source': 'survivor_call', 'idempotency_key': 'forge'})
    assert status == 400
    with pytest.raises(InvalidInput):
        store.verify_request('r1', request_id, {'received': True, 'source': 'survivor_call',
                                               'evidence_ids': ['fake'], 'idempotency_key': 'forge2'})
    foreign = store.create_request('r2', {'survivor_id': 's2', 'category': 'food', 'description': 'Food',
                                          'source_report_id': 'report2', 'idempotency_key': 'create2'})
    with pytest.raises(InvalidInput):
        store.save_call('r2', {'request_id': foreign['id'], 'idempotency_key': 'no-consent'})


def test_snapshot_retains_replay_and_cutoff(store):
    result, body = submit(store)
    restored = InMemoryRecoveryStore.from_snapshot(store.snapshot())
    assert report(restored, 'r1', body) == result
    assert len(restored.data['system_events']) == len(store.data['system_events'])
    store.data['lessons'] = [{'id': 'future', 'source_run_id': 'r2', 'source_disaster_id': 'd2',
                            'approved': True, 'approved_at': '2026-12-01T00:00:00Z'}]
    store.data['runs'][0]['knowledge_cutoff'] = '2026-10-16T00:00:00Z'
    assert not store.get_board('r1')['lessons']


def test_failed_mutations_leave_state_unchanged(store):
    result, _ = submit(store)
    before = deepcopy(store.snapshot())
    with pytest.raises(InvalidInput):
        store.claim_request('r1', result['requests'][0]['id'], {'organization_id': 'o1',
                'promised_at': 'nope', 'idempotency_key': 'invalid-date'})
    assert store.snapshot() == before
