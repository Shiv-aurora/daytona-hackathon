"""Local HTTP server for the live voice demo (stdlib only). Run it behind the ngrok domain:

    RELAY_ENV_FILE=.env python -m calls.voice.server      # port 8013
    ngrok http 8013 --url=$NGROK_DOMAIN

Routes: GET / (browser page), GET /api/demo/next, POST /api/session (claim; signed URL in voice mode),
POST /api/session/<id>/turn (typed fallback turn), POST /api/session/<id>/end,
POST /v1/chat/completions (ElevenLabs Custom LLM, bearer RELAY_LLM_SECRET).
Demo settings (read after RELAY_ENV_FILE loads): RELAY_DEMO_CALLS (default 20), RELAY_DEMO_LANGUAGE (en|zh).
"""

from __future__ import annotations

import json
import os
import pathlib
import urllib.parse
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from calls.agent import CallAgent
from calls.voice.bridge import VoiceBridge

PAGE = pathlib.Path(__file__).with_name("page.html")
ELEVENLABS_API = "https://api.elevenlabs.io/v1"
# Voice needs about 1s replies; W1's runtime model is left alone (measured: Sonnet 2-5s, Haiku ~1s).
VOICE_MODEL = "anthropic/claude-haiku-4.5"


def make_handler(bridge: VoiceBridge, next_demo=lambda: None) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _json(self, status: int, payload: dict) -> None:
            body = json.dumps(payload, default=str).encode()
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _body(self) -> dict:
            length = int(self.headers.get("Content-Length") or 0)
            try:
                return json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                return {}

        def do_GET(self) -> None:
            if self.path == "/api/demo/next":
                request = next_demo()
                return self._json(200, {"request": request}) if request else self._json(404, {
                    "error": "all demo requests used; restart the demo server"})
            if self.path not in ("/", "/index.html"):
                return self._json(404, {"error": "not found"})
            body = PAGE.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            path = urllib.parse.urlparse(self.path).path
            if path == "/api/session":
                body = self._body()
                return self._json(*bridge.open_session(body.get("request") or {}, voice=body.get("mode") != "text"))
            if path.startswith("/api/session/") and path.endswith("/turn"):
                return self._json(*bridge.text_turn(path.split("/")[3], str(self._body().get("text") or "")))
            if path.startswith("/api/session/") and path.endswith("/end"):
                # The browser can only report an error (downgrade to failed), never claim contact.
                result = bridge.end_session(path.split("/")[3], "failed" if self._body().get("error") else None)
                return self._json(200, {"result": result})
            if path.rstrip("/").endswith("/chat/completions"):
                status, payload = bridge.chat_completion(self._body(), self.headers.get("Authorization", ""))
                if isinstance(payload, dict):
                    return self._json(status, payload)
                self.send_response(status)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.end_headers()
                for line in payload:
                    self.wfile.write(line.encode())
                    self.wfile.flush()
                return None
            return self._json(404, {"error": "not found"})

        def log_message(self, format: str, *args: object) -> None:  # keep secrets out of logs
            print(f"{self.command} {urllib.parse.urlparse(self.path).path} -> {args[1] if len(args) > 1 else ''}")

    return Handler


def signed_url_fetcher(api_key: str):
    """Signed URL for the agent of the call's language; no agent for it means the text fallback."""
    from calls.voice.setup_agent import agent_env_var

    def fetch(language: str) -> str:
        agent_id = os.environ.get(agent_env_var(language))
        if not agent_id:
            raise LookupError(f"no ElevenLabs agent configured for language {language!r}")
        query = urllib.parse.urlencode({"agent_id": agent_id})
        request = urllib.request.Request(f"{ELEVENLABS_API}/convai/conversation/get-signed-url?{query}",
                                         headers={"xi-api-key": api_key})
        with urllib.request.urlopen(request, timeout=15) as response:
            return json.load(response)["signed_url"]
    return fetch


