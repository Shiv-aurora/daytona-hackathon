# Daytona helpers

- Get a key: sign in at https://app.daytona.io, open Dashboard > API Keys, create one.
- Put it in your local `.env` (never commit): `DAYTONA_API_KEY=...`; optional `DAYTONA_API_URL`, `DAYTONA_TARGET`.
- Install the SDK: `pip install -r requirements.txt` (the `daytona` package is imported lazily).
- Verify live: `make check-daytona` creates a sandbox, runs `print('relay-helper-ok')`, deletes it; exit 0 means PASS.
- With the key set, `POST /runs/{run}/helpers/spawn` uses Daytona (`provider: "daytona"`); without it, a local subprocess (`provider: "local"`).
- `GET /health` shows `daytona: {configured, provider}` (no network call).
- Real: sandbox create, code execution, delete (always in a `finally`), concurrency cap (`DAYTONA_MAX_SANDBOXES`, default 3).
- Simulated: the follow-up helper rehearses a scripted call transcript; no phone call, model, or ElevenLabs use.
- Helpers receive only ids, categories, statuses and capabilities; never names or contact details.
- Helpers only propose. They never change a request, verify a delivery, or resolve anything.
- Offline tests use fake clients; the real SDK path is untested until you run the checker.
