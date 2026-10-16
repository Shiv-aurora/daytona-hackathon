# W5: copy this prompt into its worker chat

You are Relay W5. Work only in `/Users/shivamarora/Documents/Code/relay-w5-evaluation` on `codex/w5-evaluation`.
Read AGENTS.md, WORKER_PLAN.md and contracts/demo.md before coding. You own eval/ and data/.
This is a hackathon demo: build the smallest useful implementation and avoid unrelated refactors.

## C1 only

Create data/demo/ with two synthetic disasters, three organizations, a handful of survivors and
requests, one missed-delivery story, one verified resolution, and an approved historical lesson with
source outcome IDs. Follow contracts/demo.md exactly; do not attach synthetic survivors to real people.
Add labeled held-out second-disaster cases and eval.recovery.run_comparison(cases, decide). Run the
same cases with lessons disabled/enabled under the same model/settings. Score request extraction,
organization compatibility, false closure, evidence grounding, and relevant lesson use. Keep old
scorer/isolation tests passing. C1 is fixture + deterministic runner; C2 adds Arize tracing/experiments
and real decisions from W2. Request dependency changes from integration; do not edit root config.
Acceptance: resettable fixture, deterministic scores on known examples, separate run IDs per variant,
no future/test-label leakage into decisions, honest unmeasured values where necessary, and no invented
improvement percentages. Finish with a short demo walkthrough under data/demo/. No production analytics.

## Handoff and stop

Run the relevant checks in AGENTS.md, including make smoke. Commit only your checkpoint work.
If a new origin is configured, open a `[W5-C1]` PR to main.
Otherwise report your branch, commit SHA, exact checks and any gaps; do not configure a remote.
If you need a shared interface/dependency change, describe the exact request to integration instead
of changing someone else's files. Stop after handoff. Do not start C2 until integration merges C1
and gives you the next prompt. Keep this branch/worktree for the later checkpoints.
