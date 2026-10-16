import json
from pathlib import Path

import pytest

from intake.visit_note import (
    EVENT_FIELDS,
    extract_address,
    extract_ref,
    from_transcript,
    main,
    merge,
    system_event,
    visit_note_event,
)
from interfaces import event_visible_to_run
from schemas import SCENARIO_RUN_ID, Event, SystemEvent

ROOT = Path(__file__).resolve().parents[2]


CHEN_NOTE = ("Visited Mrs. Chen, 82, at 41-22 Hollow Oak Lane. Lives alone, speaks mostly Mandarin. Basement flooded, "
             "no power since Wednesday night. Her son Wei is coming Tuesday to help clean out.")
CHEN_TS = 42.6  # hours since day 0 = Fri Sep 3 14:36


def note(text=CHEN_NOTE, ts=CHEN_TS, author="Volunteer Dana R.", run_id="run-1"):
    return visit_note_event(text, ts=ts, author=author, scenario_id="s1", run_id=run_id)


def test_event_has_the_contract_and_scenario_event_shape():
    scenario_fields = set(json.loads((ROOT / "data/scenarios/s1/events.jsonl").open().readline()))
    e = note()
    assert set(e) == set(EVENT_FIELDS) == scenario_fields
    assert Event.__required_keys__ <= set(e)
    assert "household_id" not in e
    assert e["run_id"] == "run-1" and e["source"] == "visit_note" and e["origin"] == "intake"
    assert e["real_311_key"] is None and e["ts"] == CHEN_TS and e["ts_real"] == "2021-09-03T14:36"


def test_run_isolation():
    live = note()
    assert event_visible_to_run(live, "run-1", "s1") and not event_visible_to_run(live, "run-2", "s1")
    scripted = note(run_id=SCENARIO_RUN_ID)
    assert event_visible_to_run(scripted, "run-1", "s1") and event_visible_to_run(scripted, "run-2", "s1")
    assert not event_visible_to_run(scripted, "run-1", "sample")
    assert live["_id"] != scripted["_id"], "the same note in two runs must not collide"


def test_extracts_address_and_resident_reference():
    e = note()
    assert e["address_raw"] == "41-22 Hollow Oak Ln"
    assert e["household_ref_raw"] == "Mrs. Chen"
    assert extract_address("Checked on the Islam family at 86-11 Sparrowgate Rd, basement.") == "86-11 Sparrowgate Rd"
    assert extract_ref("Checked on the Islam family at 86-11 Sparrowgate Rd.") == "Islam family"
    assert extract_address("No address given here.") is None


def test_ids_are_deterministic_content_hashes():
    assert note()["_id"] == note()["_id"]
    assert note()["_id"] != note(text=CHEN_NOTE + " Follow up Wednesday.")["_id"]
    assert note()["_id"] != note(ts=43.2)["_id"]
    assert note(text="  Visited   Mrs. Chen.  ")["text"] == "Visited Mrs. Chen."


@pytest.mark.parametrize("kwargs", [{"text": "   "}, {"ts": -0.1}, {"author": " "}, {"run_id": ""}])
def test_rejects_bad_notes(kwargs):
    with pytest.raises(ValueError):
        note(**kwargs)


def test_spoken_note_matches_typed_note_except_channel():
    spoken = from_transcript({"text": CHEN_NOTE, "language_code": "eng", "engine": "elevenlabs_scribe"},
                             ts=CHEN_TS, author="Volunteer Dana R.", scenario_id="s1", run_id="run-1")
    typed = note()
    assert spoken["_id"] == typed["_id"] and spoken["text"] == typed["text"]
    assert spoken["channel_meta"] == {"author": "Volunteer Dana R.", "language": "en", "channel": "spoken",
                                      "stt": {"engine": "elevenlabs_scribe"}}
    assert from_transcript({"text": "Visita a la Sra. Delgado."}, ts=48, author="A", scenario_id="s1",
                           run_id="run-1")["channel_meta"]["language"] == "en"


