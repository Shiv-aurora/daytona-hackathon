# Relay project handoff

The receiving agent is taking over the **whole project**, including UI, backend, shared contracts,
tests, and documentation. The old per-worker folder restrictions and manual checkpoint pauses are
historical coordination rules, not a restriction on this authorized takeover. Keep the safety rules.

## Start here

- Primary checkout: `/Users/shivamarora/Documents/Code/daytona-hackathon`, branch `main`.
- All four backend subagents' implementation and review fixes are integrated on `main`.
- The user's separate UI agent now owns continuation. No backend subagents remain working on features.
- Read `STATUS.md` for agent history, `contracts/demo.md` for payloads, and this file for gaps.
- The old `codex/w4-ui` worktree was created before the backend implementation. If using it, merge
  current local `main` into that branch first. Preserve any UI changes already made there; do not reset it.
- No GitHub remote or hosting project is configured. The original repo/services are disconnected.
  The user said they will create a new repository later. Do not reconnect the original.

## Product direction

**Relay: disaster recovery that gets smarter every time.**

Response: survivor/volunteer report -> individual assistance requests -> organization claim and promise
-> delivery report -> survivor/human verification -> resolution or reopening with human follow-up.

Intelligence: verified outcomes -> reviewed, de-identified lessons -> relevant historical recommendations
-> measured comparison with and without history. Recommendations remain subject to human review.

Target integrations: SurrealDB for persistent recovery knowledge, ElevenLabs for consenting survivor
follow-up, Arize for evaluation/observability. Emergency dispatch, radio, 211, and real agency integrations
are future scope. Build the smallest convincing hackathon demo; no production platform is expected.

## What is implemented

| Area | Implementation / important files |
| --- | --- |
| Shared boundary | `contracts/demo.py`: storage protocol and shared errors. `contracts/demo.md`: record fields, API, safety and UI expectations. |
| Recovery domain | `api/demo_store.py`: scoped in-memory reference engine, state transitions, idempotency ledger, consent, lessons and evidence checks. |
| HTTP API | `api/recovery.py`, `api/server.py`: new JSON recovery routes alongside the retained legacy console routes. |
| Durable storage | `db/recovery.py`, `db/recovery_schema.surql`: genuine embedded SurrealDB, scoped snapshots, revision-checked transaction, persisted replay ledger, reviewed public lessons. |
| Follow-up integration | `api/follow_up.py`: server-owned queued-call execution, stored result/evidence, request verification, retry repair after result storage. |
| Call safety | `calls/recovery.py`: conservative explicit receipt answers, no-consent refusal, uncertain/no-answer outcomes, fixed disclosure, durable emergency hooks, browser voice adapter. |
| Provider authentication | `calls/webhooks.py`: exact-body ElevenLabs HMAC/timestamp verification and server-owned conversation lookup; recovered emergency handling even after earlier receipt. |
| Evaluation | `eval/recovery.py`: same held-out inputs and decision callable with history off/on; labels excluded from inputs, temporal/same-disaster leakage checks. |
| Arize adapter | `eval/arize.py`: explicit opt-in aggregate tracing with the installed Arize SDK. Real SDK/export serialization tested with a fake network transport. |
| Demo data | `data/demo/seed.json`, `held_out.json`, `README.md`: two fictional disasters, three organizations, four total requests/survivors across history/current data, three held-out cases. |
| Rehearsal | `api/demo.py`: explicit scripted survivor answer plus stored comparison, with memory or real embedded SurrealDB. No telephone/network call. |
| Independent integration checks | `tests/test_recovery_integration.py`: actual local HTTP + real SurrealDB, complete request lifecycle, replay, isolation, forged evidence rejection, database restart. |

The earlier offline scenario, runtime, call safety tests, and old UI remain available as regression
coverage. MongoDB drivers/live connection paths and the previous hackathon instructions were removed.
Do not mistake the retained old console endpoints or fixtures for the new recovery application.

## Running state and commands

At handoff, the SurrealDB-backed API is running at **http://127.0.0.1:8787**. Verified HTTP 200:

- `GET /disasters`
- `GET /organizations`
- `GET /runs/demo-current/board`

