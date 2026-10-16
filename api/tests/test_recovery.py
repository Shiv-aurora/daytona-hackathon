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


def test_real_call_hooks_missed_receipt_replay_and_later_receipt(store):
    from api.demo import ScriptedTransport
    from api.follow_up import execute_follow_up
    from api.recovery import queue_follow_up
    result, _ = submit(store)
    request_id = result['requests'][0]['id']
    delivery(store, request_id)
    call = queue_follow_up(store, 'r1', request_id, {'idempotency_key': 'queue1'})['call']
    missed = execute_follow_up(store, 'r1', call['id'], ScriptedTransport('no'), '+15555550100')
    assert missed['outcome'] == 'not_received'
    assert store.get_board('r1')['requests'][0]['status'] == 'reopened'
    class NeverDial(ScriptedTransport):
        def dial(self, _):
            pytest.fail('replayed call dialed')
    assert execute_follow_up(store, 'r1', call['id'], NeverDial('yes'), '+15555550100') == missed
    second = queue_follow_up(store, 'r1', request_id, {'idempotency_key': 'queue2'})['call']
    received = execute_follow_up(store, 'r1', second['id'], ScriptedTransport('yes'), '+15555550100')
    assert received['outcome'] == 'verified_received'
    assert store.get_board('r1')['requests'][0]['status'] == 'resolved'
    assert queue_follow_up(store, 'r1', request_id, {'idempotency_key': 'queue2'})['call']['id'] == second['id']


def test_real_call_emergency_escalates_without_resolution(store):
    from api.demo import ScriptedTransport
    from api.follow_up import execute_follow_up
    from api.recovery import queue_follow_up
    result, _ = submit(store)
    request_id = result['requests'][0]['id']
    delivery(store, request_id)
    call = queue_follow_up(store, 'r1', request_id, {'idempotency_key': 'queue1'})['call']
    result = execute_follow_up(store, 'r1', call['id'], ScriptedTransport("I can't breathe"), '+15555550100')
    assert result['emergency'] is True
    board = store.get_board('r1')
    assert board['requests'][0]['status'] == 'awaiting_verification'
    assert not board['verifications']
    assert any(e['action'] == 'human_escalation' for e in board['system_events'])


def test_actual_seed_evaluation_replay_and_changed_payload():
    import json
    from pathlib import Path

    from api.recovery import compare
    seed = json.loads((Path(__file__).resolve().parents[2] / 'data/demo/seed.json').read_text())
    store = InMemoryRecoveryStore(seed)
    body = {'idempotency_key': 'evaluation1'}
    result = compare(store, 'demo-current', body)
    assert result == compare(store, 'demo-current', body)
    assert len(result['evaluations']) == 2
    assert result['evaluations'][0]['case_count'] == 3
    with pytest.raises(Conflict):
        compare(store, 'demo-current', {**body, 'changed': True})
    assert len(store.get_board('demo-current')['evaluations']) == 2


def test_cross_run_same_disaster_lesson_and_timezone_cutoff(store):
    store.data['runs'].append({'run_id': 'r3', 'disaster_id': 'd1', 'knowledge_cutoff': '2026-10-16T12:00:00+00:00'})
    store.data['lessons'] = [
        {'id': 'same', 'source_run_id': 'r1', 'source_disaster_id': 'd1',
         'approved': True, 'approved_at': '2026-10-15T10:00:00Z'},
        {'id': 'offset-future', 'source_run_id': 'r2', 'source_disaster_id': 'd2',
         'approved': True, 'approved_at': '2026-10-16T11:00:00-05:00'},
        {'id': 'offset-past', 'source_run_id': 'r2', 'source_disaster_id': 'd2',
         'approved': True, 'approved_at': '2026-10-16T13:00:00+05:00'}]
    assert [l['id'] for l in store.get_board('r3')['lessons']] == ['offset-past']


@pytest.mark.parametrize('text', ['We need food and blankets', 'We need meals and diapers',
                                 'We need groceries and supplies'])
def test_report_splits_mixed_food_and_plural_supplies(store, text):
    result = report(store, 'r1', {'disaster_id': 'd1', 'survivor_id': 's1',
                                 'text': text, 'idempotency_key': 'plural-report'})
    assert [r['category'] for r in result['requests']] == ['food', 'supplies']


def test_category_vocabulary_does_not_stem_unrelated_terms():
    from api.recovery import categories
    assert categories('The medic is preparing a statement about busyness') == ['other']
    assert categories('medications and repairs') == ['repairs', 'medicine']


def test_call_transitions_cannot_rewind_reassign_or_skip(store):
    from api.recovery import queue_follow_up
    result, _ = submit(store)
    request_id = result['requests'][0]['id']
    delivery(store, request_id)
    call = queue_follow_up(store, 'r1', request_id, {'idempotency_key': 'queue'})['call']
    for status in ('active', 'completed'):
        payload = {**call, 'status': status, 'idempotency_key': status}
        updated = store.save_call('r1', payload)
        assert updated['created_at'] == call['created_at']
        before = store.snapshot()
        assert store.save_call('r1', payload) == updated
        assert store.snapshot() == before
        for rewind in ('queued', status):
            with pytest.raises(Conflict):
                store.save_call('r1', {**call, 'status': rewind, 'idempotency_key': status + '-' + rewind})
        with pytest.raises(Conflict):
            store.save_call('r1', {**call, 'request_id': result['requests'][1]['id'],
                                  'status': 'completed', 'idempotency_key': status + '-reassign'})
    with pytest.raises(Conflict):
        store.save_call('r1', {**call, 'status': 'active', 'idempotency_key': 'terminal-redial'})
    with pytest.raises(InvalidInput):
        store.save_call('r1', {'request_id': request_id, 'status': 'completed', 'idempotency_key': 'skip-queue'})
    queued = queue_follow_up(store, 'r1', request_id, {'idempotency_key': 'queue2'})['call']
    with pytest.raises(Conflict):
        store.save_call('r1', {**queued, 'status': 'completed', 'idempotency_key': 'skip-active'})


def test_evaluation_repairs_partial_write_without_measuring_again(monkeypatch):
    import json
    from pathlib import Path

    import eval.recovery
    from api.recovery import compare

    seed = json.loads((Path(__file__).resolve().parents[2] / 'data/demo/seed.json').read_text())
    store = InMemoryRecoveryStore(seed)
    original_save = store.save_evaluation
    attempts = []
    def interrupted_save(run_id, payload):
        attempts.append(payload['variant'])
        if payload['variant'] == 'with_history':
            raise RuntimeError('simulated interruption after first persisted variant')
        return original_save(run_id, payload)
    monkeypatch.setattr(store, 'save_evaluation', interrupted_save)
    with pytest.raises(RuntimeError):
        compare(store, 'demo-current', {'idempotency_key': 'partial'})
    first = store.get_board('demo-current')['evaluations'][0]
    restored = InMemoryRecoveryStore.from_snapshot(store.snapshot())
    def never_measure_again(*args):
        pytest.fail('partial replay measured the experiment again')
    monkeypatch.setattr(eval.recovery, 'run_comparison', never_measure_again)
    records = compare(restored, 'demo-current', {'idempotency_key': 'partial'})['evaluations']
    assert len(records) == 2 and records[0] == first
    assert {r['experiment_id'] for r in records} == {first['experiment_id']}
    assert {r['measured_at'] for r in records} == {first['measured_at']}
    assert all(r['measurement_type'] == 'synthetic_deterministic' and r['limitations'] for r in records)
    assert len(restored.get_board('demo-current')['evaluations']) == 2
