"""The owner's live checker, exercised against a fake transport: no network, never dials."""
import importlib.util
import json
from pathlib import Path

from calls.elevenlabs import ElevenLabsClient

spec = importlib.util.spec_from_file_location(
    'check_elevenlabs', Path(__file__).resolve().parents[1] / 'scripts/check_elevenlabs.py')
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


def factory(failing=()):
    seen = []

    def transport(method, url, headers, body, timeout):
        seen.append((method, url))
        if any(part in url for part in failing):
            return 404, b''
        if 'get-signed-url' in url:
            return 200, json.dumps({'signed_url': 'wss://x', 'conversation_id': 'c'}).encode()
        if 'speech-to-text' in url:
            return 200, json.dumps({'text': 'hi', 'words': [{'text': 'hi', 'start': 0, 'end': 1}]}).encode()
        return 200, b'{"tier":"free","name":"agent"}'
    return (lambda: ElevenLabsClient('sk-secret', 'agent-1', transport)), seen


def test_all_steps_pass_without_calls_or_secrets(capsys, tmp_path):
    make, seen = factory()
    audio = tmp_path / 'a.wav'
    audio.write_bytes(b'RIFF')
    assert checker.main(['--stt', str(audio)], make) == 0
    out = capsys.readouterr().out
    assert 'ALL PASS' in out and 'sk-secret' not in out
    assert not any('/convai/conversations' in url or 'outbound' in url for _, url in seen)


def test_failing_agent_exits_nonzero(capsys):
    make, _ = factory(failing=('/convai/agents/',))
    assert checker.main([], make) == 1
    assert 'FAIL  agent exists' in capsys.readouterr().out


def test_blank_key_fails(capsys):
    assert checker.main([], lambda: None) == 1
