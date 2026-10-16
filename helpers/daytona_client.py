"""Sandbox clients for AI helpers. Payloads are de-identified; contact fields are refused here."""
import json
import os
import re
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from helpers.roles import script_source

FORBIDDEN_KEYS = {'phone', 'phone_number', 'email', 'address', 'display_name', 'name', 'contact'}
_EMAIL = re.compile(r'[\w.+-]+@[\w-]+\.[\w.-]+')
# Strict phone shapes only, so timestamps and UUIDs are never flagged.
_PHONE = re.compile(r'\+\d[\d ().-]{8,}\d|\(\d{3}\)\s?\d{3}-\d{4}|\b\d{3}[-.]\d{3}[-.]\d{4}\b')


def assert_no_contact(value, _key=None):
    """Refuse survivor contact fields. Only the code-owned disclosure may hold Relay's own number."""
    if isinstance(value, dict):
        for key, item in value.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise ValueError(f'payload may not contain {key}')
            assert_no_contact(item, key)
    elif isinstance(value, list):
        for item in value:
            assert_no_contact(item, _key)
    elif isinstance(value, str) and _key != 'disclosure' and (_EMAIL.search(value) or _PHONE.search(value)):
        raise ValueError('payload may not contain contact details')


def build_code(role, payload):
    assert_no_contact(payload)
    return ('import json\nPAYLOAD = json.loads(' + json.dumps(json.dumps(payload)) + ')\n'
            + script_source(role))


def daytona_status(env=None):
    """No network: only whether a key is present."""
    env = os.environ if env is None else env
    configured = bool((env.get('DAYTONA_API_KEY') or '').strip())
    return {'configured': configured, 'provider': 'daytona' if configured else 'local'}


class LocalSandboxClient:
    """Subprocess in a throwaway temp dir. Not isolation: an offline stand-in, labelled local."""
    provider = 'local'

    def run(self, role, payload, timeout=20):
        code = build_code(role, payload)
        with tempfile.TemporaryDirectory(prefix='relay-helper-') as tmp:
            script = Path(tmp) / 'helper.py'
            script.write_text(code)
            done = subprocess.run([sys.executable, '-I', str(script)], cwd=tmp, capture_output=True,
                                  text=True, timeout=timeout, env={}, check=False)
            return {'stdout': done.stdout, 'exit_code': done.returncode,
                    'sandbox_id': 'local-' + Path(tmp).name}


class DaytonaSandboxClient:
    """Real Daytona SDK: one fresh sandbox per run, always deleted."""
    provider = 'daytona'

    def __init__(self, daytona=None, max_concurrency=None):
        self._daytona = daytona
        limit = max_concurrency or int(os.environ.get('DAYTONA_MAX_SANDBOXES') or 3)
        self._slots = threading.BoundedSemaphore(limit)

    def _client(self):
        if self._daytona is None:
            from daytona import Daytona  # lazy: offline installs do not need the SDK
            self._daytona = Daytona()  # reads DAYTONA_API_KEY / DAYTONA_API_URL / DAYTONA_TARGET
        return self._daytona

    def _params(self, role):
        try:
            from daytona import CreateSandboxFromSnapshotParams
        except ImportError:  # injected fake client in offline tests
            return None
        return CreateSandboxFromSnapshotParams(language='python', labels={'app': 'relay-helper', 'role': role})

    def run(self, role, payload, timeout=20):
        code = build_code(role, payload)
        if not self._slots.acquire(timeout=timeout):
            raise TimeoutError('too many helper sandboxes running')
        sandbox = None
        try:
            daytona = self._client()
            sandbox = daytona.create(self._params(role), timeout=timeout)
            response = sandbox.process.code_run(code, timeout=int(timeout))
            return {'stdout': response.result or '', 'exit_code': response.exit_code,
                    'sandbox_id': sandbox.id}
        finally:
            try:
                if sandbox is not None:
                    self._client().delete(sandbox)
            finally:
                self._slots.release()


def default_client(env=None):
    env = os.environ if env is None else env
    return DaytonaSandboxClient() if daytona_status(env)['configured'] else LocalSandboxClient()
