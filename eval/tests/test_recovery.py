"""Synthetic metric checks, label isolation, time cutoffs and optional tracing."""

import json
from copy import deepcopy
from pathlib import Path

import pytest

from eval.arize import configure_arize, trace_comparison
from eval.recovery import run_comparison

FIXTURE = Path(__file__).resolve().parents[2] / 'data' / 'demo'


def cases():
    return json.loads((FIXTURE / 'held_out.json').read_text())


def decision(case, *, lessons_enabled):
    category = case['conditions'][0]
    verification = case['verification']
    return {'categories': [category], 'organization_id': next(
        org['id'] for org in case['organizations'] if category in org['capabilities']),
        'status': 'resolved' if verification.get('received') is True else 'awaiting_verification',
        'evidence_ids': verification.get('evidence_ids', []),
        'lesson_ids': [lesson['id'] for lesson in case['lessons']
                    if set(lesson['conditions']) <= set(case['conditions'])]}


def test_known_metrics_and_no_labels():
    seen = []

    def spy(case, *, lessons_enabled):
        assert 'expected' not in case and 'id' not in case
        seen.append((deepcopy(case), lessons_enabled))
        return decision(case, lessons_enabled=lessons_enabled)

    result = run_comparison(cases(), spy)
    assert result['case_count'] == 3
    assert result['measurement_type'] == 'synthetic_deterministic'
    assert result['trace_url'] is None
    for variant in ('without_history', 'with_history'):
        assert result[variant]['category_extraction'] == 1
        assert result[variant]['organization_compatibility'] == 1
        assert result[variant]['false_closure'] == 0
        assert result[variant]['groundedness'] == 1
    assert result['without_history']['relevant_lesson_use'] is None
    assert result['with_history']['relevant_lesson_use'] == 1
    assert seen[0][0]['run_id'] != seen[3][0]['run_id']
    for before, after in zip(seen[:3], seen[3:]):
        a, b = before[0], after[0]
        for key in a.keys() - {'run_id', 'lessons'}:
            assert a[key] == b[key]


def test_future_approval_and_unapproved_context_excluded():
    rows = cases()[:1]
    future = deepcopy(rows[0]['lessons'][0])
    future.update(id='future', approved_at='2027-01-01T00:00:00Z')
    unapproved = deepcopy(future)
    unapproved.update(id='unapproved', approved=False)
    same_disaster = deepcopy(rows[0]['lessons'][0])
    same_disaster.update(id='held-out-leak', source_disaster_id=rows[0]['disaster_id'])
    rows[0]['lessons'] += [future, unapproved, same_disaster]

    def spy(case, *, lessons_enabled):
        assert all(item['id'] == 'lesson-confirm-handoff' for item in case['lessons'])
        return decision(case, lessons_enabled=lessons_enabled)

    run_comparison(rows, spy)
    rows[0]['as_of'] = '2026-01-01T00:00:00'
    with pytest.raises(ValueError, match='timezone'):
        run_comparison(rows, spy)


def test_false_closure_unsupported_citations_and_input_mutation():
    def wrong(case, *, lessons_enabled):
        case['verification'].update(received=True, evidence_ids=['invented'])
        return {'categories': ['wrong'], 'organization_id': 'wrong', 'status': 'resolved',
                    'evidence_ids': ['invented'], 'lesson_ids': ['invented']}

    result = run_comparison(cases()[:1], wrong)
    assert result['with_history']['false_closure'] == 1
    assert result['with_history']['groundedness'] == 0
    assert result['with_history']['category_extraction'] == 0
    assert result['with_history']['organization_compatibility'] == 0
    assert result['with_history']['relevant_lesson_use'] == 0
    assert run_comparison([], wrong)['with_history']['groundedness'] is None


def test_seed_is_scoped_and_lesson_has_real_outcomes():
    seed = json.loads((FIXTURE / 'seed.json').read_text())
    scopes = {r['run_id']: r['disaster_id'] for r in seed['runs']}
    for collection in ('survivors', 'requests', 'calls', 'verifications', 'evaluations', 'system_events'):
        for row in seed[collection]:
            assert scopes[row['run_id']] == row['disaster_id']
    outcomes = {v['id']: v for v in seed['verifications']}
    for lesson in seed['lessons']:
        assert lesson['source_outcome_ids']
        for outcome_id in lesson['source_outcome_ids']:
            assert outcomes[outcome_id]['run_id'] == lesson['source_run_id']
            assert outcomes[outcome_id]['created_at'] < lesson['approved_at']
    assert all('phone' not in survivor for survivor in seed['survivors'])


def test_explicit_registration_and_missing_credentials(monkeypatch):
    monkeypatch.delenv('ARIZE_SPACE_ID', raising=False)
    with pytest.raises(ValueError):
        configure_arize(register=lambda **kwargs: pytest.fail('must not register'))
    monkeypatch.setenv('ARIZE_SPACE_ID', 'test-space')
    monkeypatch.setenv('ARIZE_API_KEY', 'test-key')
    captured = {}

    def register(**kwargs):
        captured.update(kwargs)
        return 'provider'

    assert configure_arize(register=register, transport='http') == 'provider'
    assert captured['endpoint'] == 'https://otlp.arize.com/v1/traces'
    assert captured['api_key'] == 'test-key'


def test_real_otel_exporter_with_mock_transport():
    # Optional integration dependency; no network or live Arize credentials.
    from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import SimpleSpanProcessor

    class Response:
        ok = True
        status_code = 200
        text = ''
        reason = 'OK'

    class Session:
        def __init__(self):
            self.headers = {}
            self.requests = []

        def request(self, method, url, **kwargs):
            assert method == "POST"
            self.requests.append((url, kwargs))
            return Response()

        def post(self, url, **kwargs):
            self.requests.append((url, kwargs))
            return Response()

        def close(self):
            pass

    session = Session()
    exporter = OTLPSpanExporter(endpoint='https://otlp.arize.com/v1/traces', session=session,
                                headers={'arize-space-id': 'test', 'arize-api-key': 'test'})
    provider = TracerProvider()
    provider.add_span_processor(SimpleSpanProcessor(exporter))
    result = run_comparison(cases(), decision)
    trace_comparison(provider, result)
    provider.shutdown()
    assert len(session.requests) == 1
    body = session.requests[0][1]['data']
    assert b'relay.with_history.category_extraction' in body
    assert b'We need food' not in body
    assert b'expected' not in body
    assert result['trace_url'] is None


def test_installed_arize_registration_path(monkeypatch):
    import arize.otel

    monkeypatch.setenv("ARIZE_SPACE_ID", "test-space")
    monkeypatch.setenv("ARIZE_API_KEY", "test-key")
    captured = {}

    def register(**kwargs):
        captured.update(kwargs)
        return "provider"

    monkeypatch.setattr(arize.otel, "register", register)
    assert configure_arize() == "provider"
    assert captured["transport"] == arize.otel.Transport.HTTP
    assert captured["set_global_tracer_provider"] is False
