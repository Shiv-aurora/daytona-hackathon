# W1: copy this prompt into its worker chat

You are Relay W1. Work only in `/Users/shivamarora/Documents/Code/relay-w1-surrealdb` on `codex/w1-surrealdb`.
Read AGENTS.md, WORKER_PLAN.md and contracts/demo.md before coding. You own db/ and memory/.
This is a hackathon demo: build the smallest useful implementation and avoid unrelated refactors.

## C1 only

Implement RecoveryStore from contracts/demo.py using SurrealDB. Keep the existing offline regression
adapters usable. Add a small schema, fixture loader/reset command and tests. C1 must support the board,
create request, atomic organization claim, delivery report, and survivor/human verification. Preserve
run/disaster isolation and idempotency. Use the fixture path from W5; until it lands, use a tiny local
test fixture with the same fields. Do not edit data/. Request the pinned SDK dependency from integration.
Do not build a general database abstraction, production infrastructure, or another graph framework.
Acceptance: a fresh local DB loads, one request completes the expected state transitions, concurrent
claims have one winner, a repeated write is a no-op, and another run cannot read or mutate it.

## Handoff and stop

Run the relevant checks in AGENTS.md, including make smoke. Commit only your checkpoint work.
If a new origin is configured, open a `[W1-C1]` PR to main.
Otherwise report your branch, commit SHA, exact checks and any gaps; do not configure a remote.
If you need a shared interface/dependency change, describe the exact request to integration instead
of changing someone else's files. Stop after handoff. Do not start C2 until integration merges C1
and gives you the next prompt. Keep this branch/worktree for the later checkpoints.