The current board has three requests, three synthetic survivors, one seeded call, and one historical
lesson. The process was launched through this chat's execution session `83619`; check the URL before
starting another process. The local UI was previously started on port 3000; its current state was not
rechecked during this handoff because UI work belongs to the receiving agent.

Run commands from the primary repository root:

```sh
# Already installed locally: Python 3.13 virtualenv with pinned backend/test dependencies.
# For a clean environment:
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt

# Persistent local backend; first check whether port 8787 is already serving it.
make serve PYTHON=.venv/bin/python

# Resettable rehearsal using a genuine ephemeral SurrealDB and a scripted answer.
make demo-surreal PYTHON=.venv/bin/python

# Receipt/emergency variants, also scripted and without network calls.
.venv/bin/python -m api.demo --store memory --answer yes
.venv/bin/python -m api.demo --store memory --answer 'I cannot breathe'

# Tests and lint.
.venv/bin/python -m pytest -q
.venv/bin/python -m ruff check .
make smoke PYTHON=.venv/bin/python
```

`requirements.txt` pins `surrealdb==2.0.0` and `arize-otel==0.14.1`. No Docker daemon is required.
The `.venv`, installed UI dependencies, credentials, and local database are ignored, not committed.

Persistent storage defaults to `surrealkv://.relay-demo`. **Only one API process may own that path**:
the embedded SDK maintains independent cached views across separate connections. A file lock rejects
another owner. One process supports concurrent HTTP threads and claim consistency.

To reset, stop the API cleanly so its store closes, then run:

```sh
.venv/bin/python -m db.recovery --seed data/demo/seed.json --reset
make serve PYTHON=.venv/bin/python
```

Reset replaces the demo tables and discards interactions. It is not necessary for ordinary startup.
`SURREAL_URL`, `SURREAL_NAMESPACE`, `SURREAL_DATABASE`, `SURREAL_USERNAME`, `SURREAL_PASSWORD` are read from
local `.env` plus process environment. Blank settings select the local embedded database.

## UI integration: first remaining task

No `ui/` files were changed during this backend/subagent build. The existing console remains the
earlier mock recovery console. Completely redesign it around the new shared board.

Suggested navigation: **Response, Organizations, Calls, Intelligence**. Include a disaster selector,
obvious simulated-data/access labels, shared request board, organization claim/delivery actions,
and request detail showing promise, organization report, survivor evidence, and verification separately.
Intelligence should show reviewed lessons and source outcomes plus the actual comparison results.

Set the UI's local `NEXT_PUBLIC_RELAY_API_URL=http://127.0.0.1:8787`. This changes configuration only;
the old UI's adapter still needs to be replaced/adapted to the new routes. Read `contracts/demo.md`.

Useful identifiers:

- Runs: `demo-current`, `demo-history`.
- Disasters: `demo-storm-2026`, `demo-flood-2025`.
- Organizations: `demo-food`, `demo-supplies`, `demo-transport`.
- Requests: `current-food-1` (open), `current-supplies-1` (awaiting verification),
  `current-transport-1` (reopened); historical request `history-food-1` is resolved.
- Reviewed historical lesson: `lesson-confirm-handoff`.

The new API paths do **not** have an `/api` prefix. Board path is `/runs/{run_id}/board`, not the old
`/runs/{run_id}/console`. Mutation routes and bodies are listed in `contracts/demo.md`.
Every mutation needs an idempotency key; reuse it only for retrying the identical action/payload.

`GET /runs` is still a legacy compatibility route, not a new recovery-run directory. The two demo run IDs
are documented above; add a small new-run discovery route if the UI needs one. Do not fabricate records.

Public `/verify` accepts **human_review** only. A UI receipt form must not pretend to be an ElevenLabs
call. `/follow-up` queues a consent-checked job; it does not start a real call. An explicit server-owned
execution path is needed for a new interactive call experience.

## Other remaining work and honest limits

1. **Live ElevenLabs wiring is incomplete.** Request-level sessions/browser bridge and signed webhook
   helper exist, but the new recovery API does not register the browser session/Custom LLM/SSE/webhook
   HTTP routes. The old `calls.voice.server` is a separate legacy voice server. Wire opaque server-bound
   sessions and authenticated provider conversation mapping before exposing the new live experience.
   Outbound telephony is disabled/not implemented. Fresh agent credentials, callback configuration,
   private contact lookup, and confirmed consent from the actual demo recipient are still required.
   Synthetic fixture opt-in does not authorize calling a real person.
