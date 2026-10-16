# data/

Scenario data for Relay, built to the Relay Data Spec. Owner: W5. Stdlib-only Python.

```bash
python data/pull_311.py types     # 1a: complaint types + flood ZIP ranking (prints)
python data/pull_311.py extract   # 1b: raw 311 rows -> data/raw/ (gitignored)
python data/load_311.py           # real backbone -> data/derived/
python data/gen_scenario.py       # -> data/scenarios/s1/
python data/validate.py           # THE Scenario 1 gate: spec §7 + C2 integration rules + identical regeneration
python data/gen_sample.py         # -> data/sample_data/ (1-week fixture, no network needed)
pytest -q data intake             # fixture gates + integration with the merged W1/W2/W3/W4 code
```

`data/raw/` and `data/derived/events_311.jsonl` (~14 MB) are gitignored; regenerate them with the first three
commands. Everything else in `derived/` is committed, so tests and `gen_sample.py` run offline.

**Real backbone:** NYC 311 (`erm2-nwe9`), Queens, Sep 1 – Oct 13, 2021, filtered and time-shifted only.
ZIPs: 11354 11355 11368 11372 11373 11377 (spec) + 11369 11370 11375 11358 11432 (top Ida flood ZIPs from 1a).
Complaint types: `config/complaint_types.json`.

**Contract:** files follow `schemas.py` on `main`. `ts` = **hours since scenario day 0** = storm start,
2021-09-01T20:00 New York (a Wednesday); `scenario.json` has `day0` and `end_ts` (1032 h = days 0–42). Events are
keyed by `_id`, carry `run_id: "scenario"` (scenario input), and are in the runtime's `(ts, _id)` cursor order. Every
event also has `ts_real`. The generators think in days internally; `data/contract.py` converts at write time.

On screen: **"Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated."**

## scenarios/s1/

| File | Visible to Relay? | Notes |
|---|---|---|
| `events.jsonl` | **yes** (strip `origin`) | `schemas.Event` + spec §2a fields; sorted by `(ts, _id)`; no `household_id` |
| `registry.json` | **yes** | `schemas.RegistryEntry` (incl. `first_name`) + `registered_ts`, `name`, `address`, `registered_by`, `note` (Relay needs these to match registry to events) |
| `households_truth.json` | no | spec §2b; `timeline` uses the closed fact set (`ts`, `due_ts`, `until_ts` in hours); each fact has `fid` for `facts_disclosed` |
| `personas.json` | no | spec §4d prompt with `{current_day}` and `{timeline_facts}` left to fill (facts with `day <= current_day`) |
| `needles.json` | no | `schemas.Needle`: caught if an escalation fires before `deadline` citing ≥2 `required_event_ids`; `danger_at`, `response_hours` |
| `decoys.json` | no | an escalation citing any `event_ids` is false |
| `promises.json` | no | `schemas.TruthPromise` `{household_id, source_event_id, made_ts, due_ts, status, status_ts}` + `promise_id`, `who`, `what`, `evidence_event_ids` |
| `event_truth.json` | no | event_id → household_id + structured fact (null for real 311) |
| `contact_truth.json` | no (call simulator / evaluator only) | per opted-in household: `no_answer` windows and the scripted `script` lines a connected call hears; see `data/contact.py` |
| `REVIEW.md` | — | human review sheet: every needle and decoy with its visible events and truth |

**Frozen Scenario 1 (W5-C2):** 150 households, 60 registered, 10 needles, 11 decoys, 1,520 events (70% real),
revision `dbf318e41947f813` (sha256 of `events.jsonl`, stamped on `scenario.json`, needles, decoys and contact truth).

- **Identity:** every household has one `identity_address` (number + short street, plus the unit only when another
  household shares the building). The registry records it. Needle required events and decoy events use address forms
  that W2's normalized matcher resolves to it; background events keep harder variants for fuzzy matching.
- **Silent households:** required evidence is the 311 report + the registration visit note (person-linked, two
  services) + the block outage. `contact_truth.json` makes the silence reproducible: each goes unanswered from before
  registration + 72h through its deadline.
- **Calls:** never pre-generated and never scenario input. `data.contact.ScriptedResident` is a W3 `Transport` over
  contact truth, so baseline and Relay hear the same residents. Under W3-C2 a request must be queued in the
  `CallLedger` (W1 -> W2 `schedule_call`) before `CallAgent(..., ledger).start` places it; W3 writes each result
  under the calling run's id.
