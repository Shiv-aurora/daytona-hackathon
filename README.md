# Relay

**An AI-powered disaster recovery network that follows up on survivors, coordinates human assistance, and learns from every storm.**

Built for Daytona HackSprint #6 (with Arize AI).

- **Live demo:** https://relay-demo-swart.vercel.app (runs on seeded, in-browser data; no backend needed)
- **Stack:** Next.js, Python (stdlib API), SurrealDB, Daytona, ElevenLabs, Arize

## Inspiration

A hurricane passes. Emergency crews rescue people, restore roads, and respond to life-threatening incidents. Weeks later,
thousands may still face power outages, missing medication, damaged homes, inaccessible supplies, or assistance that was
promised but never arrived. The initial emergency might be over; the consequences are not.

Recovery runs through a fragmented network of agencies, nonprofits, volunteers, and case managers. A reported delivery is
not necessarily a received delivery. A closed incident is not a resolved need. And lessons from one disaster rarely reach
the next.

**What if every disaster had an AI recovery workforce that kept following up, kept connecting people to help, and got
smarter after every storm?**

## What it does

Relay is multi-agent disaster recovery coordination. A central orchestrator keeps a picture of unresolved needs, and AI
helpers work alongside human relief organizations toward verified resolution.

1. **Turn disaster reports into actionable needs.** A flooded-home report becomes separate requests (food,
   transportation, electricity, repairs), each with a status, a history, and a potential responsible organization.
   Safety-critical or uncertain cases escalate to humans. The prototype uses synthetic reports; future authorized
   integrations could include 911 dispatch, 211, emergency communications, and utility updates.
2. **Coordinate the human response.** A shared dashboard lets organizations view, claim, and report progress on requests.
   Marking something delivered does not close the case: Relay tracks *reported delivery* separately from
   *recipient-confirmed receipt*.
3. **An AI helper workforce.** Helpers handle intake, triage, organization matching, follow-up, and verification.
   Daytona runs helper tasks in isolated sandboxes with scoped, de-identified data, so helpers propose next actions
   without unrestricted survivor access and without making sensitive decisions. ElevenLabs is the voice layer: with
   consent, an AI follow-up agent contacts a survivor, checks a reported need, and records whether help was received or
   needs human attention. Longer term, helpers could retrieve verified information on outages, assistance, shelters, and
   transportation.
4. **Keep cases from silently disappearing.** An organization reports groceries delivered. Relay follows up. The
   resident says they never arrived because the road was inaccessible. The request is reopened, becomes visible to a
   coordinator, and an alternative handoff is arranged. Only confirmed assistance or explicit human verification
   resolves a request.
5. **Learn from one storm to improve the next.** SurrealDB keeps persistent recovery history: needs, commitments,
   follow-ups, verified outcomes, and human-reviewed lessons. When a similar problem appears in a future disaster, Relay
   retrieves relevant lessons by case conditions and recommends a more informed response. For example, if inaccessible
   delivery locations repeatedly caused failures in one flood, the next response verifies accessible handoff points
   first. That is institutional memory across disasters, not just closed tickets.

## Try the demo

1. Open https://relay-demo-swart.vercel.app (it redirects to `/live`).
2. Click **Start demo** on the Live page to run the report -> request -> claim -> delivery -> verification -> lesson flow.
   There is also a safety demo that shows emergency escalation to a human.
