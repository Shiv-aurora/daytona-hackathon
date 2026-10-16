# Start here

Five persistent worker chats build one demo. The integration chat stays on `main`.

| Worker | Worktree (beside this repo) | Prompt |
| --- | --- | --- |
| W1 | `../relay-w1-surrealdb` | [SurrealDB](workers/W1_SURREALDB.md) |
| W2 | `../relay-w2-recovery` | [Recovery workflow/API](workers/W2_RECOVERY.md) |
| W3 | `../relay-w3-calls` | [ElevenLabs calls](workers/W3_CALLS.md) |
| W4 | `../relay-w4-ui` | [UI](workers/W4_UI.md) |
| W5 | `../relay-w5-evaluation` | [Arize and demo data](workers/W5_EVALUATION.md) |

Open each worker chat in its own worktree and paste its prompt. Read `AGENTS.md` and
`contracts/demo.md` first. Build C1 only; do not start C2 until integration merges C1 and sends the next prompt.
The branches are local until the owner creates a new GitHub repository. Never reconnect the original.
No worktree shares dependencies or local secret files automatically; install what your worker needs.
