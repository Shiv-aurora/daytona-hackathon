# W3: copy this prompt into its worker chat

You are Relay W3. Work only in `/Users/shivamarora/Documents/Code/relay-w3-calls` on `codex/w3-calls`.
Read AGENTS.md, WORKER_PLAN.md and contracts/demo.md before coding. You own calls/.
This is a hackathon demo: build the smallest useful implementation and avoid unrelated refactors.

## C1 only

Keep the existing ElevenLabs browser voice bridge and fixed disclosure/safety behavior. Add
calls.recovery.run_follow_up(job, context, transport) with the result shape in contracts/demo.md.
Ask whether the specific promised assistance arrived and record received=true/false/null with evidence.
Use a fake transport in tests and keep a clearly labeled typed fallback. A completed or unanswered call
must not automatically mean receipt. Check opt-in before starting and emergencies before any model.
C1 is the verification adapter plus the existing browser voice path; no outbound phone integration yet.
Do not call real people while implementing. C2 will connect outbound telephony only with new credentials
and confirmed demo-recipient opt-in. Request HTTP route registration from W2; do not edit api/.
Acceptance: received, not received, no answer, no consent, and emergency cases all produce correct
results; replay does not double-call or double-write, and existing safety tests stay green.

## Handoff and stop

Run the relevant checks in AGENTS.md, including make smoke. Commit only your checkpoint work.
If a new origin is configured, open a `[W3-C1]` PR to main.
Otherwise report your branch, commit SHA, exact checks and any gaps; do not configure a remote.
If you need a shared interface/dependency change, describe the exact request to integration instead
of changing someone else's files. Stop after handoff. Do not start C2 until integration merges C1
and gives you the next prompt. Keep this branch/worktree for the later checkpoints.
