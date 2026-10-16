# W2: copy this prompt into its worker chat

You are Relay W2. Work only in `/Users/shivamarora/Documents/Code/relay-w2-recovery` on `codex/w2-recovery`.
Read AGENTS.md, WORKER_PLAN.md and contracts/demo.md before coding. You own api/, runtime/, and intake/.
This is a hackathon demo: build the smallest useful implementation and avoid unrelated refactors.

## C1 only

Implement the new demo API in contracts/demo.md using an in-memory RecoveryStore with the exact shared
signatures. Keep the retained scenario tests passing. Split one submitted report into separate food /
supplies requests; apply the existing emergency check before model extraction. Support board loading,
claim, delivery report, and explicit human verification; delivery alone must not resolve anything.
Start with deterministic extraction or a mockable model; no new agent framework, production auth,
emergency-feed connectors, or direct DB driver imports. The seeded org selector is demo-only.
Acceptance: a submitted report -> two requests -> one claim -> reported delivery -> failed verification
reopens the request, with an event for each action. A duplicate/foreign-run action cannot corrupt state.
Use W1's storage protocol, but do not edit db/ or memory/.

## Handoff and stop

Run the relevant checks in AGENTS.md, including make smoke. Commit only your checkpoint work.
If a new origin is configured, open a `[W2-C1]` PR to main.
Otherwise report your branch, commit SHA, exact checks and any gaps; do not configure a remote.
If you need a shared interface/dependency change, describe the exact request to integration instead
of changing someone else's files. Stop after handoff. Do not start C2 until integration merges C1
and gives you the next prompt. Keep this branch/worktree for the later checkpoints.
