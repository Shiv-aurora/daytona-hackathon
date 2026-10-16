import re

from calls.agent_prompt import (
    DYNAMIC_VARIABLES,
    OUTCOME_LABELS,
    REQUIRED_RULES,
    SYSTEM_PROMPT,
)
from calls.safety import EMERGENCY_LINES


def test_prompt_has_every_safety_rule():
    for rule in REQUIRED_RULES:
        assert rule in SYSTEM_PROMPT, rule
    assert EMERGENCY_LINES['en'] in SYSTEM_PROMPT


def test_prompt_has_labels_variables_and_end_call():
    for label in OUTCOME_LABELS:
        assert label in SYSTEM_PROMPT
    for name in DYNAMIC_VARIABLES:
        assert '{{' + name + '}}' in SYSTEM_PROMPT
    assert set(re.findall(r'\{\{(\w+)\}\}', SYSTEM_PROMPT)) <= set(DYNAMIC_VARIABLES)
    assert 'end_call' in SYSTEM_PROMPT


def test_prompt_matches_workforce_doc():
    from pathlib import Path
    doc = (Path(__file__).resolve().parents[1] / 'AGENT_WORKFORCE.md').read_text()
    assert SYSTEM_PROMPT.strip() in doc
