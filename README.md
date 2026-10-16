# Relay

**Disaster recovery that gets smarter every time.**

Relay connects people affected by disasters with organizations that can help, follows up until
assistance is verified, and uses reviewed recovery lessons to inform the next response.

Two connected views:

- **Relay Response:** needs -> organization commitments -> follow-up -> verified resolution.
- **Relay Intelligence:** verified outcomes -> reviewed lessons -> evidence-backed recommendations.

## Demo we are building

A survivor reports a need. A seeded relief organization claims it and reports delivery. A consenting
survivor tells the ElevenLabs agent the help did not arrive, so Relay reopens the request for a human.
After a verified resolution, a coordinator reviews a lesson. A similar request in a second disaster
retrieves that lesson. Arize compares decisions with and without the historical knowledge.

SurrealDB will store requests, organizations, commitments, calls, outcomes, and lesson relationships.
ElevenLabs handles follow-up voice. Arize measures decision quality; it does not decide ground truth.
Recommendations need human review. Calls remain opt-in, with fixed disclosure and emergency handling.

## Current backend

Four backend subagents have implemented the recovery API, genuine local SurrealDB storage,
safe receipt-verification calls, a two-disaster fixture, and historical-lesson evaluation.
[STATUS.md](STATUS.md) records their work and integration results. The UI is being built separately.
No Git remote or hosting project is configured, and no real calls are started automatically.

```bash
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
make smoke PYTHON=.venv/bin/python
make demo-surreal PYTHON=.venv/bin/python
make serve PYTHON=.venv/bin/python

cd ui
npm ci
npm run dev -- --hostname 127.0.0.1
```

The backend serves `http://127.0.0.1:8787`: start with `GET /disasters` and
`GET /runs/demo-current/board`. The new UI should use the payloads in
[contracts/demo.md](contracts/demo.md) and API details in [api/RECOVERY.md](api/RECOVERY.md).
The existing `/console` still uses mock data until the separate UI work is connected.

`make demo-surreal` is a resettable in-memory SurrealDB rehearsal with a scripted survivor,
not a real phone call. `make serve` persists to the ignored `.relay-demo` database directory.
Only one API process may open that embedded database. See [db/RECOVERY.md](db/RECOVERY.md).
The prior offline scenario is still available with `make demo-legacy`.

Decisions and measured comparisons currently use an explicit rule-based baseline and three
synthetic held-out cases. No real-world accuracy improvement is claimed. ElevenLabs browser/provider
adapters and optional Arize aggregate tracing require fresh credentials for live use; neither live
calling nor hosted Arize ingestion has been verified.

## Agent coordination

The integration agent spawns backend subagents in isolated worktrees, reviews and integrates their
commits, and maintains [STATUS.md](STATUS.md). The former manual worker/PR approval pauses are retired.
The user owns UI development in a separate AI chat; backend agents must leave `ui/` alone.

Future integrations such as authorized emergency dispatch, radio, and 211 feeds are outside this demo.
