# Relay demo contract v1

Integration owns this file and `demo.py`. Workers use these names; request additions instead of
silently inventing incompatible fields. Existing schemas/interfaces remain for the offline regression
scenario. The new demo uses this smaller boundary.

## Core records

All operational records include `id`, `run_id`, `disaster_id`, and ISO-8601 UTC `created_at`.
The special shared configuration records are disasters and seeded organization profiles.

- Disaster: `id`, `name`, `kind`, `region`, `started_at`.
- Organization: `id`, `name`, `capabilities` (string list), `region`.
- Survivor: core fields plus `display_name`, `language`, `call_opt_in` (boolean).
  Phone numbers are server-only. Never send them in board/trace/lesson payloads.
- Request: core fields plus `survivor_id`, `category`, `description`, `status`, `due_at` (nullable),
  `organization_id` (nullable), `promised_at` (nullable), `source_report_id`.
- Call: core fields plus `request_id`, `survivor_id`, `status`, `provider_conversation_id` (nullable),
  `outcome`, `summary`, `evidence_ids` (string list). No raw phone numbers.
- Verification: core fields plus `request_id`, `received` (true/false/null), `source`
  (`survivor_call` or `human_review`), `evidence_ids`, `notes`.
- Lesson: `id`, `source_disaster_id`, `source_run_id`, `source_outcome_ids`, `summary`, `conditions`
  (string list), `recommendation`, `approved` (boolean), `approved_at` (nullable), `created_at`.
  Only approved de-identified lessons may be returned for another disaster. Recommendations cite lesson IDs.
- Evaluation: core fields plus `experiment_id`, `variant` (`without_history`/`with_history`),
  `case_count`, `metrics` (numeric values or null), `measured_at`, `trace_url` (nullable).
- System event: core fields plus `module`, `action`, `subject_id`, `details` (object).

Request statuses: `open`, `claimed`, `awaiting_verification`, `resolved`, `reopened`.
Claim requires `open` or `reopened`; delivery report requires `claimed` and yields
`awaiting_verification`. Only received=true from survivor evidence or a human review yields `resolved`.
received=false yields `reopened`; no answer/received=null keeps the request unverified.
Reject invalid transitions and a second concurrent claim with 409. Replay the same idempotency key
without duplicating a request, call, verification, or event. An emergency emits a human escalation
before any model call and never automatically resolves the request.

## API

Python API owns `/runs/{run_id}/...` (no `/api` prefix). UI uses `NEXT_PUBLIC_RELAY_API_URL`.
The server rejects records from another run/disaster; do not trust a client-supplied identity.
The demo org selector chooses one of the seed organizations and is visibly labeled as simulated access.

- `GET /disasters` -> `{ disasters: Disaster[] }`
- `GET /organizations` -> `{ organizations: Organization[] }`
- `GET /runs/{run_id}/board` -> Board below.
- `POST /runs/{run_id}/reports` body `{ disaster_id, text, survivor_id, idempotency_key }`
  -> `{ requests: Request[] }`. Intake splits individual needs; emergency handling occurs first.
- `POST /runs/{run_id}/requests/{id}/claim` body `{ organization_id, promised_at, idempotency_key }`
  -> `{ request: Request }`.
- `POST /runs/{run_id}/requests/{id}/delivery` body `{ organization_id, notes, idempotency_key }`
  -> `{ request: Request }`.
- `POST /runs/{run_id}/requests/{id}/verify` body `{ received, source, evidence_ids, notes, idempotency_key }`
  -> `{ request: Request, verification: Verification }`. `survivor_call` source is server-generated only;
  a UI submission is a `human_review` and must never fabricate a call.
- `POST /runs/{run_id}/requests/{id}/follow-up` body `{ idempotency_key }`
  -> `{ call: Call }`. Queue only for confirmed opt-in. Starting an actual call requires an explicit demo action.
- `POST /runs/{run_id}/lessons/{id}/approve` body `{ idempotency_key }` -> `{ lesson: Lesson }`.
- `POST /runs/{run_id}/lessons` body `{ source_outcome_ids, summary, conditions, recommendation,
  idempotency_key }` -> `{ lesson: Lesson }`. Draft only, with `approved=false`; source outcomes must
  exist in this run's verification evidence. Approval is a separate human demo action.
- `POST /runs/{run_id}/evaluations/compare` body `{ idempotency_key }` -> comparison result from the
  frozen held-out demo cases. Persist measured variants for the board. Clearly label synthetic runs.

Board is `{ run_id, disaster: Disaster, organizations: Organization[], survivors: Survivor[],
requests: Request[], calls: Call[], verifications: Verification[], lessons: Lesson[],
evaluations: Evaluation[], system_events: SystemEvent[] }`.
On a selected request, show evidence/verification beside the promise and delivery report.
Use 400 for bad input, 404 for unknown or out-of-scope IDs, 409 for invalid/replayed-conflicting actions,
and 503 for unavailable live services. Error body is `{ error: string }`.

## Worker seams

`contracts/demo.py` is the storage protocol; W1 implements it and W2 calls it. Payloads use the fields above.
Report parsing is W2's responsibility; storage receives one normalized request at a time.
All mutation payloads include `idempotency_key`. Storage enforces identity and transition checks atomically.
`emit_event(run_id, payload)` writes an event without manufacturing an assistance request; emergency
handling uses it to record immediate human escalation before extraction or model execution.

W3 exports `calls.recovery.run_follow_up(job: dict, context: dict, transport) -> dict`.
Its result has `call_id`, `request_id`, `run_id`, `disaster_id`, `outcome`, `received` (true/false/null),
`summary`, `evidence_ids`, and `emergency` (boolean). W2 schedules jobs, supplies server-resolved context,
and writes results through RecoveryStore. W3 owns the provider/webhook adapter and signature verification;
W2 owns HTTP route registration. Never infer receipt merely because a call completed.

W5 exports `eval.recovery.run_comparison(cases: list[dict], decide) -> dict` with `experiment_id`,
`case_count`, `without_history` and `with_history` metric dictionaries, `measured_at`, and `trace_url`.
A case includes report, available organizations/conditions, approved historical lessons, and labeled
expected category, valid organization IDs, expected verification, and relevant lesson IDs.
`decide(case, lessons_enabled=bool)` returns the workflow decision; W2 supplies it at integration.
Run the same held-out cases in both variants. Store results through RecoveryStore for the UI.

## Demo design

Left navigation: Response, Organizations, Calls, Intelligence. Top bar: disaster selector and demo label.
Response is the shared request board with filters, claim/delivery actions and a request detail drawer.
Calls shows consent, queued/active/completed calls, transcript/summary, and unresolved outcomes.
Intelligence shows reviewed lessons, linked outcomes, suggested applications, and measured comparison.
Use readable light surfaces, a restrained teal accent and accessible amber/red status cues. This is an
operations workspace for relief coordinators, not the old token/debug console. Mobile access and keyboard
navigation matter. Future emergency-feed integrations are shown only as future scope, never fake live feeds.
