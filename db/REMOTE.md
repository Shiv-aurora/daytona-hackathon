# Remote SurrealDB (Cloud or self-hosted)

1. In SurrealDB Cloud create an instance; under Authentication create a user (root, or a namespace/database owner). Copy the `wss://...` endpoint.
2. In local `.env` (never commit it) set `SURREAL_URL=wss://<instance>` (`/rpc` optional), `SURREAL_NAMESPACE`, `SURREAL_DATABASE`, `SURREAL_USERNAME`, `SURREAL_PASSWORD`. Blank `SURREAL_URL` = embedded `surrealkv://.relay-demo`.
3. Run `make check-surreal` (connect, sign in, apply schema twice, write/read/delete a scoped probe). Fix any FAIL before starting the API.
4. `make serve` seeds `data/demo/seed.json` once (first start); `python -m db.recovery --reset` reseeds Relay tables only.
5. `from db.remote import surreal_status` returns `{"configured", "mode", "reachable"}` (TCP check, cached 10s) for `/health`.

Handled differences: no file lock (revision-checked `UPDATE ... WHERE revision=$n` arbitrates writers; replay ledger stays in the run row); sign-in tries root, then namespace, then database scope; one reconnect+retry if the websocket drops; a concurrent first-seed loser keeps the winner's data.
Known limits: not yet run against a live instance; each read fetches the whole run snapshot (latency scales with round-trip time); one reconnect only, no TLS pinning; remote hosts are accepted only through `SURREAL_URL` (`allow_remote`), the default constructor still rejects non-local endpoints.

## Local server (no account)
Download the release binary from github.com/surrealdb/surrealdb/releases (tested: v3.3.0, macOS arm64) and run
`SURREAL_USER=root SURREAL_PASS=<pw> surreal start --bind 127.0.0.1:8000 surrealkv://$HOME/.relay-surreal/data`.
In `.env`: `SURREAL_URL=ws://127.0.0.1:8000`, namespace/database `relay`, `SURREAL_USERNAME=root`, `SURREAL_PASSWORD=<pw>`.
Then `make check-surreal` and `make serve`. Note: SDK 2.0 returns no rows for BEGIN..COMMIT on server 3.x, so writes are confirmed by read-back.
