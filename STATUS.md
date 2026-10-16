# Relay build status

Mode: active backend subagents. UI is owned by the user's separate AI agent; do not edit `ui/`.

Goal: demo report -> organization claim -> delivery report -> survivor verification -> reviewed lesson -> measured reuse.

| Agent | Workspace / branch | Work | Status |
| --- | --- | --- | --- |
| `storage` | `../relay-w1-surrealdb` / `codex/w1-surrealdb` | Local SurrealDB persistence, seed/reset, isolation | Implementing; genuine embedded DB connection verified |
| `recovery` | `../relay-w2-recovery` / `codex/w2-recovery` | Demo API, intake, transitions, follow-up wiring | Implementing store and API; coordinating storage/call interfaces |
| `calls` | `../relay-w3-calls` / `codex/w3-calls` | Verification calls, consent/emergency gates, ElevenLabs adapters | Implementing verification and authenticated webhook adapters |
| `evaluation` | `../relay-w5-evaluation` / `codex/w5-evaluation` | Two-disaster fixture, honest comparison, Arize export | Building fixture and evaluator; Arize dependency verified |
| Integration | This workspace / `main` | Coordinate agents, review/merge, run full backend demo | In progress |

## Working agreements

- Agents use their own worktrees and commit their work. Only integration updates this file.
- No UI changes, remote connections to the original project, deployments, or real phone calls.
- Use `contracts/demo.md` and `contracts/demo.py`; coordinate signature changes with integration.
- Shared seed shape: `data/demo/seed.json` contains `disasters`, `organizations`, `runs`
  (`run_id`, `disaster_id`), `survivors`, `requests`, `calls`, `verifications`, `lessons`,
  `evaluations`, and `system_events` arrays.
- Live service credentials may be unavailable. Implement and test adapters, but distinguish live verification from offline tests.

## Verification

- Starting baseline: 338 Python tests, 85 UI tests, lint/build, and offline smoke passed.
- New backend demo and live integration results: pending.
- Storage verified a genuine local embedded SurrealDB instance; no Docker daemon is needed.
- Agreed dependencies: `surrealdb==2.0.0`, `arize-otel==0.14.1`.

## Integration log

- User replaced the manual worker/PR checkpoint plan with active subagent implementation.
- Four backend agents will build concurrently. The fifth/UI workstream stays with the user.
- Shared kickoff committed as `6068066`; backend agents have been told to sync it.
- Seed IDs agreed: `demo-history` / `demo-current`; disasters `demo-flood-2025` / `demo-storm-2026`;
  organizations `demo-food`, `demo-supplies`, `demo-transport`.
