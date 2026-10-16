# Relay synthetic demo

`seed.json` is resettable fixture input, not a claim about real disasters or people.
Use run `demo-current` and disaster `demo-storm-2026`; history is `demo-history`
and `demo-flood-2025`. Organizations are `demo-food`, `demo-supplies`, and
`demo-transport`. No phone numbers are seeded and no call starts automatically.

1. Open current-food-1 and claim it for demo-food. Report delivery: it must remain
   awaiting verification. A coordinator or an explicitly opted-in call can record
   that nothing arrived, reopening the request. Claim again, report delivery,
   and record evidence of receipt to resolve it.
2. current-supplies-1 already awaits verification; current-transport-1 was reopened
   after non-receipt. The transport survivor has not opted in: calls must refuse.
3. Historical history-food-1 shows a missed delivery followed by confirmed receipt.
   lesson-confirm-handoff cites both actual verification records. Its recommendation
   is de-identified and was approved before the current-disaster evaluation cutoff.
4. Run `eval.recovery.run_comparison` on `held_out.json` with W2's decision callable.
   The same callable, reports, organizations, evidence, conditions and cutoff run
   twice, with different isolated experiment run IDs and history off/on. `expected`
   is held-out truth, never a decision input. Do not tune decisions to these labels.

Scores are deterministic synthetic checks, with three cases. False closure is an
error rate; all other scores are pass rates. Groundedness checks cited IDs against
provided evidence/context, not semantic truth. Relevant lesson use is measured only
where a relevant lesson exists and history is enabled; otherwise it is null.
No gain is promised: keep the measured results, including ties or regressions.

Arize export is optional: install `arize-otel==0.14.1`, configure local ARIZE_SPACE_ID,
ARIZE_API_KEY and optional ARIZE_PROJECT_NAME, then explicitly call
`configure_arize()` and `trace_comparison(provider, result)`. Shut down the provider
when finished. Only aggregate metric values and experiment identifiers leave the
process. No credentials or paid-service calls are used by tests. Without credentials
results stay local and trace_url stays null; no live Arize trace has been verified.
The integration uses Arize's documented HTTP OTLP endpoint and register arguments:
[Arize OpenTelemetry documentation](https://arize.com/docs/ax/observe/tracing-integrations-auto/opentelemetry-integrations-for-arize/opentelemetry-arize-otel).