def test_merge_is_ordered_and_idempotent():
    a, b, c = note(ts=72.0), note(ts=24.0), note(ts=24.0, author="Volunteer Omar F.")
    stream = merge([a], [b, c])
    assert [e["ts"] for e in stream] == [24.0, 24.0, 72.0]
    assert stream == sorted(stream, key=lambda e: (e["ts"], e["_id"]))
    assert merge(stream, [a, b]) == stream
    with pytest.raises(ValueError):
        merge(stream, [dict(a, text="edited")])


def test_system_event_is_run_scoped():
    e = note()
    s = system_event(e, "run-1")
    assert SystemEvent.__required_keys__ <= set(s)
    assert s["run_id"] == "run-1" and s["module"] == "intake" and s["ts"] == e["ts"] and s["ref_ids"] == [e["_id"]]
    assert system_event(e, "run-1")["_id"] == s["_id"]
    for bad in ("", SCENARIO_RUN_ID):
        with pytest.raises(ValueError):
            system_event(e, bad)


def test_cli_prints_event_and_system_event(capsys):
    assert main(["--scenario", "s1", "--ts", "42.6", "--author", "Volunteer Dana R.", "--run-id", "run-1",
                 CHEN_NOTE]) == 0
    event, sys_event = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert event == note() and sys_event["run_id"] == "run-1"


def test_cli_defaults_to_scenario_input(capsys):
    assert main(["--scenario", "s1", "--ts", "42.6", "--author", "Volunteer Dana R.", CHEN_NOTE]) == 0
    (line,) = capsys.readouterr().out.splitlines()
    assert json.loads(line) == note(run_id=SCENARIO_RUN_ID)


# ---------- the live demo note ----------

def demo_visit():
    """The exact Mrs. Chen visit note in Scenario 1 (s1_n_01's first required event) and her registry entry."""
    s1 = ROOT / "data" / "scenarios" / "s1"
    hero = next(n for n in json.loads((s1 / "needles.json").read_text()) if n["needle_id"] == "s1_n_01")
    visit = next(e for e in map(json.loads, (s1 / "events.jsonl").open()) if e["_id"] == hero["required_event_ids"][0])
    entry = next(r for r in json.loads((s1 / "registry.json").read_text()) if r["household_id"] == hero["household_id"])
    return visit, entry


def test_exact_demo_note_typed_or_spoken_resolves_to_mrs_chen():
    from db.scope import RunScope
    from db.testing import open_test_database
    from memory.households import match_household, seed_household

    visit, entry = demo_visit()
    kw = {"ts": visit["ts"], "author": visit["channel_meta"]["author"], "scenario_id": "s1", "run_id": "demo-run"}
    typed = visit_note_event(visit["text"], **kw)
    spoken = from_transcript({"text": visit["text"], "language_code": "eng", "engine": "elevenlabs_scribe"}, **kw)
    assert typed["_id"] == spoken["_id"] and typed["text"] == spoken["text"] == visit["text"]
    for e in (typed, spoken):
        assert (e["run_id"], e["scenario_id"], e["ts"]) == ("demo-run", "s1", 42.6)
        assert (e["address_raw"], e["household_ref_raw"]) == (visit["address_raw"], visit["household_ref_raw"])
    with open_test_database() as db:
        scope = RunScope(db, "demo-run")
        seed_household(scope, entry["household_id"], name=entry["name"], address=entry["address"])
        assert match_household(scope, {"name": typed["household_ref_raw"], "address": typed["address_raw"]}) == \
            entry["household_id"]


def test_replaying_the_demo_note_is_a_noop_downstream():
    from db.events import record_event
    from db.scope import RunScope
    from db.testing import open_test_database

    visit, _ = demo_visit()
    event = visit_note_event(visit["text"], ts=visit["ts"], author="Volunteer Dana R.", scenario_id="s1",
                             run_id="demo-run")
    replay = visit_note_event(visit["text"], ts=visit["ts"], author="Volunteer Dana R.", scenario_id="s1",
                              run_id="demo-run")
    with open_test_database() as db:
        scope = RunScope(db, "demo-run")
        assert record_event(scope, event) is True
        assert record_event(scope, replay) is False
        assert len(db["events"].find({"run_id": "demo-run"})) == 1
    assert merge([event], [replay]) == [event]
    assert system_event(event, "demo-run") == system_event(replay, "demo-run")
    assert system_event(event, "demo-run")["run_id"] == "demo-run"
