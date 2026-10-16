"""Live ElevenLabs checker for the owner: `make check-elevenlabs` (or add `STT=file.wav`).

Reads .env (or RELAY_ENV_FILE). Verifies the key, the agent id, signed-URL creation and, only with
`--stt <file>`, Scribe. Never places a call and never prints secrets. Exit 0 only if every step passes.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from calls.elevenlabs import ElevenLabsClient, ElevenLabsError


def load_env(path: str) -> None:
    file = Path(path)
    if not file.is_file():
        return
    for line in file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            key, _, value = line.partition('=')
            os.environ.setdefault(key.strip(), value.strip().strip('"\''))


def step(name: str, action) -> bool:
    try:
        detail = action()
    except ElevenLabsError as exc:
        print(f'FAIL  {name}: {exc}')
        return False
    except Exception as exc:  # noqa: BLE001 - report the type only, never a message that could hold a secret
        print(f'FAIL  {name}: {type(exc).__name__}')
        return False
    print(f'PASS  {name}' + (f' ({detail})' if detail else ''))
    return True


def main(argv: list[str], client_factory=ElevenLabsClient.from_env) -> int:
    load_env(os.environ.get('RELAY_ENV_FILE', '.env'))
    stt_file = argv[argv.index('--stt') + 1] if '--stt' in argv and argv.index('--stt') + 1 < len(argv) else None
    client = client_factory()
    if client is None:
        print('FAIL  ELEVENLABS_API_KEY is blank (set it in .env)')
        return 1
    results = [step('api key valid (GET /user/subscription)',
                    lambda: 'tier ' + str(client.subscription().get('tier', 'unknown')))]
    if not client.agent_id:
        print('FAIL  ELEVENLABS_AGENT_ID is blank (see calls/LIVE.md)')
        results.append(False)
    else:
        results.append(step('agent exists (GET /convai/agents/<id>)',
                            lambda: 'name ' + str(client.get_agent().get('name', '?'))))

        def signed():
            result = client.signed_url()
            return 'conversation_id returned' if result.get('conversation_id') else \
                'WARNING: no conversation_id; webhooks cannot map to sessions'
        results.append(step('signed URL creation', signed))
    if not os.environ.get('ELEVENLABS_WEBHOOK_SECRET'):
        print('WARN  ELEVENLABS_WEBHOOK_SECRET is blank: POST /webhooks/elevenlabs will answer 503')
    if stt_file:
        def stt():
            data = Path(stt_file).read_bytes()
            result = client.transcribe(data, Path(stt_file).name)
            return f'{len(result["segments"])} segments, {len(result["text"])} chars'
        results.append(step('Scribe speech-to-text on ' + Path(stt_file).name, stt))
    else:
        print('SKIP  Scribe speech-to-text (pass --stt <audio file>)')
    print('ALL PASS' if all(results) else 'SOME STEPS FAILED')
    return 0 if all(results) else 1


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
