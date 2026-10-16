# Backend tasks for the next agents

Repo: https://github.com/Shiv-aurora/daytona-hackathon (branch from `main`, open a PR to `main`).
Read first: `HANDOFF.md`, `contracts/demo.md`, `AGENTS.md` (safety and isolation rules still apply).
Do not edit `ui/`. Each task is independent. Run `make smoke` and the full Python suite before the PR.
Never commit credentials; real calls and paid services stay out of tests.

## B1 · Demo API gaps (`codex/b1-demo-api`) — do first
Deliverables:
1. `POST /runs/{run}/calls/{call_id}/start` body `{idempotency_key, mode:"scripted", scripted_answer:"no"|"yes"|"no_answer"}`.
   Use `execute_follow_up` + `ScriptedTransport`. Require opt-in (409 otherwise), only a queued call (409), and the
   request must be `awaiting_verification` or `reopened`. Return `{call, request}`. Calls expose `mode` and the fixed `disclosure`.
2. `POST /demo/reset`: restore seed data for the in-memory AND SurrealDB stores.
3. `GET /runs` -> `{runs:[{run_id, disaster_id}]}` (the old route shadows it) and
   `GET /health` -> `{ok, store, live:{elevenlabs, arize, surreal}}` (booleans, never secrets).
4. Keep `conditions` (e.g. `access_blocked`) on requests; `create_request` currently drops them.
5. `GET /runs/{run}/requests/{id}/recommendations`: approved, de-identified lessons only, with `source_outcomes`.
6. Compare response includes per-case rows and `synthetic: true`.
Acceptance: tests for each route, including 409s and idempotent replay; UI `?mode=live` works end to end.

## B2 · Voice intake and triage (`codex/b2-voice-intake`)
Flow: an incoming call (simulated: audio file or scripted transcript; real 911/radio is out of scope) ->
ElevenLabs speech-to-text -> code-owned emergency check FIRST (before any LLM) -> LLM triage (Groq, model name from env)
-> structured output `{needs:[category], conditions:[], urgency_deadline, summary}` -> `POST /runs/{run}/reports`.
Deliverables:
1. `POST /runs/{run}/intake/calls` accepting `{transcript}` or `{audio}`; returns `{call, transcript, triage, requests, escalated}`.
2. Transcript segments with speaker and timestamps; store them on the call. Ship 3 sample transcripts in `data/demo/`
   (food+supplies with road blocked; emergency phrase; unclear caller).
3. Triage never ranks people or gives medical advice; low-confidence output goes to a human queue.
4. LLM client behind an interface with a deterministic fake for tests.
Acceptance: emergency text never reaches the LLM (test); every mutation emits a `system_event` with run and disaster ids.

## B3 · AI helper agents on Daytona (`codex/b3-helpers`) — spec pending
Concept (owner still finalizing): five ElevenLabs agents, each spawned in a Daytona sandbox, follow up with households and
organizations and keep the dashboard/triage list fresh; an assigner suggests org matches (humans confirm).
Do not start until the owner sends the final spec. Expect: helper roles, a `helpers` table (status, last_action, run_id),
`GET /runs/{run}/helpers`, and sample call transcripts.