def load_env_file(path: str | None) -> None:
    """Minimal KEY=VALUE loader for this project's explicitly selected env file."""
    if not path:
        return
    for line in pathlib.Path(os.path.expanduser(path)).read_text().splitlines():
        key, sep, value = line.partition("=")
        if sep and key.strip() and not key.lstrip().startswith("#"):
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def demo_requests(count: int) -> list[dict]:
    """The only requests the demo server will ever place, all queued explicitly at startup. Each can be
    dialed once; the page picks the next unused one, so every "Start call" is a fresh request."""
    return [{"_id": f"callreq-demo-{n}", "run_id": "demo-run", "scenario_id": "s1", "household_id": "hh-chen",
             "proposal_id": f"prop-demo-{n}", "purpose": "promise_check_in", "requested_ts": 504.0}
            for n in range(1, count + 1)]


def demo_backend(requests: list[dict] | None = None, language: str = "en"):
    """In-memory backend seeded with the Mrs. Chen demo household for offline voice development."""
    from calls.fakes import InMemoryBackend, InMemoryLedger

    backend = InMemoryBackend(
        registry={"hh-chen": {"household_id": "hh-chen", "opt_in": True, "language": language,
                              "first_name": "Mei"}},
        households={("demo-run", "hh-chen"): {
            "first_name": "Mei", "language": language,
            "open_promises": [{"text": "Her son Wei is coming Tuesday to help clean out the basement.",
                               "made_ts": 42.6, "due_ts": 150.0}],
            "recent_calls": [{"ts": 144.0, "outcome": "no_answer", "answered": False}],
            "outage_status": "Con Ed pushed block restoration to day 12 or later"}})
    ledger = InMemoryLedger()
    for request in requests or demo_requests(2):  # explicit queue, like W1 -> W2 schedule_call
        ledger.queue(request)
    return backend, ledger


class LoggingResponder:
    """Prints each time the responder (model) is called, so a smoke test can prove what reached it."""

    def __init__(self, inner):
        self.inner = inner

    def reply(self, context: dict, transcript: list[dict]):
        print(f"responder called with resident turn: {transcript[-1]['text']!r}", flush=True)
        return self.inner.reply(context, transcript)


def main() -> None:
    load_env_file(os.environ.get("RELAY_ENV_FILE"))
    from calls.fakes import FakeTransport
    from calls.responders import ModelResponder, ScriptedResponder
    from runtime.llm import OpenRouterClient

    api_key = os.environ.get("OPENROUTER_API_KEY")
    llm = OpenRouterClient(api_key, model=os.environ.get("RELAY_VOICE_MODEL") or VOICE_MODEL) if api_key else None
    responder = LoggingResponder(ModelResponder(llm) if llm else ScriptedResponder())
    requests = demo_requests(int(os.environ.get("RELAY_DEMO_CALLS") or 20))  # read after the env file
    language = os.environ.get("RELAY_DEMO_LANGUAGE") or "en"
    backend, ledger = demo_backend(requests, language)
    agent = CallAgent(backend, FakeTransport([]), responder, os.environ["RELAY_CALLBACK_NUMBER"], ledger)
    bridge = VoiceBridge(agent, os.environ.get("RELAY_LLM_SECRET", ""),
                         signed_url_fetcher(os.environ.get("ELEVENLABS_API_KEY", "")),
                         log=lambda line: print(line, flush=True))
    port = int(os.environ.get("RELAY_VOICE_PORT", "8013"))
    print(f"Relay voice bridge on http://localhost:{port} (responder: {type(responder.inner).__name__}"
          f"{' / ' + llm.model if llm else ''}; "
          f"{len(requests)} demo requests queued; demo language {language})", flush=True)

    def next_demo() -> dict | None:
        return next((r for r in requests if ledger.status.get(r["_id"]) == "queued"), None)

    ThreadingHTTPServer(("127.0.0.1", port), make_handler(bridge, next_demo)).serve_forever()


if __name__ == "__main__":
    main()
