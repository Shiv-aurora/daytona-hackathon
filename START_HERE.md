# Current Relay build

The integration chat on `main` runs backend subagents and maintains `STATUS.md`.
The user is handling the UI with a separate AI agent. Do not edit `ui/` in backend work.

Read `AGENTS.md`, `STATUS.md`, and `contracts/demo.md`. Worker checkpoints and manual PR
approval pauses from the earlier plan are superseded by the current subagent assignments.

Backend ownership stays isolated: storage uses `../relay-w1-surrealdb`, recovery/API uses
`../relay-w2-recovery`, calls uses `../relay-w3-calls`, evaluation/data uses
`../relay-w5-evaluation`. Never switch branches in another agent's worktree.

Run the backend with `make serve PYTHON=.venv/bin/python`; inspect `/disasters` and
`/runs/demo-current/board`. Run a resettable, scripted no-network rehearsal with
`make demo-surreal PYTHON=.venv/bin/python`. Setup and live-service limitations are in README.md.
