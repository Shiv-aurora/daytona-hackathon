# Relay build status

Mode: backend subagent work integrated; handing the whole project to the user's receiving UI agent.
Read `HANDOFF.md` for implementation details, startup, remaining work, and limitations.

Goal: demo report -> organization claim -> delivery report -> survivor verification -> reviewed lesson -> measured reuse.

| Agent | Workspace / branch | Work | Status |
| --- | --- | --- | --- |
| `storage` | `../relay-w1-surrealdb` / `codex/w1-surrealdb` | Local SurrealDB persistence, seed/reset, isolation | Complete; integrated as `bf83a6a`, lifecycle fixture repair `5f55283` |
| `recovery` | `../relay-w2-recovery` / `codex/w2-recovery` | Demo API, intake, transitions, follow-up wiring | Complete; merged `9513975` and review fixes `1a05ddd` |
| `calls` | `../relay-w3-calls` / `codex/w3-calls` | Verification calls, consent/emergency gates, ElevenLabs adapters | Reviewed and merged (`d128d5f`); 24 new tests, no real calls |
| `evaluation` | `../relay-w5-evaluation` / `codex/w5-evaluation` | Two-disaster fixture, honest comparison, Arize export | Reviewed and merged (`d7a50e7`); 7 new tests, no live export |
| Integration | This workspace / `main` | Coordinate agents, review/merge, run full backend demo | Complete for this backend build; API running locally |

## Working agreements

- The receiving agent now owns the whole project and may update this file, shared contracts, and backend.
- All backend subagents have handed off; no backend feature work is continuing during takeover.
- No UI changes, remote connections to the original project, deployments, or real phone calls.
- Use `contracts/demo.md` and `contracts/demo.py`; coordinate signature changes with integration.
- Shared seed shape: `data/demo/seed.json` contains `disasters`, `organizations`, `runs`
  (`run_id`, `disaster_id`), `survivors`, `requests`, `calls`, `verifications`, `lessons`,
  `evaluations`, and `system_events` arrays.
- Live service credentials may be unavailable. Implement and test adapters, but distinguish live verification from offline tests.

## Verification

- Starting baseline: 338 Python tests, 85 UI tests, lint/build, and offline smoke passed.
- Final integrated backend: **394 Python tests passed**, **38 smoke tests passed**, Ruff and source compilation passed.
- Independent real-database HTTP checks passed for report splitting, claim/delivery, false receipt/reopen,
  confirmed receipt, rejection of forged call evidence, run isolation, and comparison replay.
- File-backed SurrealDB closed/reopened successfully with its request and idempotency ledger intact.
- Storage verified a genuine local embedded SurrealDB instance; no Docker daemon is needed.
- Agreed dependencies: `surrealdb==2.0.0`, `arize-otel==0.14.1`.
- Project-local `.venv` installed; baseline still passes all 338 Python tests with the new dependencies.
- Calls branch: 362 tests and smoke passed. Evaluation branch: 345 tests and smoke passed.
- Arize's installed SDK and real HTTP exporter were tested using a fake network transport.
- Integrated `python -m api.demo --store surreal` completed against genuine local `mem://` SurrealDB:
  scripted non-receipt recorded, request reopened, and both three-case evaluation variants persisted.
- First independent HTTP/Surreal check caught a real plural-intake bug (`food and blankets` created
  only food). The owning agent fixed it and added regression coverage; all 25 targeted tests now pass.

## Integration log

- User replaced the manual worker/PR checkpoint plan with active subagent implementation.
- Four backend agents will build concurrently. The fifth/UI workstream stays with the user.
- Shared kickoff committed as `6068066`; backend agents have been told to sync it.
- Seed IDs agreed: `demo-history` / `demo-current`; disasters `demo-flood-2025` / `demo-storm-2026`;
  organizations `demo-food`, `demo-supplies`, `demo-transport`.
- Review caught and corrected recovered-emergency handling after a recorded receipt, and same-disaster
  lesson leakage into held-out evaluations.
- Recovery/storage are integrated with the actual shared seed, call hooks, evaluation API, and restart persistence.
- Embedded SurrealDB is limited to one API process per local database path; concurrent claims are tested
  within that server. Opening another process against the same path will fail closed.
- Review tightened persisted call transitions and comparison replay after a partial write. Current
  decisions are an explicit deterministic demo baseline; ElevenLabs live calling and hosted Arize export
  have not been exercised, and no real-world performance improvement is claimed.

## Running backend / UI handoff

- Base URL: `http://127.0.0.1:8787` (local SurrealDB-backed API; data persists in ignored `.relay-demo`).
- Verified HTTP 200: `/disasters`, `/organizations`, `/runs/demo-current/board`.
- Current board: three synthetic requests, three survivors, one seeded call and one historical lesson.
- Shared payloads: `contracts/demo.md`; API details: `api/RECOVERY.md`; database setup: `db/RECOVERY.md`.
- Restart: `make serve PYTHON=.venv/bin/python` (one process per embedded database).
- Resettable scripted rehearsal: `make demo-surreal PYTHON=.venv/bin/python` (no telephone/network calls).
- `ui/` has no changes from this backend/subagent build. Its design and wiring remain with the user's other AI agent.
