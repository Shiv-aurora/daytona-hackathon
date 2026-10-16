"""Arize tracing is opt-in, de-identified, and behavior-neutral. No network."""
from contextlib import contextmanager

import pytest

from api.recovery import decide
from calls.fakes import FakeTransport
from calls.recovery import run_follow_up
from eval import arize_trace
from eval.arize_trace import clean, traced


class FakeSpan:
    def __init__(self):
        self.attributes = {}

    def set_attribute(self, key, value):
        self.attributes[key] = value


class FakeTracer:
    def __init__(self):
        self.spans = []

    @contextmanager
    def start_as_current_span(self, name):
        span = FakeSpan()
        self.spans.append((name, span))
        yield span


@pytest.fixture(autouse=True)
def reset(monkeypatch):
    monkeypatch.delenv('ARIZE_API_KEY', raising=False)
    monkeypatch.delenv('ARIZE_SPACE_ID', raising=False)
    arize_trace.set_tracer(None)
    yield
    arize_trace.set_tracer(None)


@pytest.fixture
def tracer():
    fake = FakeTracer()
    arize_trace.set_tracer(fake)
    return fake


def test_noop_without_keys(monkeypatch):
    monkeypatch.setattr('eval.arize.configure_arize',
                        lambda **kw: pytest.fail('must not register without keys'))
    assert not arize_trace.enabled()
    with traced('x', run_id='r1') as span:
        span.set(outcome='ok')
    assert arize_trace._get_tracer() is None

    @traced('y')
    def add(a, b):
        return a + b
    assert add(1, 2) == 3


def test_registration_failure_is_swallowed(monkeypatch):
    monkeypatch.setenv('ARIZE_API_KEY', 'k')
    monkeypatch.setenv('ARIZE_SPACE_ID', 's')

    def boom(**kw):
        raise RuntimeError('no network')
    monkeypatch.setattr('eval.arize.configure_arize', boom)
    with traced('x', run_id='r1'):
        pass


def test_free_text_and_unknown_attributes_are_dropped(tracer):
    attrs = {'run_id': 'run-a', 'disaster_id': 'flood-a', 'outcome': 'not_received',
             'emergency': False, 'lesson_ids': ['l1'], 'text': 'My name is Ana at 5 Elm St',
             'description': 'Food requested', 'phone': '+12125550123', 'survivor_id': 's1',
             'transcript': ['hello'], 'summary': 'x', 'category': 'y' * 500}
    assert clean(attrs) == {'relay.run_id': 'run-a', 'relay.disaster_id': 'flood-a',
                            'relay.outcome': 'not_received', 'relay.emergency': False,
                            'relay.lesson_ids': ['l1']}
    with traced('x', **attrs) as span:
        span.set(report='free text', status='ok')
    recorded = tracer.spans[0][1].attributes
    assert set(recorded) <= {'openinference.span.kind'} | {'relay.' + k for k in arize_trace.ALLOWED}
    assert 'relay.status' in recorded
    assert 'Ana' not in repr(recorded)


def test_follow_up_outcome_unchanged_and_traced(tracer):
    def run():
        job = {'call_id': 'call-1', 'request_id': 'req-1', 'run_id': 'run-a', 'disaster_id': 'flood-a'}
        results, events = {}, []
        context = {'run_id': 'run-a', 'disaster_id': 'flood-a',
                   'request': {'id': 'req-1', 'survivor_id': 'sv-1', 'description': 'food delivery',
                               'run_id': 'run-a', 'disaster_id': 'flood-a'},
                   'survivor': {'id': 'sv-1', 'call_opt_in': True, 'language': 'en',
                                'run_id': 'run-a', 'disaster_id': 'flood-a'},
                   'callback_number': '+12125550123', 'claim_call': lambda j: True,
                   'get_call_result': results.get,
                   'finish_call': lambda j, r: results.setdefault(j['call_id'], r),
                   'emit_event': events.append, 'escalate': lambda e: None}
        return run_follow_up(job, context, FakeTransport(['no'])), events

    traced_result, traced_events = run()
    arize_trace.set_tracer(None)
    plain_result, plain_events = run()
    assert traced_result == plain_result and traced_result['outcome'] == 'not_received'
    assert [e['action'] for e in traced_events] == [e['action'] for e in plain_events]
    name, span = tracer.spans[0]
    assert name == 'relay.follow_up.outcome'
    assert span.attributes['relay.outcome'] == 'not_received'
    assert span.attributes['relay.run_id'] == 'run-a'
    assert span.attributes['relay.emergency'] is False
    assert not any('food' in str(v) or '2125550123' in str(v) for v in span.attributes.values())


def test_decide_unchanged_and_traces_lesson_ids(tracer):
    case = {'disaster_id': 'flood-a', 'report': 'We need food. My name is Ana Smith.',
            'organizations': [{'id': 'org-1', 'capabilities': ['food']}], 'conditions': ['flood'],
            'lessons': [{'id': 'lesson-1', 'approved': True, 'approved_at': '2020-01-01T00:00:00Z',
                         'conditions': ['flood'], 'recommendation': 'Call ahead'}]}
    with_trace = decide(case, lessons_enabled=True)
    arize_trace.set_tracer(None)
    assert decide(case, lessons_enabled=True) == with_trace
    assert with_trace['lesson_ids'] == ['lesson-1']
    attrs = tracer.spans[0][1].attributes
    assert attrs['relay.lesson_ids'] == ['lesson-1']
    assert attrs['relay.category'] == 'food'
    assert 'Ana' not in repr(attrs)
