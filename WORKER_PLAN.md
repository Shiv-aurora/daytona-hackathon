# Relay demo checkpoints

## The demo story

1. A report creates separate requests for food and supplies.
2. A relief organization claims a request and promises a delivery time.
3. The organization reports delivery; the request becomes `awaiting_verification`.
4. An opted-in survivor tells the ElevenLabs agent the delivery did not arrive.
5. Relay reopens the request, records the evidence, and flags human follow-up.
6. Receipt is later verified; a coordinator approves a de-identified lesson.
7. A similar request in a second disaster retrieves that lesson with its source outcome.
8. Arize shows a controlled comparison with historical lessons enabled and disabled.

## Three checkpoints only

| Worker | C1: useful piece | C2: connect the pieces | C3: make the demo reliable |
| --- | --- | --- | --- |
| W1 SurrealDB | Implement RecoveryStore on a fresh local SurrealDB; seed/reset fixture and atomic claims | Persist calls, verification, and reviewed lessons with graph links; restart-safe reads | Fix run/time isolation, duplicate writes, and reset issues found in the full demo |
| W2 Recovery | Implement the board API and request/claim/delivery/verification flow against an in-memory RecoveryStore | Wire SurrealDB, call scheduling/results, lesson recommendations, and real fixture | One reproducible demo command; fix deadline/retry and integration failures |
| W3 Calls | Adapt existing safety-first agent to request verification; fake transport + real ElevenLabs browser voice path | Add outbound telephony if new credentials/number are provided; verified webhook mapping and idempotent call results | Rehearse with an explicitly consenting demo recipient; preserve a clearly labeled typed/scripted fallback |
| W4 UI | Redesign the demo workspace against contract-shaped mocks | Wire the backend API, org actions, calls, lessons, and measured evaluation results | Walk the whole story, responsive/error states, obvious demo labels |
| W5 Evaluation | Two-disaster synthetic fixture, labeled expected results, deterministic scoring and experiment runner | Arize traces/experiments; compare same model and inputs with lessons off/on | Freeze demo seed/results, report honest wins/regressions, write the presentation walkthrough |

C1 workers may work independently using the shared contract and mocks. W5 owns `data/demo/`.
W1 loads the fixture from a path supplied by integration; it does not edit W5 data.
Merge each wave in this order: **W5 fixture -> W1 storage -> W2 workflow -> W3 calls -> W4 UI**.
If W3's API hookup is needed, integration coordinates the W2/W3 merge; W3 never edits `api/`.
C3 consists of fixes for the demo, not new features. No automatic deployments or external account setup.

## PR / review cadence

- C1 is the initial prompt in each worker brief. One checkpoint equals one PR/review batch.
- Keep each worker on its dedicated branch for the whole project.
- Before a checkpoint, merge the latest reviewed `main` into the worker branch.
- Commit and open `[W#-C#] result` against the new remote when available. Include exact checks, gaps,
  and any shared interface change request. With no remote, report the commit SHA instead.
- Stop after handing off. Integration reviews scope, tests, and the demo action before merging.
- After merge, integration sends a short C2/C3 prompt describing only the next work and acceptance test.
- Request shared dependency/config changes in the PR; integration applies them on `main`.

## Handoff gate

Python compilation, Ruff, full pytest, and `make smoke` must pass for Python changes.
UI changes run the committed lockfile install plus lint/test/build.
Integration must also walk the relevant UI action through API -> storage -> rendered result.
Do not delete failing safety or isolation tests. If a service credential is missing, report it and
use the labeled offline fallback; never claim a live integration was verified.

## Demo boundaries

Two synthetic disasters, three seeded organizations, a handful of survivors and requests.
Seeded organization selection is enough; do not build production accounts or real agency integrations.
No real emergency feeds, household ranking, medical advice, automatic lesson approval, or autonomous calls.
A delivery report is not proof of receipt. Unanswered calls remain unverified.
Historical lessons carry source outcome IDs and applicability limits. Compare on held-out second-disaster
cases, and keep the model, prompts except injected context, inputs, and time cutoff the same.
No invented improvement percentages. Report regressions and the synthetic sample size.
