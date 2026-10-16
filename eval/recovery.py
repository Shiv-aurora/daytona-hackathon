"""Controlled, synthetic recovery evaluation; held-out labels never reach decisions."""

from copy import deepcopy
from datetime import datetime, timezone
from uuid import uuid4


def _time(value):
    result = datetime.fromisoformat(value.replace('Z', '+00:00'))
    if result.tzinfo is None:
        raise ValueError('Evaluation timestamps must include a timezone')
    return result


def _decision_input(case, run_id, lessons_enabled):
    cutoff = _time(case['as_of'])
    lessons = []
    if lessons_enabled:
        for lesson in case.get('lessons', []):
            if (lesson.get('source_disaster_id') != case['disaster_id']
                    and lesson.get('approved') is True and lesson.get('approved_at')
                    and _time(lesson['approved_at']) <= cutoff
                    and _time(lesson['created_at']) <= cutoff):
                # Only the contract's de-identified lesson fields cross this boundary.
                lessons.append({key: deepcopy(lesson[key]) for key in (
                    'id', 'source_disaster_id', 'source_run_id', 'source_outcome_ids',
                    'summary', 'conditions', 'recommendation', 'approved',
                    'approved_at', 'created_at')})
    return {'report': case['report'], 'organizations': deepcopy(case['organizations']),
                'conditions': deepcopy(case.get('conditions', [])), 'lessons': lessons,
                'verification': deepcopy(case.get('verification', {})),
                'as_of': case['as_of'], 'run_id': run_id, 'disaster_id': case['disaster_id']}


def _score(case, inputs, decision, lessons_enabled):
    expected = case['expected']
    available = {lesson['id'] for lesson in inputs['lessons']}
    cited = set(decision.get('lesson_ids', []))
    relevant = set(expected['relevant_lesson_ids'])
    evidence = set(inputs['verification'].get('evidence_ids', []))
    resolved = decision.get('status') == 'resolved'
    receipt = inputs['verification'].get('received') is True and bool(evidence)
    grounded = (set(decision.get('evidence_ids', [])) <= evidence
                and cited <= available and (not resolved or receipt))
    return {
        'category_extraction': float(set(decision.get('categories', [])) == set(expected['categories'])),
        'organization_compatibility': float(decision.get('organization_id') in expected['valid_organization_ids']),
        'false_closure': float(resolved and expected['received'] is not True),
        'groundedness': float(grounded),
        'relevant_lesson_use': (float(bool(cited & relevant) and cited <= relevant)
                                if lessons_enabled and relevant else None),
    }


def run_comparison(cases: list[dict], decide) -> dict:
    """Compare one decision callable/settings with only historical context changed.

    Metrics are deterministic checks on synthetic labels, not semantic LLM judging.
    ``false_closure`` is an error rate (lower is better); other values are pass rates.
    Absent relevant-lesson opportunities produce null, never an invented score.
    ``decide`` must be side-effect free; variant run IDs cannot mutate the live demo.
    """
    experiment_id = f'recovery-{uuid4().hex}'
    result = {'experiment_id': experiment_id, 'case_count': len(cases),
                  'measured_at': datetime.now(timezone.utc).isoformat(), 'trace_url': None,
                  'measurement_type': 'synthetic_deterministic',
                  'limitations': ['Small synthetic held-out set; no real-world accuracy claim.',
                               'Groundedness checks citation membership and receipt evidence only.']}
    for variant in ('without_history', 'with_history'):
        enabled = variant == 'with_history'
        scores = []
        for case in cases:
            inputs = _decision_input(case, f'{experiment_id}-{variant}', enabled)
            # Retain an independent scoring copy: a callable cannot mutate its evidence.
            decision = decide(deepcopy(inputs), lessons_enabled=enabled)
            scores.append(_score(case, inputs, decision, enabled))
        metrics = {}
        for name in ('category_extraction', 'organization_compatibility', 'false_closure',
                     'groundedness', 'relevant_lesson_use'):
            measured = [score[name] for score in scores if score[name] is not None]
            metrics[name] = sum(measured) / len(measured) if measured else None
        result[variant] = metrics
    return result
