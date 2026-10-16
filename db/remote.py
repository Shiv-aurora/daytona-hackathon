"""Choose embedded vs remote SurrealDB from SURREAL_* settings; remote status probe.

Blank SURREAL_URL (or mem://, file://, surrealkv://) keeps the embedded store. A ws(s)/http(s)
URL selects a remote server such as SurrealDB Cloud. Errors never include credentials.
"""

from __future__ import annotations

import os
import socket
import time
from collections.abc import Mapping
from contextlib import suppress
from urllib.parse import urlparse

REMOTE_SCHEMES = {"ws", "wss", "http", "https"}
EMBEDDED_SCHEMES = {"mem", "memory", "file", "surrealkv"}
DEFAULT_EMBEDDED_URL = "surrealkv://.relay-demo"


class RemoteError(RuntimeError):
    """Connection/auth failure with a secret-free message."""


def surreal_env(env: Mapping[str, str] | None = None, dotenv=".env") -> dict[str, str]:
    from db.config import read_dotenv

    return {**(read_dotenv(dotenv) if dotenv else {}), **(os.environ if env is None else env)}


def mode_for(url: str) -> str:
    return "remote" if urlparse((url or "").strip()).scheme in REMOTE_SCHEMES else "embedded"


def _clean(value: str | None) -> str | None:
    return (value or "").strip() or None


def open_db(endpoint, namespace, database, username=None, password=None, *, remote=False):
    """Connect, authenticate, select namespace/database. Returns a connected blocking client."""
    from surrealdb import Surreal

    db = Surreal(endpoint)
    try:
        db.connect()
    except Exception as exc:  # noqa: BLE001
        raise RemoteError(f"Cannot connect to SurrealDB ({type(exc).__name__})") from None
    if username is not None:
        if not remote:
            db.signin({"username": username, "password": password})
        else:
            _signin_remote(db, namespace, database, username, password)
    try:
        db.use(namespace, database)
    except Exception as exc:  # noqa: BLE001
        raise RemoteError(f"Cannot select namespace/database ({type(exc).__name__})") from None
    return db


def _signin_remote(db, namespace, database, username, password):
    # SurrealDB users exist at root, namespace or database level; try widest scope first.
    base = {"username": username, "password": password}
    attempts = (base, {**base, "namespace": namespace},
                {**base, "namespace": namespace, "database": database})
    for creds in attempts:
        # Try the next scope on failure; never echo the server's error text.
        with suppress(Exception):
            db.signin(creds)
            return
    raise RemoteError("SurrealDB sign-in failed at root, namespace and database level; "
                      "check SURREAL_USERNAME/SURREAL_PASSWORD")


_PROBE = {"at": 0.0, "key": None, "ok": None}


def surreal_status(env: Mapping[str, str] | None = None, *, ttl: float = 10.0, timeout: float = 2.0,
                   dotenv=".env") -> dict:
    """{"configured", "mode", "reachable"}; reachable is None unless remote (TCP check, cached)."""
    url = (surreal_env(env, dotenv).get("SURREAL_URL") or "").strip()
    mode = mode_for(url)
    status = {"configured": bool(url), "mode": mode, "reachable": None}
    if mode == "remote":
        parsed = urlparse(url)
        port = parsed.port or (443 if parsed.scheme in {"wss", "https"} else 80)
        key = (parsed.hostname, port)
        now = time.monotonic()
        if _PROBE["key"] != key or now - _PROBE["at"] > ttl:
            try:
                socket.create_connection(key, timeout=timeout).close()
                ok = True
            except OSError:
                ok = False
            _PROBE.update(at=now, key=key, ok=ok)
        status["reachable"] = _PROBE["ok"]
    return status
