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

## Current baseline

The existing console and recovery scenario run offline. Live database connectors have been removed.
The five worker branches implement the new demo; those integrations are not complete yet.
No Git remote or hosting project is configured. No old secrets or history are retained.

```bash
python3 -m pip install -r requirements-dev.txt
make smoke
python3 -m runtime.demo --store local --score

cd ui
npm ci
npm run dev -- --hostname 127.0.0.1
```

Open `/console`. The existing UI uses mock data until the redesigned UI and backend are merged.
The in-process reference API starts with `python3 -m api.server`; its data resets on restart.

## Worker chats

Start with [START_HERE.md](START_HERE.md), then your file in [workers/](workers/).
[WORKER_PLAN.md](WORKER_PLAN.md) defines the three merge checkpoints and demo acceptance criteria.
[contracts/demo.md](contracts/demo.md) freezes the small integration boundary for all five workers.

Future integrations such as authorized emergency dispatch, radio, and 211 feeds are outside this demo.