3. Open the **Calls** page (`/calls`) and use the ElevenLabs **Relay AI Helper** voice widget to talk to the follow-up
   agent (needs a microphone; the page must be on the agent's domain allowlist).
4. Other pages: `/response` (board), `/organizations`, `/intelligence` (lessons and comparison).

The hosted demo runs entirely in the browser on seeded data. The UI shows "Simulated" mode.

## How we built it

Four sponsor technologies, each with a specific job:

- **Daytona:** isolated helper execution in disposable sandboxes. Helpers return suggested actions; sensitive contact
  information is kept out of sandbox payloads (`helpers/`, see [helpers/DAYTONA.md](helpers/DAYTONA.md)).
- **ElevenLabs:** consent-checked voice sessions, structured conversation handling, and post-call processing
  (`calls/`, see [calls/LIVE.md](calls/LIVE.md) and [calls/WIDGET.md](calls/WIDGET.md)).
- **SurrealDB:** the system of record for cases, organization commitments, calls, outcomes, and reviewed lessons
  (`db/`).
- **Arize:** evaluation of Relay's decisions and of whether historical lessons actually help, via a with-versus-without
  comparison (`eval/`).

### Architecture

```
Next.js UI (ui/)  ->  Python stdlib HTTP API (api/)  ->  SurrealDB (db/)
                          |        |
                          |        +--> Daytona helper sandboxes (helpers/): intake, triage, matcher, follow-up, verifier
                          +-----------> ElevenLabs agent (calls/): consent-gated voice follow-up, post-call webhook
Arize (eval/): evaluation and tracing of decisions, opt-in
```

- The **UI** talks to the API when `NEXT_PUBLIC_RELAY_API_URL` is set; otherwise it uses a simulated in-browser backend
  (this is what the hosted demo does).
- The **API** (`python -m api.server`) uses only the Python standard library for HTTP, and exposes the recovery board,
  helper, voice, and background-data routes. Every operational read and write carries a `run_id` and `disaster_id`, and
  every mutation emits a `system_event`.
- **SurrealDB** runs embedded (`surrealkv://`), as a local server, or remote (Cloud or self-hosted).
- **Daytona** sandboxes run helper roles; without a Daytona key a local stand-in is used.
- **Arize** tracing is optional and de-identified. It lives on the branch `codex/b10-arize-basic` (not merged here) and
  has not been verified against a live Arize project.

## Safety principles

- **Calls require confirmed opt-in.** No consent, no call.
- **The disclosure is fixed and code-owned.** The AI-identity disclosure is not generated by a model.
- **Emergency detection and human escalation run before any LLM.**
- **Delivery is not resolution.** An organization reporting delivery never closes a request; verification is recorded
  separately.
- **Only reviewed, de-identified lessons cross disasters.** Survivor records never leave their run.
- **Humans decide.** Work is sorted by deadlines and status. Relay does not rank people and gives no medical advice.
- **Isolation and replay.** Reads and writes are scoped by `run_id` and `disaster_id`, with replay and time-cutoff tests.

## Honest status and limitations

- The demo uses **synthetic, seeded data**. Households, calls, and outcomes are simulated.
- The with-versus-without lesson comparison is **n = 3** on a synthetic recorded fixture. It illustrates the method; it
  is not evidence of real-world effectiveness.
- The SurrealDB backend also holds **real NYC 311 requests from Hurricane Ida (Queens, 2021), 1,042 rows**, loaded as
  read-only background context with no households or contact fields (`scripts/load_background_311.py`). This is **not
  shown in the hosted demo**.
- The ElevenLabs widget uses ElevenLabs' **built-in LLM**, so in the widget demo emergency handling is a prompt rule, not
  code. A **code-owned custom-LLM bridge** (every turn passes the emergency check before any model) is available via
  `calls.voice.setup_agent` / `make agent-apply ARGS="--yes --custom-llm"`, but needs a public tunnel.
- The **post-call webhook needs a public tunnel** (ngrok or cloudflared) to reach a local API.
- Arize tracing is on `codex/b10-arize-basic` and **not verified live**.
- Remote SurrealDB was not run against a live instance in docs (see [db/REMOTE.md](db/REMOTE.md)).
- The callback number in the disclosure is fictional: `+1 212 555 0100`.
- No real agency integrations (911, radio, 211), no production auth. The organization selector in the UI is a demo
  control, not authorization.

## Run it locally

Prerequisites: Python 3 and Node >= 20.9. Credentials go only in a local, git-ignored `.env`; copy the empty templates
and fill in only what you need. Blank values run fully offline.

```bash
# Backend
cp .env.example .env            # optional; blank = embedded SurrealDB, local stand-ins
uv venv .venv
uv pip install --python .venv/bin/python -r requirements.txt -r requirements-dev.txt
make smoke PYTHON=.venv/bin/python        # safety, runtime, scenario and integration tests
make demo-surreal PYTHON=.venv/bin/python # scripted in-memory SurrealDB rehearsal (no real call)
make serve PYTHON=.venv/bin/python        # API on http://127.0.0.1:8787, seeds data/demo/seed.json on first start
make check-surreal PYTHON=.venv/bin/python  # connectivity check for your SURREAL_* settings

# UI
cd ui
cp .env.example .env.local      # optional; blank = simulated in-browser backend
npm ci
npm run dev -- --hostname 127.0.0.1       # http://127.0.0.1:3000
npm run lint && npm test && npm run build
```

To point the UI at the local API, set `NEXT_PUBLIC_RELAY_API_URL=http://127.0.0.1:8787` in `ui/.env.local`.

Other targets: `make demo` (in-memory), `make check-daytona`, `make check-elevenlabs`, `make agent-inspect`,
`make agent-simulate`, and `make agent-apply` (dry run unless `ARGS="--yes"`). Remote SurrealDB setup is in
[db/REMOTE.md](db/REMOTE.md); Vercel deployment is in [DEPLOY.md](DEPLOY.md). More detail: [STATUS.md](STATUS.md),
[contracts/demo.md](contracts/demo.md), [api/RECOVERY.md](api/RECOVERY.md), [db/RECOVERY.md](db/RECOVERY.md).

## Challenges

- **Delivery versus receipt.** Modeling "delivered" and "resolved" as separate states, so no single report can close a
  case, shaped the whole data model.
- **Safety before intelligence.** Keeping the disclosure and emergency escalation in code, ahead of any LLM, while still
  getting a natural-sounding voice agent.
- **Cross-disaster memory without leaking people.** Lessons must help the next storm without exposing survivors, so only
  reviewed, de-identified lessons cross run boundaries, and helpers see scoped payloads only.
- **Honest evaluation.** Comparing decisions with and without historical lessons on small synthetic data, and being
  clear about what that can and cannot show.
- **Integrating four services in a hackathon.** Each integration has an offline stand-in so the demo and tests run
  without keys or paid calls.

## What's next

- Authorized intake integrations: 911 dispatch, 211, emergency communications, utility updates.
- Helpers that retrieve verified information on outages, assistance, shelters, and transportation.
- Verify Arize tracing live and run the lesson comparison on larger, real recovery data.
- Run the code-owned custom-LLM voice bridge as the default, with a hosted webhook endpoint.
- Real authentication and per-organization authorization.
- A coordinator workflow for reviewing and publishing lessons across many disasters.
