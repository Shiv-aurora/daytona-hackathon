"""HTTP server for the Relay run API: `python -m api.server [--host 127.0.0.1] [--port 8787]`.

Standard library only. Uses the seeded in-process reference store. JSON everywhere; CORS for the console's origin (RELAY_API_ORIGIN, default "*").
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from api.relay import handle


def make_handler(db: Any, origin: str = "*", recovery_store=None) -> type[BaseHTTPRequestHandler]:
    class RelayHandler(BaseHTTPRequestHandler):
        def do_OPTIONS(self) -> None:  # CORS preflight for the console's JSON POSTs
            self._send(204, None)

        def do_GET(self) -> None:
            self._route("GET", None)

        def do_POST(self) -> None:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            try:
                body = json.loads(raw) if raw else {}
            except ValueError:
                body = None
            if not isinstance(body, dict):
                self._send(400, {"error": "the body must be a JSON object"})
                return
            self._route("POST", body)

        def _route(self, method: str, body: dict | None) -> None:
            try:
                from api.recovery import handle as recovery_handle
                if recovery_store is not None:
                    status, payload = recovery_handle(recovery_store, method, self.path, body)
                    if status == 404 and payload == {"error": "not found"}:
                        status, payload = handle(db, method, self.path, body)
                else:
                    status, payload = handle(db, method, self.path, body)
            except Exception as exc:  # noqa: BLE001 - never leak internals to the browser
                print(f"relay api: {method} {self.path} failed: {type(exc).__name__}", file=sys.stderr)
                status, payload = 500, {"error": "internal error"}
            self._send(status, payload)

        def _send(self, status: int, payload: dict | None) -> None:
            data = b"" if payload is None else json.dumps(payload, default=str).encode()
            self.send_response(status)
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return RelayHandler


def main(argv: list[str] | None = None) -> None:
    from db.fakes import FakeDatabase
    from runtime.demo import DemoBackend
    from runtime.scenario import load_scenario

    parser = argparse.ArgumentParser(description="Relay run API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    parser.add_argument("--store", choices=("memory", "surreal"), default="memory")
    parser.add_argument("--seed", default="data/demo/seed.json")
    args = parser.parse_args(argv)
    with open(args.seed) as stream:
        seed = json.load(stream)
    if args.store == "memory":
        from api.demo_store import InMemoryRecoveryStore
        recovery_store = InMemoryRecoveryStore(seed)
    else:
        from db.recovery import SurrealRecoveryStore
        recovery_store = SurrealRecoveryStore.from_env(seed=seed)
    db = FakeDatabase()
    DemoBackend(db, "relay-demo", load_scenario("data/scenarios/s1"))
    server = ThreadingHTTPServer((args.host, args.port),
                                 make_handler(db, os.environ.get("RELAY_API_ORIGIN", "*"), recovery_store))
    print(f"Relay run API on http://{args.host}:{args.port} (in-process reference data)")
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if hasattr(recovery_store, "close"):
            recovery_store.close()


if __name__ == "__main__":
    main()
