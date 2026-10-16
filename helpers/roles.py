"""Provisional helper roles, kept as data. Each role runs one stdlib-only script in a sandbox."""
from pathlib import Path

SCRIPTS = Path(__file__).with_name('scripts')

# needs_request: the role works on one request; otherwise on the whole run summary.
ROLES = [
    {'role': 'intake', 'script': 'intake.py', 'needs_request': False},
    {'role': 'triage', 'script': 'triage.py', 'needs_request': False},
    {'role': 'matcher', 'script': 'matcher.py', 'needs_request': True},
    {'role': 'follow_up', 'script': 'follow_up.py', 'needs_request': True},
    {'role': 'verifier', 'script': 'verifier.py', 'needs_request': True},
]
BY_ROLE = {r['role']: r for r in ROLES}


def script_source(role):
    return (SCRIPTS / BY_ROLE[role]['script']).read_text()