- **Filing from visible data:** `data/filing.py` walks the events through W2's matcher with only the visible registry
  seeded and files a household from any named+addressed report that matches nobody. Every unregistered needle
  (`s1_n_02`, `03`, `05`, `06`, `07`) is filed that way before its deadline, and >=2 required events from >=2 services
  then resolve to it; `validate.py` and `data/tests/test_integration.py` check this without hidden truth.

Hero (`s1_n_01`, pinned in `test_mrs_chen_demo_path_is_pinned`): Mrs. Mei Chen, 82, 41-22 Hollow Oak Ln (basement),
Sunnyside 11104, registered at h 43.0.

| Beat | Event / truth | h | Wall clock |
|---|---|---|---|
| Visit note: son Wei coming Tuesday | `s1_e_000376` (visit_note) | 42.6 | Fri Sep 3 14:36 |
| Promise lapses (end of sim day Tue) | promise due | 144.0 | Tue Sep 7 20:00 |
| Calls go unanswered | contact truth no_answer | 145.5 → 493.0 | Tue 21:30 → Wed Sep 22 09:00 |
| Con Ed pushes the block to Sep 13+ | `s1_e_000818` (utility) | 158.7 | Wed Sep 8 10:43 |
| Flooded meter, no one answered the door | `s1_e_001073` (crew) | 303.0 | Tue Sep 14 11:00 |
| She answers: "My son never came…" | contact truth script | 493.0 | Wed Sep 22 09:00 |
| Deadline / danger | needle | 528 / 600 | Thu Sep 23 20:00 / Sun Sep 26 20:00 |

## Frozen demo seed (W5-C3)

Scenario 1 is the judge/demo dataset and is **frozen**. `scenarios/s1/manifest.json` pins the scenario id, seed 21,
revision `dbf318e41947f813`, `day0`, `end_ts`, the canonical label, the SHA-256 of every artifact the runtime,
evaluator, call simulator or demo reads, and Mrs. Chen's visible anchors (registry `s1_h_001`; `s1_e_000376`
visit note h 42.6, `s1_e_000818` utility delay h 158.729, `s1_e_001073` crew h 303.0). It holds nothing that is not
already in `registry.json` or `events.jsonl`.

- `python data/freeze.py` verifies the committed files against the manifest; `python data/validate.py` runs it too,
  plus regeneration, revision stamps, reachability of all 10 needles from visible data, decoy resolutions, the
  Wang/Gonzalez traps, real/synthetic separation, privacy, opt-in-only contact truth and the label.
- `python data/gen_scenario.py` refuses to overwrite `scenarios/s1/`; regenerate into another directory to compare.
- A data defect that blocks the live E2E path is reported to the PM first. Only after sign-off: regenerate with
  `--force`, re-pin with `python data/freeze.py --write`, and ship the new revision in its own PR.

## sample_data/

One week, 5 households, 1 needle (`sample_n_01`, broken promise, 3 sources), 1 decoy (`sample_d_01`), 1 opted-in
household (Rosa Delgado). Same file shapes as `scenarios/s1/`. Five real 311 rows (one per day) are copied from
Scenario 1 as background only. `example_escalations.json` holds three proposals in the evaluator's input shape
(`_id, run_id, household_id, ts, cited_event_ids`) with hand-computed verdicts under the IMPLEMENTATION_PLAN §5 rule
(caught before `deadline` with ≥2 required events; in time if `ts + response_hours < danger_at`; any decoy citation is
a false escalation) and the expected `eval.scorer.score_run` result. `data/tests` runs W4's scorer on it when `eval/`
is importable.

## Real vs synthetic

- **Real 311 rows** are never edited. They keep `origin: "real"`, a `real_311_key`, and their real public address and
  coordinates, and they map to no household in `event_truth.json`.
- **Synthetic households live only on clearly fictional streets** from `config/fictional_streets.json`. Every name was
  checked against NYC's official street centerline (CSCL) and every 311 request since 2010, citywide, with zero
  matches; names sharing a word with a real street in the scenario ZIPs are rejected too. Re-check with
  `python data/verify_fictional_streets.py` (network). Fictional street k in a ZIP borrows the flood intensity and
  house-number ranges of that ZIP's k-th most flood-hit real street, never its name or location.
- **Synthetic coordinates are one ZIP-level point** (2 decimals, about 1 km) or absent; never a jittered real point.
- `data/tests/test_data_gates.py` and `validate.py` enforce all of this for every committed scenario, plus the real
  address blocklist (`derived/address_blocklist.json`).

Visit notes captured live go through `intake/` (see `intake/README.md`).
