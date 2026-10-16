# Backend demo

From the repository root with Python dependencies installed:

```sh
python -m api.server --store memory --seed data/demo/seed.json --port 8787
python -m api.demo --store memory --seed data/demo/seed.json
```

The first command serves the recovery API alongside retained `/runs` and console
routes. The second explicitly runs a synthetic, no-network survivor follow-up
and measured held-out evaluation. No call is made and no provider credentials
are needed. `--answer yes`, `--answer no`, and `--answer 'I cannot breathe'`
exercise receipt, missed delivery, and immediate human escalation.

Use `--store surreal` for the SurrealDB adapter. It reads its local configuration
through `SurrealRecoveryStore.from_env`; one API process must own a local
embedded database. Do not start multiple workers or an autoreloader against the
same local database. The server closes the adapter on shutdown. No deployment
or remote project is configured by these commands.

The demo selector is simulated organization access. It is not authentication.
GET `/disasters`, `/organizations`, `/runs/demo-current/board`; POST report,
claim, delivery, human verification, follow-up queue, lesson draft/approval and
`/runs/demo-current/evaluations/compare` use `contracts/demo.md` payloads.
A delivery report leaves the request awaiting verification. The public verify
endpoint rejects `survivor_call`; only the server-owned execution bridge writes
that evidence after a consent-checked call. Queueing is separate from execution.

Integration seams: `api.server.make_handler(db, origin, recovery_store)` injects
any `RecoveryStore`. `api.follow_up.execute_follow_up(store, run_id, call_id,
transport, callback_number)` runs an explicitly requested queued call with
server-resolved survivor identity. It supplies W3 durable hooks, stores the
completed evidence, and idempotently verifies explicit receipt or non-receipt.
The demo uses one serialized execution lane; it is not a distributed call worker.
An interrupted active call remains active for human review instead of redialing.
The Surreal adapter forwards `get_survivor` for server-only contact resolution.

Historical lessons require human approval; drafts require real run-scoped
verification outcomes and reject known survivor details/email/phone content.
The demo de-identification checks are conservative string rules, so a human must
still review each lesson. Only approved lessons from a different disaster and
before the run's knowledge cutoff cross boundaries. The decision baseline is
rule-based and cites only approved relevant lessons. Evaluation results are
synthetic measurements, not claims of real-world model accuracy.
