# Arize tracing (basic)

Two opt-in pieces, both no-ops without keys:

- `eval/arize.py` exports aggregate comparison results (`trace_comparison`).
- `eval/arize_trace.py` provides `traced(name, **attrs)` (context manager or decorator)
  around key decision points.

## What is traced

| Span | Where | Attributes |
| --- | --- | --- |
| `relay.follow_up.outcome` | `calls/recovery.py` `_finish` | run_id, disaster_id, request_id, outcome, received, emergency |
| `relay.helper.run` | `api/helper_routes.py` `execute` | role, run_id, disaster_id, request_id, category, status |
| `relay.recovery.decide` | `api/recovery.py` `decide` | disaster_id, category, status, organization_id, lesson_ids |
| `relay.recovery.compare` | `api/recovery.py` `compare` | run_id, disaster_id, experiment_id, case_count |

Only an allow-list of de-identified attributes (`ALLOWED` in `arize_trace.py`) can be
recorded; everything else (report text, descriptions, transcripts, summaries, phone
numbers, survivor ids) is dropped before it reaches a span. Strings over 80 chars are dropped.

## Turn it on

Set in your local `.env` (never commit): `ARIZE_API_KEY`, `ARIZE_SPACE_ID`, optionally
`ARIZE_PROJECT_NAME` (default `relay-demo`). `arize-otel` is in `requirements.txt`.
Export happens through `eval.arize.configure_arize` (OTLP/HTTP, no global tracer provider).
If keys are missing or registration fails, tracing silently does nothing and code behaves identically.

## Status

Unit tests use fake tracers only (no network). **Not verified live**: no ARIZE_*
keys were present when this was built, so no trace has been confirmed in the Arize UI.
