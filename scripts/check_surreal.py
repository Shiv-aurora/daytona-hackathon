"""Live SurrealDB checker: `make check-surreal`. Reads .env, prints PASS/FAIL per step, exit 0/1.

Uses a throwaway table (relay_probe) and never prints credentials. Embedded when SURREAL_URL is blank.
"""

from __future__ import annotations

import sys
import uuid
from contextlib import suppress
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from db.remote import (
    DEFAULT_EMBEDDED_URL,
    RemoteError,
    mode_for,
    open_db,
    surreal_env,
)


def _redact(text: str, secrets) -> str:
    for secret in filter(None, secrets):
        text = text.replace(secret, "***")
    return text[:200]


def run(env=None, dotenv=".env", out=print) -> int:
    cfg = surreal_env(env, dotenv)
    url = (cfg.get("SURREAL_URL") or "").strip() or DEFAULT_EMBEDDED_URL
    ns = (cfg.get("SURREAL_NAMESPACE") or "relay").strip()
    name = (cfg.get("SURREAL_DATABASE") or "relay").strip()
    user = (cfg.get("SURREAL_USERNAME") or "").strip() or None
    password = cfg.get("SURREAL_PASSWORD") or None
    secrets = (password, user)
    remote = mode_for(url) == "remote"
    ok = True
    state = {}

    def step(label, fn):
        nonlocal ok
        if not ok:
            out(f"SKIP {label}")
            return
        try:
            detail = fn()
            out(f"PASS {label}" + (f" ({detail})" if detail else ""))
        except Exception as exc:  # noqa: BLE001
            ok = False
            out(f"FAIL {label}: {type(exc).__name__}: {_redact(str(exc), secrets)}")

    def check_config():
        if remote and not (user and password):
            raise RemoteError("remote SURREAL_URL needs SURREAL_USERNAME and SURREAL_PASSWORD")
        return f"mode={'remote' if remote else 'embedded'} ns={ns} db={name}"

    def connect():
        state["db"] = open_db(url, ns, name, user, password, remote=remote)

    def schema():
        text = (Path(__file__).resolve().parents[1] / "db" / "recovery_schema.surql").read_text()
        state["db"].query(text)
        state["db"].query(text)  # second apply proves idempotency
        return "applied twice"

    probe = {"id": "probe-" + uuid.uuid4().hex[:8], "run_id": "probe-run", "disaster_id": "probe-disaster"}

    def write():
        state["db"].query("CREATE relay_probe SET pid=$id, run_id=$run_id, disaster_id=$disaster_id;", probe)

    def read():
        rows = state["db"].query(
            "SELECT * FROM relay_probe WHERE pid=$id AND run_id=$run_id AND disaster_id=$disaster_id;", probe)
        if len(rows) != 1:
            raise RuntimeError(f"expected 1 scoped probe row, got {len(rows)}")
        other = state["db"].query("SELECT * FROM relay_probe WHERE pid=$id AND run_id='other-run';", probe)
        if other:
            raise RuntimeError("probe visible under a different run_id")
        return "scoped"

    def delete():
        state["db"].query("DELETE relay_probe WHERE pid=$id;", probe)
        if state["db"].query("SELECT * FROM relay_probe WHERE pid=$id;", probe):
            raise RuntimeError("probe row still present")

    step("config", check_config)
    step("connect + sign in + use namespace/database", connect)
    step("apply schema (idempotent)", schema)
    step("write scoped probe record", write)
    step("read scoped probe record", read)
    step("delete probe record", delete)
    if "db" in state:
        with suppress(Exception):
            state["db"].query("REMOVE TABLE IF EXISTS relay_probe;")
            state["db"].close()
    out("RESULT: PASS" if ok else "RESULT: FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(run())
