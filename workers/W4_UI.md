# W4: copy this prompt into its worker chat

You are Relay W4. Work only in `/Users/shivamarora/Documents/Code/relay-w4-ui` on `codex/w4-ui`.
Read AGENTS.md, WORKER_PLAN.md and contracts/demo.md before coding. You own ui/.
This is a hackathon demo: build the smallest useful implementation and avoid unrelated refactors.

## C1 only

Completely redesign the coordinator console around contracts/demo.md using contract-shaped mocks.
Build Response, Organizations, Calls, and Intelligence views with a disaster selector. Response has a
shared request board, an org selector labeled as demo access, claim/delivery actions, and a detail
drawer showing commitment, survivor evidence and verification separately. Calls shows consent and
follow-up results. Intelligence shows reviewed lessons with source outcomes and an honest unmeasured
state until evaluations exist. Do not invent success metrics or live emergency integrations.
Use a calm, readable operations UI with light surfaces and restrained teal/status colors; keep keyboard
and small-screen access. Preserve functional safety/run-isolation coverage while porting old components.
C1 is a clickable mock walkthrough; C2 connects the API. Do not add a database driver, host/deploy,
build production auth, or edit other worker folders. Use npm ci and run lint/test/build.
Acceptance: a user can walk report -> claim -> delivery -> failed verification/reopened, inspect a call,
and see a historical lesson from a second disaster. Clearly label all simulated data and actions.

## Handoff and stop

Run the relevant checks in AGENTS.md, including make smoke. Commit only your checkpoint work.
If a new origin is configured, open a `[W4-C1]` PR to main.
Otherwise report your branch, commit SHA, exact checks and any gaps; do not configure a remote.
If you need a shared interface/dependency change, describe the exact request to integration instead
of changing someone else's files. Stop after handoff. Do not start C2 until integration merges C1
and gives you the next prompt. Keep this branch/worktree for the later checkpoints.
