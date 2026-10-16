# intake/

Typed or spoken volunteer visit notes -> one Relay event, in the same shape as `data/scenarios/*/events.jsonl`
(`schemas.Event` + the data spec's fields). Owner: W5. Stdlib-only Python plus the root `schemas.py`.

`ts` is hours since scenario day 0 (storm start, 2021-09-01 20:00 New York). A note captured during a run carries that
run's `run_id`; a note authored into scenario input carries `schemas.SCENARIO_RUN_ID` (`"scenario"`).

```python
from intake.visit_note import visit_note_event, from_transcript, merge, system_event

event = visit_note_event("Visited Mrs. Chen, 82, at 41-22 Hollow Oak Lane ...", ts=42.6,
                         author="Volunteer Dana R.", scenario_id="s1", run_id="run-1")
spoken = from_transcript({"text": "...", "language_code": "eng"}, ts=42.6,
                         author="Volunteer Dana R.", scenario_id="s1", run_id="run-1")  # speech-to-text, no network
stream = merge(existing_events, [event])   # idempotent, sorted by (ts, _id)
trace = system_event(event, "run-1")        # schemas.SystemEvent for the runtime/DB layer to persist
```

```bash
python -m intake.visit_note --scenario s1 --ts 42.6 --author "Volunteer Dana R." "Visited Mrs. Chen ..."   # scenario input
python -m intake.visit_note --scenario s1 --ts 42.6 --author "Volunteer Dana R." --transcript note.json --run-id run-1
```

- `_id` is a content hash (`<scenario>_vn_<12 hex>` over scenario, run, ts, author, text), so re-submitting the same
  note is a no-op and the same note in two runs never collides.
- `address_raw` and `household_ref_raw` are best-effort extractions from the text; no `household_id` is set. The
  street suffix is abbreviated ("41-22 Hollow Oak Lane" -> "41-22 Hollow Oak Ln"), the form registry identities use, so
  W2's normalized match resolves the live demo note to Mrs. Chen.
- `origin` is `"intake"` (hidden from Relay, like every event's `origin`).
