"""Thread-safe offline adapter for Relay's small recovery contract."""
import json
import re
from copy import deepcopy
from datetime import datetime, timezone
from threading import RLock
from uuid import uuid4

from contracts.demo import Conflict, InvalidInput, NotFound


def now():
    return datetime.now(timezone.utc).isoformat()


def timestamp(value):
    try:
        result = datetime.fromisoformat(value.replace('Z', '+00:00'))
        if result.tzinfo is None:
            raise ValueError
        return result
    except (ValueError, TypeError, AttributeError):
        raise InvalidInput('timestamps must include a timezone') from None


class InMemoryRecoveryStore:
    def __init__(self, seed=None):
        self.data = deepcopy(seed or {})
        for table in ('disasters', 'organizations', 'runs', 'survivors', 'requests', 'calls',
                      'verifications', 'lessons', 'evaluations', 'system_events', 'helper_runs'):
            self.data.setdefault(table, [])
        self.lock = RLock()
        self.replays = {}

    def _scope(self, run_id):
        run = next((r for r in self.data['runs'] if r['run_id'] == run_id), None)
        if not run:
            raise NotFound('unknown run')
        return run['disaster_id']

    def _record(self, table, run_id, record_id):
        disaster = self._scope(run_id)
        record = next((r for r in self.data[table] if r['id'] == record_id
                       and r.get('run_id') == run_id and r.get('disaster_id') == disaster), None)
        if record is None:
            raise NotFound('unknown or out-of-scope record')
        return record

    def _new(self, run_id, payload):
        return {**deepcopy(payload), 'id': payload.get('id', str(uuid4())), 'run_id': run_id,
                'disaster_id': self._scope(run_id), 'created_at': now()}

    def _mutate(self, run_id, action, subject, payload, operation):
        with self.lock:
            disaster = self._scope(run_id)
            if payload.get('disaster_id', disaster) != disaster:
                raise NotFound('out-of-scope disaster')
            key = payload.get('idempotency_key')
            if not isinstance(key, str) or not key.strip():
                raise InvalidInput('idempotency_key is required')
            replay_key = (run_id, key)
            fingerprint = json.dumps([action, subject, payload], sort_keys=True)
            if replay_key in self.replays:
                previous, result = self.replays[replay_key]
                if previous != fingerprint:
                    raise Conflict('idempotency key was used with a different action or payload')
                return deepcopy(result)
            result = operation()
            self.data['system_events'].append(self._new(run_id, {
                'module': 'recovery', 'action': action, 'subject_id': subject or result.get('id'),
                'details': {}}))
            self.replays[replay_key] = (fingerprint, deepcopy(result))
            return deepcopy(result)

    def list_disasters(self):
        return deepcopy(self.data['disasters'])

    def list_organizations(self):
        return deepcopy(self.data['organizations'])

    def get_board(self, run_id):
        with self.lock:
            disaster = self._scope(run_id)
            result = {'run_id': run_id, 'disaster': next((d for d in self.list_disasters()
                      if d['id'] == disaster), None), 'organizations': self.list_organizations()}
            for table in ('survivors', 'requests', 'calls', 'verifications', 'evaluations', 'system_events'):
                result[table] = [deepcopy(r) for r in self.data[table]
                                 if r.get('run_id') == run_id and r.get('disaster_id') == disaster]
            result['survivors'] = [{k: v for k, v in s.items() if k in
                                    ('id', 'run_id', 'disaster_id', 'created_at', 'display_name', 'language', 'call_opt_in')}
                                   for s in result['survivors']]
            cutoff = next(r for r in self.data['runs'] if r['run_id'] == run_id).get('knowledge_cutoff', now())
            result['lessons'] = [deepcopy(r) for r in self.data['lessons']
                                 if (r.get('source_run_id') == run_id and r.get('source_disaster_id') == disaster)
                                 or (r.get('source_disaster_id') != disaster and r.get('approved') is True and r.get('approved_at')
                                     and timestamp(r['approved_at']) <= timestamp(cutoff)
                                     and timestamp(r.get('created_at', r['approved_at'])) <= timestamp(cutoff))]
            return result

    def create_request(self, run_id, payload):
        def create():
            self._record('survivors', run_id, payload.get('survivor_id'))
            for field in ('category', 'description', 'source_report_id'):
                if not isinstance(payload.get(field), str) or not payload[field].strip():
                    raise InvalidInput(f'{field} is required')
            row = self._new(run_id, {k: payload[k] for k in
                            ('survivor_id', 'category', 'description', 'source_report_id')})
            row.update(status='open', due_at=payload.get('due_at'), organization_id=None, promised_at=None)
            self.data['requests'].append(row)
            return row
        return self._mutate(run_id, 'request_created', None, payload, create)

    def claim_request(self, run_id, request_id, payload):
        def claim():
            row = self._record('requests', run_id, request_id)
            org = next((o for o in self.data['organizations'] if o['id'] == payload.get('organization_id')), None)
            if org is None:
                raise NotFound('unknown organization')
            if row['status'] not in ('open', 'reopened'):
                raise Conflict('request already claimed or closed')
            if row['category'] not in org['capabilities']:
                raise InvalidInput('organization does not support this category')
            promised = payload.get('promised_at')
            try:
                if datetime.fromisoformat(promised.replace('Z', '+00:00')).tzinfo is None:
                    raise ValueError
            except (ValueError, TypeError, AttributeError):
                raise InvalidInput('promised_at must be an ISO timestamp with timezone') from None
            row.update(status='claimed', organization_id=org['id'], promised_at=promised)
            return row
        return self._mutate(run_id, 'request_claimed', request_id, payload, claim)

    def report_delivery(self, run_id, request_id, payload):
        def delivery():
            row = self._record('requests', run_id, request_id)
            if row['status'] != 'claimed' or row['organization_id'] != payload.get('organization_id'):
                raise Conflict('delivery requires the claiming organization')
            row.update(status='awaiting_verification', delivery_notes=payload.get('notes', ''))
            return row
        return self._mutate(run_id, 'delivery_reported', request_id, payload, delivery)

    def verify_request(self, run_id, request_id, payload):
        def verify():
            row = self._record('requests', run_id, request_id)
            if row['status'] not in ('awaiting_verification', 'reopened'):
                raise Conflict('request is not awaiting verification')
            if payload.get('received') is not None and type(payload.get('received')) is not bool:
                raise InvalidInput('received must be true, false, or null')
            source = payload.get('source')
            if source not in ('human_review', 'survivor_call'):
                raise InvalidInput('invalid verification source')
            if source == 'survivor_call':
                matching = [c for c in self.data['calls'] if c.get('run_id') == run_id
                            and c.get('disaster_id') == self._scope(run_id) and c.get('request_id') == request_id
                            and c.get('status') == 'completed'
                            and ((payload.get('received') is True and c.get('outcome') == 'verified_received')
                                 or (payload.get('received') is False and c.get('outcome') == 'not_received')
                                 or payload.get('received') is None) and payload.get('evidence_ids')
                            and set(payload['evidence_ids']).issubset(c.get('evidence_ids', []))]
                if not matching:
                    raise InvalidInput('survivor verification requires stored call evidence')
            verification = self._new(run_id, {'request_id': request_id, 'received': payload.get('received'),
                        'source': source, 'evidence_ids': payload.get('evidence_ids', []), 'notes': payload.get('notes', '')})
            self.data['verifications'].append(verification)
            if payload.get('received') is True:
                row['status'] = 'resolved'
            elif payload.get('received') is False:
                row['status'] = 'reopened'
                self.data['system_events'].append(self._new(run_id, {'module': 'recovery',
                    'action': 'human_escalation', 'subject_id': request_id, 'details': {'reason': 'delivery_not_received'}}))
            return {'request': row, 'verification': verification}
        return self._mutate(run_id, 'request_verified', request_id, payload, verify)

    def save_call(self, run_id, payload):
        def save():
            request = self._record('requests', run_id, payload.get('request_id'))
            survivor = self._record('survivors', run_id, request['survivor_id'])
            if payload.get('survivor_id', survivor['id']) != survivor['id']:
                raise NotFound('survivor mismatch')
            if survivor.get('call_opt_in') is not True:
                raise InvalidInput('confirmed survivor call opt-in is required')
            clean = {k: v for k, v in payload.items() if k not in ('idempotency_key', 'phone', 'phone_number')}
            clean['survivor_id'] = survivor['id']
            row = self._new(run_id, clean)
            existing = next((c for c in self.data['calls'] if c['id'] == row['id']), None)
            if existing:
                if existing['run_id'] != run_id or existing['disaster_id'] != self._scope(run_id):
                    raise NotFound('out-of-scope call')
                if existing['request_id'] != request['id'] or existing['survivor_id'] != survivor['id']:
                    raise Conflict('call request and survivor cannot change')
                allowed = {'queued': 'active', 'active': 'completed'}
                if allowed.get(existing['status']) != row.get('status'):
                    raise Conflict('call must advance queued -> active -> completed; terminal calls are immutable')
                row['created_at'] = existing['created_at']
                existing.update(row)
                return existing
            if row.get('status') != 'queued':
                raise InvalidInput('new calls must be queued before execution')
            self.data['calls'].append(row)
            return row
        return self._mutate(run_id, 'call_saved', payload.get('id'), payload, save)

    def save_lesson(self, run_id, payload):
        def save():
            outcomes = payload.get('source_outcome_ids', [])
            if not outcomes:
                raise InvalidInput('lesson requires verified source outcomes')
            receipts = []
            for outcome in outcomes:
                verification = self._record('verifications', run_id, outcome)
                receipts.append(verification.get('received'))
            if True not in receipts:
                raise InvalidInput('lesson requires at least one confirmed receipt')
            content = json.dumps([payload.get('summary'), payload.get('conditions'), payload.get('recommendation')])
            if re.search(r'[\w.+-]+@[\w.-]+|(?:\+?\d[ ().-]*){7,}', content):
                raise InvalidInput('lesson must be de-identified')
            for survivor in self.data['survivors']:
                for field in ('display_name', 'phone', 'phone_number', 'email', 'address'):
                    value = survivor.get(field)
                    if isinstance(value, str) and value and value.lower() in content.lower():
                        raise InvalidInput('lesson must not include survivor details')
            for field in ('summary', 'recommendation'):
                if not isinstance(payload.get(field), str) or not payload[field].strip():
                    raise InvalidInput(f'{field} is required')
            if not isinstance(payload.get('conditions'), list) or not all(isinstance(c, str) for c in payload['conditions']):
                raise InvalidInput('conditions must be a string list')
            row = {k: deepcopy(payload.get(k)) for k in ('summary', 'conditions', 'recommendation', 'source_outcome_ids')}
            row.update(id=str(uuid4()), source_run_id=run_id, source_disaster_id=self._scope(run_id),
                       approved=False, approved_at=None, created_at=now())
            self.data['lessons'].append(row)
            return row
        return self._mutate(run_id, 'lesson_drafted', None, payload, save)

    def approve_lesson(self, run_id, lesson_id, payload):
        def approve():
            row = next((r for r in self.data['lessons'] if r['id'] == lesson_id
                        and r.get('source_run_id') == run_id and r.get('source_disaster_id') == self._scope(run_id)), None)
            if row is None:
                raise NotFound('unknown lesson')
            # Approval is an explicit coordinator review of the de-identified draft.
            row.update(approved=True, approved_at=now())
            return row
        return self._mutate(run_id, 'lesson_approved', lesson_id, payload, approve)

    def save_evaluation(self, run_id, payload):
        def save():
            row = self._new(run_id, {k: v for k, v in payload.items() if k != 'idempotency_key'})
            self.data['evaluations'].append(row)
            return row
        return self._mutate(run_id, 'evaluation_saved', None, payload, save)

    def save_helper_run(self, run_id, payload):
        def save():
            row = self._new(run_id, {k: v for k, v in payload.items() if k != 'idempotency_key'})
            self.data['helper_runs'].append(row)
            return row
        return self._mutate(run_id, 'helper_run_saved', None, payload, save)

    def list_helper_runs(self, run_id):
        with self.lock:
            disaster = self._scope(run_id)
            return [deepcopy(r) for r in self.data['helper_runs']
                    if r.get('run_id') == run_id and r.get('disaster_id') == disaster]

    def snapshot(self):
        with self.lock:
            return {'data': deepcopy(self.data), 'replays': [
                [run, key, fingerprint, deepcopy(result)]
                for (run, key), (fingerprint, result) in self.replays.items()]}

    @classmethod
    def from_snapshot(cls, snapshot):
        store = cls(snapshot['data'])
        store.replays = {(run, key): (fingerprint, deepcopy(result))
                         for run, key, fingerprint, result in snapshot.get('replays', [])}
        return store

    def emit_event(self, run_id, payload):
        def emit():
            event = self._new(run_id, {k: deepcopy(payload[k]) for k in
                                     ('module', 'action', 'subject_id', 'details')})
            self.data['system_events'].append(event)
            return event
        # emit itself is the audit event: do not append a duplicate wrapper event.
        with self.lock:
            before = len(self.data['system_events'])
            result = self._mutate(run_id, 'event_emitted', payload.get('subject_id'), payload, emit)
            if len(self.data['system_events']) == before + 2:
                self.data['system_events'].pop()
            return result

    def get_survivor(self, run_id, survivor_id):
        """Server-only contact lookup, never included in a public board."""
        with self.lock:
            return deepcopy(self._record('survivors', run_id, survivor_id))