2. **The new decision baseline is deterministic.** Intake uses keyword category detection, and
   `api.recovery.decide` selects capable organizations and relevant approved lessons. It is not a new
   live LLM agent. The earlier `runtime/llm.py` provider client exists but is not wired into the new
   report/recommendation flow. Preserve emergency-first checks if adding a model.
3. **Historical recommendations are not yet a full live product flow.** The board retrieves reviewed
   history; the comparison callable produces cited recommendations. A request-level recommendation
   endpoint/action can reuse that logic with server-resolved context. Do not expose held-out labels or
   claim the system retrains itself. Learning currently means reviewed memory and retrieval.
4. **Arize live integration is unverified.** Aggregate-span export is available through explicit
   `configure_arize()` / `trace_comparison(provider, result)`. No hosted datasets, experiments, evaluator
   tasks, real ingestion, or trace URL were verified. Credentials are absent. Current metrics are
   deterministic checks on three synthetic cases, labeled `synthetic_deterministic`; no real-world
   accuracy improvement is demonstrated. Preserve `measurement_type`, `limitations`, and null trace URLs.
5. **Storage is a demo aggregate, not a normalized graph platform.** Requests/evidence/replay state are
   stored in scoped run snapshots. Public lessons also expose native source-outcome IDs/conditions.
   Do not show a fabricated live knowledge graph. Normalize only if useful to the actual demo.
6. **Demo access is simulated.** There is no production auth, agency onboarding, automatic background
   telephone worker, or real emergency/agency connection. These are outside the immediate demo scope.
7. **Finish one full visible walkthrough.** Report food + blankets -> claim -> report delivery ->
   non-receipt -> reopened/human follow-up -> later verified receipt -> draft/review lesson -> inspect
   reviewed history and honest comparison in the second disaster. Then run UI lint/tests/build and
   verify UI -> API -> SurrealDB -> UI. Backend verification already covers the HTTP/database portion.

## Safety constraints to preserve

- No call without confirmed opt-in; no automatic live calls while testing.
- Fixed disclosure and emergency response stay code-owned and unchanged by an LLM.
- Emergency detection and durable human escalation happen before model work.
- Organization-reported delivery is not verified receipt; no-answer/uncertainty never close a request.
- No medical advice or ranking households; use deadlines/status and human review.
- All operational queries/mutations remain scoped by run and disaster; keep replay and time-cutoff tests.
- Only reviewed de-identified lessons may cross disaster boundaries. Approval and creation must precede
  the target run's frozen knowledge cutoff. New approvals appear in subsequently seeded runs, not past ones.
- Never trust browser-supplied survivor-call evidence or provider summaries as proof of receipt.
- Keep real secrets/contacts out of Git, public board payloads, metrics, and traces.

## Verification and Git state

Latest integrated checks: **394 Python tests passed**, **38 smoke tests passed**, all **25 targeted
HTTP/storage tests passed**, Ruff, compileall, and diff checks passed. A genuine SurrealDB scripted
rehearsal and file-backed restart/replay passed. These are backend results.

The UI's earlier baseline had 85 tests, lint and build passing before this backend work. That is not
verification of the redesigned UI; rerun its committed-lockfile checks after UI changes.

Important implementation commits: evaluation `d7a50e7`, calls `d128d5f`, recovery `9513975`, storage
integrated as `bf83a6a`, storage fixture fix `5f55283`, recovery review fixes `1a05ddd` (merge `ac70a5f`).
The final handoff commit also includes the independent integration tests and updated Makefile/docs/status.

Backend worktrees remain beside the main checkout for reference: `relay-w1-surrealdb`,
`relay-w2-recovery`, `relay-w3-calls`, `relay-w5-evaluation`. Some contain temporary cherry-picked
dependency history; **main is the integrated source of truth**. Do not blindly merge them again.
No remote push or PR was made. The original history was removed; current history is the fresh demo build.
