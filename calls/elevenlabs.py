"""Tiny ElevenLabs HTTP client (stdlib only): signed URLs, agent lookup, Scribe speech-to-text.

Errors never carry the API key, request headers, or response bodies. No call is ever placed here.
`transport` is injectable (method, url, headers, body, timeout) -> (status, bytes) so tests use fakes.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid

API = 'https://api.elevenlabs.io/v1'
TIMEOUT = 20
STT_TIMEOUT = 120
STT_MODEL = 'scribe_v1'


class ElevenLabsError(RuntimeError):
    """Secret-free provider failure. `status` is the HTTP status, or None for network errors."""
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def elevenlabs_status(env=None) -> dict:
    """Configuration presence only; never touches the network."""
    env = os.environ if env is None else env
    return {'configured': bool((env.get('ELEVENLABS_API_KEY') or '').strip()),
            'agent_configured': bool((env.get('ELEVENLABS_AGENT_ID') or '').strip())}


def _urllib_transport(method, url, headers, body, timeout):
    request = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, b''  # never surface the provider's body
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise ElevenLabsError(f'network error: {type(exc).__name__}') from None


def multipart(fields: dict, file_field: str, filename: str, content_type: str, data: bytes):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
    parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
                  f'filename="{filename}"\r\nContent-Type: {content_type}\r\n\r\n').encode())
    parts.extend([data, f'\r\n--{boundary}--\r\n'.encode()])
    return b''.join(parts), f'multipart/form-data; boundary={boundary}'


def segments_from_words(words: list) -> list[dict]:
    """Group consecutive same-speaker words into {speaker,start,end,text} segments."""
    segments = []
    for word in words or []:
        if word.get('type', 'word') == 'audio_event':
            continue
        speaker = str(word.get('speaker_id') or 'speaker_0')
        text = word.get('text', '')
        if segments and segments[-1]['speaker'] == speaker:
            segments[-1]['text'] += text
            if word.get('end') is not None:
                segments[-1]['end'] = word['end']
        elif text.strip():
            segments.append({'speaker': speaker, 'start': word.get('start'), 'end': word.get('end'),
                             'text': text})
    for segment in segments:
        segment['text'] = segment['text'].strip()
    return [s for s in segments if s['text']]


class ElevenLabsClient:
    def __init__(self, api_key: str, agent_id: str = '', transport=_urllib_transport):
        if not api_key:
            raise ValueError('ELEVENLABS_API_KEY required')
        self._key, self.agent_id, self._transport = api_key, agent_id, transport

    @classmethod
    def from_env(cls, env=None, transport=_urllib_transport):
        env = os.environ if env is None else env
        key = (env.get('ELEVENLABS_API_KEY') or '').strip()
        return cls(key, (env.get('ELEVENLABS_AGENT_ID') or '').strip(), transport) if key else None

    def _request(self, method, path, body=None, content_type='application/json', timeout=TIMEOUT):
        headers = {'xi-api-key': self._key, 'Accept': 'application/json'}
        if body is not None:
            headers['Content-Type'] = content_type
        status, raw = self._transport(method, API + path, headers, body, timeout)
        if status >= 400:
            raise ElevenLabsError(f'ElevenLabs request failed (HTTP {status})', status)
        try:
            return json.loads(raw or b'{}')
        except ValueError:
            raise ElevenLabsError('ElevenLabs returned a non-JSON response', status) from None

    def subscription(self) -> dict:
        return self._request('GET', '/user/subscription')

    def get_agent(self, agent_id: str | None = None) -> dict:
        return self._request('GET', '/convai/agents/' + urllib.parse.quote(agent_id or self.agent_id, safe=''))

    def signed_url(self, agent_id: str | None = None) -> dict:
        """Returns {'signed_url': str, 'conversation_id': str|None}. The URL is short-lived."""
        agent = agent_id or self.agent_id
        if not agent:
            raise ElevenLabsError('ELEVENLABS_AGENT_ID is not configured')
        query = urllib.parse.urlencode({'agent_id': agent, 'include_conversation_id': 'true'})
        result = self._request('GET', '/convai/conversation/get-signed-url?' + query)
        if not isinstance(result.get('signed_url'), str):
            raise ElevenLabsError('ElevenLabs returned no signed_url')
        return {'signed_url': result['signed_url'], 'conversation_id': result.get('conversation_id')}

    def transcribe(self, audio: bytes, filename: str = 'audio', content_type: str = 'application/octet-stream') -> dict:
        body, ctype = multipart({'model_id': STT_MODEL, 'diarize': 'true', 'timestamps_granularity': 'word'},
                                'file', filename, content_type, audio)
        result = self._request('POST', '/speech-to-text', body, ctype, STT_TIMEOUT)
        return {'provider': 'elevenlabs', 'model': STT_MODEL, 'language': result.get('language_code'),
                'text': (result.get('text') or '').strip(), 'segments': segments_from_words(result.get('words'))}


def fake_transcribe(audio: bytes, filename: str = 'audio') -> dict:
    """Offline stand-in used only when no API key exists. Transcribes nothing; clearly labelled."""
    text = '[offline fake transcript: no audio was transcribed]'
    return {'provider': 'fake', 'live': False, 'model': None, 'language': None, 'text': text,
            'segments': [{'speaker': 'speaker_0', 'start': 0.0, 'end': 0.0, 'text': text}],
            'note': f'ELEVENLABS_API_KEY is blank; received {len(audio)} bytes but did not send them anywhere.'}
