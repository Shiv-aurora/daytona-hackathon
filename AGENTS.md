# Relay demo agent rules

Relay connects disaster survivors with relief organizations, verifies that assistance arrived,
and reuses reviewed lessons from earlier recoveries. Build a hackathon demo, not a production platform.

## Stack and scope

- SurrealDB is the target database. The retained offline store is a reference/test adapter only.
- ElevenLabs provides voice follow-up. Arize evaluates decisions and historical lesson usefulness.
- Next.js is the UI. No hosting, old credentials, or external project links are configured.
- MVP: report -> request -> organization claim -> delivery report -> survivor verification -> lesson.
- 911/radio/211 integrations, real agency connections, production auth, and infrastructure are out of scope.
- A demo organization selector represents seeded organizations; it is not production authorization.

## Safety and isolation

- Never commit credentials. Use local `.env` files; commit only empty `.env.example` templates.
- Calls require confirmed opt-in. Keep the fixed disclosure and emergency response code-owned.
- Emergency detection and immediate human escalation run before any LLM.
- No medical advice or ranking people. Sort work by deadlines/status and let humans decide.
- An organization reporting delivery does not resolve a request. Record verification separately.
- Every operational read/write preserves `run_id` and `disaster_id`; mutations emit a `system_event`.
- Only reviewed, de-identified lessons may cross disaster/run boundaries. Never share survivor records.
- Do not weaken, skip, or delete safety, isolation, replay, or time-cutoff tests to pass CI.

## Five worker chats

| Worker | Branch | Owns |
| --- | --- | --- |
| W1 SurrealDB | `codex/w1-surrealdb` | `db/`, `memory/` |
| W2 Recovery | `codex/w2-recovery` | `api/`, `runtime/`, `intake/` |
| W3 Calls | `codex/w3-calls` | `calls/` |
| W4 UI | `codex/w4-ui` | `ui/` |
| W5 Evaluation | `codex/w5-evaluation` | `eval/`, `data/` |

Integration chat owns `main`, `contracts/`, `schemas.py`, `interfaces.py`, `graph_state.py`,
root configuration/CI/dependencies, and worker instructions. Request shared changes rather than
editing another worker's files. A worker may change its own package manifest/lockfile.

## Working rules

- Current execution: integration spawns backend subagents and maintains `STATUS.md`.
  The user owns the UI in a separate AI chat. Do not edit `ui/` in backend work.
  The old manual C1/C2/C3 approval pauses are superseded for explicitly assigned subagent tasks;
  follow the assigned implementation scope and hand results back to integration.
- Each chat uses its own worktree. Never switch worker branches in another chat's directory.
- Read `START_HERE.md`, your worker brief, and `WORKER_PLAN.md` before starting.
- Work on one checkpoint only. Aim for the smallest useful demo; no generic frameworks or unrelated refactors.
- Work against `contracts/demo.md` and `contracts/demo.py`; mock the same signatures when dependencies lag.
- Run Python compile, Ruff, and relevant tests; before handoff run the full Python suite.
- UI uses `npm ci`, then lint, tests, and build. Report actual failures; never invent passing checks.
- Run `make smoke` before handoff. Keep real calls and paid service use out of tests.
- With a new remote: open `[W#-C#] short result` PR to `main`, include checks and limitations, then stop.
- With no remote: commit locally, report branch/SHA/checks, then stop. Do not create or reconnect a remote.
- Integration reviews and merges. After merge, sync `main` into your worker branch before the next prompt.
