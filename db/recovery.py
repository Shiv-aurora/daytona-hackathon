"""SurrealDB persistence for the small Relay demo.

Each run is a versioned aggregate. A conditional UPDATE atomically commits the
transition, verification, event and payload-sensitive replay ledger together.
Business rules are shared with the reference store rather than reimplemented.
"""

from __future__ import annotations

import argparse
import fcntl
import json
from contextlib import suppress
from copy import deepcopy
from datetime import UTC, datetime
from pathlib import Path
from threading import RLock
from urllib.parse import urlparse

from contracts.demo import Conflict, InvalidInput, NotFound

OPERATIONAL = (
    "survivors",
    "requests",
    "calls",
    "verifications",
    "evaluations",
    "system_events",
)


def _engine():
    from api.demo_store import InMemoryRecoveryStore

    return InMemoryRecoveryStore


class SurrealRecoveryStore:
    """Embedded SurrealDB (default) or, with allow_remote, a remote ws(s)/http(s) server.

    Remote differences handled: no file lock (optimistic revisions arbitrate writers), scoped
    sign-in (root/namespace/database user), one reconnect+retry on a dropped connection, and a
    seed race between processes (loser re-reads the winner's seed).
    """

    def __init__(
        self,
        endpoint="mem://",
        namespace="relay",
        database="demo",
        *,
        seed=None,
        username=None,
        password=None,
        allow_remote=False,
    ):
        from db.remote import REMOTE_SCHEMES, open_db

        parsed = urlparse(endpoint)
        scheme = parsed.scheme
        self._remote = bool(allow_remote) and scheme in REMOTE_SCHEMES
        if not self._remote:
            if scheme not in {"mem", "memory", "file", "surrealkv", "ws", "http"}:
                raise InvalidInput("Use a fresh local SurrealDB endpoint")
            if scheme in {"ws", "http"} and parsed.hostname not in {
                "localhost",
                "127.0.0.1",
                "::1",
            }:
                raise InvalidInput("Only a local SurrealDB server is allowed")
        self._lock = RLock()
        self._file_lock = None
        # Embedded engines must not open the same file from separate connections:
        # the SDK does not coordinate those independent cached views.
        if scheme in {"file", "surrealkv"}:
            raw_path = endpoint.split("://", 1)[1]
            db_path = Path(raw_path).expanduser().resolve()
            db_path.parent.mkdir(parents=True, exist_ok=True)
            lock_path = db_path.with_name(db_path.name + ".relay-lock")
            self._file_lock = lock_path.open("a")
            try:
                fcntl.flock(self._file_lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                self._file_lock.close()
                raise Conflict(
                    "Local database already open; use the running API process"
                ) from None
        self._conn = (endpoint, namespace, database, username, password)
        self._db = open_db(*self._conn, remote=self._remote)
        self._q(Path(__file__).with_name("recovery_schema.surql").read_text())
        if seed is not None:
            self.seed(seed)

    def _q(self, sql, params=None):
        try:
            return self._db.query(sql) if params is None else self._db.query(sql, params)
        except (OSError, ConnectionError, TimeoutError):
            if not self._remote:
                raise
        except Exception as exc:
            if not self._remote or "Connection" not in type(exc).__name__:
                raise
        # Remote connection dropped: reconnect once. Writes are revision-checked or
        # transactional, so replaying the statement is safe.
        from db.remote import open_db

        with suppress(Exception):
            self._db.close()
        self._db = open_db(*self._conn, remote=True)
        return self._db.query(sql) if params is None else self._db.query(sql, params)

    @classmethod
    def from_env(cls, *, seed=None, env=None, dotenv=".env"):
        from db.remote import DEFAULT_EMBEDDED_URL, mode_for, surreal_env

        env = surreal_env(env, dotenv)
        url = (env.get("SURREAL_URL") or "").strip() or DEFAULT_EMBEDDED_URL
        return cls(
            url,
            (env.get("SURREAL_NAMESPACE") or "relay").strip(),
            (env.get("SURREAL_DATABASE") or "relay").strip(),
            seed=seed,
            username=(env.get("SURREAL_USERNAME") or "").strip() or None,
            password=env.get("SURREAL_PASSWORD") or None,
            allow_remote=mode_for(url) == "remote",
        )

    def close(self):
        self._db.close()
        if self._file_lock is not None:
            fcntl.flock(self._file_lock, fcntl.LOCK_UN)
            self._file_lock.close()
            self._file_lock = None

    def seed(self, fixture: dict, reset=False):
        """Load fixture once. Explicit reset replaces only Relay demo tables."""
        fixture = deepcopy(fixture)
        # Freeze history at run initialization unless the fixture specifies a cutoff.
        for run in fixture.get("runs", []):
            run.setdefault("knowledge_cutoff", datetime.now(UTC).isoformat())
        runs = fixture.get("runs", [])
        if not runs:
            raise InvalidInput("Seed must contain runs")
        known = {r["run_id"]: r["disaster_id"] for r in runs}
        for table in OPERATIONAL:
            for row in fixture.get(table, []):
                if known.get(row.get("run_id")) != row.get("disaster_id"):
                    raise InvalidInput(f"{table} record has invalid scope")
        with self._lock:
            if not reset and self._q("SELECT * FROM relay_demo_config:seed;"):
                return
            # Validate each scoped seed with the exact workflow engine before writing.
            rows = []
            for run in runs:
                scoped = {
                    "runs": [run],
                    "disasters": fixture.get("disasters", []),
                    "organizations": fixture.get("organizations", []),
                }
                for table in OPERATIONAL:
                    scoped[table] = [
                        r
                        for r in fixture.get(table, [])
                        if r["run_id"] == run["run_id"]
                    ]
                scoped["lessons"] = [
                    r
                    for r in fixture.get("lessons", [])
                    if r.get("source_run_id") == run["run_id"]
                ]
                store = _engine()(scoped)
                store.emit_event(
                    run["run_id"],
                    {
                        "module": "storage",
                        "action": "seed_loaded",
                        "subject_id": run["run_id"],
                        "details": {"reset": reset},
                        "idempotency_key": "storage-seed-load",
                    },
                )
                rows.append(
                    {**run, "revision": 0, "snapshot": json.dumps(store.snapshot())}
                )
            config = json.dumps(
                {k: fixture.get(k, []) for k in ("disasters", "organizations", "runs")}
            )
            public_rows = [
                self._public(lesson)
                for lesson in fixture.get("lessons", [])
                if lesson.get("approved") is True
            ]
            deletion = (
                "DELETE relay_demo_run; DELETE relay_demo_config; DELETE relay_demo_lesson; "
                if reset
                else ""
            )
            try:
                self._q(
                    "BEGIN; "
                    + deletion
                    + "CREATE relay_demo_config:seed SET snapshot=$config; "
                    "INSERT INTO relay_demo_run $rows; INSERT INTO relay_demo_lesson $public; COMMIT;",
                    {"config": config, "rows": rows, "public": public_rows},
                )
            except Exception:
                # Another process seeded first (remote): keep its data unless reset was requested.
                if reset or not self._remote or not self._q("SELECT * FROM relay_demo_config:seed;"):
                    raise

    def _config(self):
        rows = self._q("SELECT * FROM relay_demo_config:seed;")
        if not rows:
            raise NotFound("Demo database has not been seeded")
        return json.loads(rows[0]["snapshot"])

    def list_disasters(self):
        return self._config()["disasters"]

    def list_organizations(self):
        return self._config()["organizations"]

    def _read(self, run_id):
        run = next((r for r in self._config()["runs"] if r["run_id"] == run_id), None)
        if run is None:
            raise NotFound("Unknown run")
        rows = self._q(
            "SELECT * FROM relay_demo_run WHERE run_id=$run AND disaster_id=$disaster;",
            {"run": run_id, "disaster": run["disaster_id"]},
        )
        if not rows:
            raise NotFound("Unknown run")
        row = rows[0]
        return row, _engine().from_snapshot(json.loads(row["snapshot"]))

    def get_survivor(self, run_id, survivor_id):
        with self._lock:
            _, store = self._read(run_id)
            return store.get_survivor(run_id, survivor_id)

    def get_board(self, run_id):
        with self._lock:
            row, store = self._read(run_id)
            board = store.get_board(run_id)
            # Query only reviewed public lessons, never other runs' survivor data.
            lessons = self._q(
                "SELECT * FROM relay_demo_lesson WHERE approved=true "
                "AND approved_epoch <= $cutoff AND created_epoch <= $cutoff;",
                {"cutoff": self._cutoff(run_id)},
            )
            existing = {lesson["id"] for lesson in board["lessons"]}
            for public in lessons:
                lesson = json.loads(public["snapshot"])
                if lesson["id"] not in existing and lesson["source_disaster_id"] != row["disaster_id"]:
                    board["lessons"].append(lesson)
            return board

    def _cutoff(self, run_id):
        run = next(r for r in self._config()["runs"] if r["run_id"] == run_id)
        cutoff = run.get("knowledge_cutoff", datetime.now(UTC).isoformat())
        return datetime.fromisoformat(cutoff).timestamp()

    def _public(self, lesson):
        # Whitelist: no survivor names, contact fields, transcript or arbitrary metadata.
        fields = (
            "id",
            "source_disaster_id",
            "source_run_id",
            "source_outcome_ids",
            "summary",
            "conditions",
            "recommendation",
            "approved",
            "approved_at",
            "created_at",
        )
        public = {key: lesson.get(key) for key in fields}
        return {
            "snapshot": json.dumps(public),
            "source_run_id": lesson["source_run_id"],
            "source_disaster_id": lesson["source_disaster_id"],
            "source_outcome_ids": lesson.get("source_outcome_ids", []),
            "conditions": lesson.get("conditions", []),
            "lesson_id": lesson["id"],
            "approved": True,
            "approved_epoch": datetime.fromisoformat(lesson["approved_at"]).timestamp(),
            "created_epoch": datetime.fromisoformat(lesson["created_at"]).timestamp(),
        }

    def _mutate(self, method, run_id, *args):
        with self._lock:
            for _ in range(8):
                row, store = self._read(run_id)
                result = getattr(store, method)(run_id, *args)
                snapshot = json.dumps(store.snapshot())
                publication = ""
                params = {
                    "snapshot": snapshot,
                    "run": run_id,
                    "disaster": row["disaster_id"],
                    "revision": row["revision"],
                }
                if method == "approve_lesson":
                    public = self._public(result.get("lesson", result))
                    params["public"] = public
                    params["lesson"] = public["lesson_id"]
                    publication = (
                        "IF array::len($changed)>0 { UPSERT relay_demo_lesson "
                        "CONTENT $public WHERE lesson_id=$lesson; }; "
                    )
                updated = self._q(
                    "BEGIN; LET $changed = (UPDATE relay_demo_run SET snapshot=$snapshot, revision += 1 "
                    "WHERE run_id=$run AND disaster_id=$disaster AND revision=$revision RETURN AFTER); "
                    + publication
                    + "RETURN $changed; COMMIT;",
                    params,
                )
                if updated is None:
                    # SurrealDB 3.x over the 2.0 SDK returns no rows for a BEGIN..COMMIT block;
                    # confirm the revision-checked write by reading it back.
                    updated = self._confirm(run_id, row, snapshot)
                if updated:
                    return result
            raise Conflict("Concurrent update; retry the same idempotency key")

    def _confirm(self, run_id, row, snapshot):
        rows = self._q(
            "SELECT revision, snapshot FROM relay_demo_run WHERE run_id=$run AND disaster_id=$disaster",
            {"run": run_id, "disaster": row["disaster_id"]},
        )
        return bool(rows) and rows[0]["revision"] == row["revision"] + 1 and rows[0]["snapshot"] == snapshot

    def create_request(self, run_id, payload):
        return self._mutate("create_request", run_id, payload)

    def claim_request(self, run_id, request_id, payload):
        return self._mutate("claim_request", run_id, request_id, payload)

    def report_delivery(self, run_id, request_id, payload):
        return self._mutate("report_delivery", run_id, request_id, payload)

    def verify_request(self, run_id, request_id, payload):
        return self._mutate("verify_request", run_id, request_id, payload)

    def save_call(self, run_id, payload):
        return self._mutate("save_call", run_id, payload)

    def save_lesson(self, run_id, payload):
        return self._mutate("save_lesson", run_id, payload)

    def approve_lesson(self, run_id, lesson_id, payload):
        return self._mutate("approve_lesson", run_id, lesson_id, payload)

    def emit_event(self, run_id, payload):
        return self._mutate("emit_event", run_id, payload)

    def save_evaluation(self, run_id, payload):
        return self._mutate("save_evaluation", run_id, payload)

    def save_helper_run(self, run_id, payload):
        return self._mutate("save_helper_run", run_id, payload)

    def list_background_311(self, limit=500):
        with self._lock:
            return self._q("SELECT * FROM relay_background_311 ORDER BY reported_at LIMIT $n", {"n": limit}) or []

    def list_helper_runs(self, run_id):
        with self._lock:
            return self._read(run_id)[1].list_helper_runs(run_id)


def main():
    parser = argparse.ArgumentParser(
        description="Seed a fresh local Relay SurrealDB demo"
    )
    parser.add_argument("--seed", default="data/demo/seed.json")
    parser.add_argument("--reset", action="store_true")
    args = parser.parse_args()
    store = SurrealRecoveryStore.from_env()
    try:
        store.seed(json.loads(Path(args.seed).read_text()), reset=args.reset)
        print(
            json.dumps(
                {"disasters": store.list_disasters(), "database": "local SurrealDB"}
            )
        )
    finally:
        store.close()


if __name__ == "__main__":
    main()
