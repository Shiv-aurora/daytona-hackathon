# Local SurrealDB demo

Install root `requirements.txt` (pins `surrealdb==2.0.0`). No Docker or cloud
account is needed: the official SDK embeds a genuine SurrealDB engine.

```sh
python3 -m db.recovery --seed data/demo/seed.json --reset
```

`SurrealRecoveryStore.from_env()` reads `.env` and process environment using the
existing `SURREAL_URL`, `SURREAL_NAMESPACE`, `SURREAL_DATABASE`,
`SURREAL_USERNAME`, and `SURREAL_PASSWORD` names. Blank values select a fresh
persistent local `surrealkv://.relay-demo` database. `mem://` creates an ephemeral
database for tests. Explicit server endpoints must be local HTTP/WS addresses.
No remote service is contacted by default. Never add credentials to a fixture.

The first seed initializes the database; later startups preserve interactions.
`--reset` atomically replaces only the three `relay_demo_*` tables. Close the
running API before executing the seed/reset CLI, then restart it.

Run **one API process** per embedded database. Embedded SDK connections to the
same file maintain independent cached views; a filesystem lock deliberately
rejects a second owner. A single store supports concurrent threads; its lock and
revision-checked SurrealDB transaction preserve claim/state/replay consistency.
Close the store at server shutdown before reopening the database.

This is a tiny demo aggregate, not a normalized production graph: each run owns
one snapshot containing its requests, survivor data, evidence, events and replay
ledger. W2's reference adapter supplies the shared transition/validation rules.
A conditional database update commits them together. Explicit lesson approval
publishes a whitelisted public lesson in that same transaction. Source outcome
IDs and applicability conditions are also native fields on the public lesson
record. Survivor records are never loaded across runs for history retrieval.
Each run freezes `knowledge_cutoff` during initial seeding unless supplied in the
fixture; both lesson creation and review must precede that cutoff. New reviews
become available to subsequently seeded runs rather than rewriting past context.

Verified locally with real embedded SurrealDB: completion needs receipt evidence,
missed delivery reopens, no-answer stays unverified, payload-sensitive replay,
concurrent claims, database close/reopen, run isolation, contact privacy, reviewed
lesson publication/cutoffs, and W5's two-disaster fixture.

Primary SDK/query references:
- https://surrealdb.com/docs/languages/python/installation
- https://surrealdb.com/docs/reference/query-language/statements/update
