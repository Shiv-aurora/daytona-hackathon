"""Offline regressions for matching, run/time isolation, and approved lesson reuse."""

import pytest

from db.events import record_event
from db.scope import RunScope
from db.testing import open_test_database
from memory.adapter import DemoMemory
from memory.households import seed_household
from memory.lessons import LessonStore


@pytest.fixture
def relay():
    with open_test_database() as db:
        yield db, "retrieval-test"


def eventually(check):
    return check()  # offline writes are immediately visible


def test_fuzzy_search_matches_misspellings_within_the_run_only(relay):
    db, tag = relay
    memory = DemoMemory(db, fuzzy=True)
    relay_run, other_run = f"{tag}-relay", f"{tag}-other"
    seed_household(RunScope(db, relay_run), "hh-chen", name="Mei Chen", address="45-18 162 Street 1F")
    seed_household(RunScope(db, relay_run), "hh-delgado", name="Rosa Delgado", address="37-14 104th St Bsmt")
    seed_household(RunScope(db, other_run), "hh-wong", name="Rosa Delgato", address="9 Oak Ave")

    # Positive matches first, each waiting for the reference store to return its document; negatives only after.
    assert eventually(lambda: memory.match_household(relay_run, {"name": "Mae Chenn"})) == "hh-chen"
    assert eventually(lambda: memory.match_household(relay_run, {"name": "Mrs. Delgado"})) == "hh-delgado"
    assert eventually(lambda: memory.match_household(other_run, {"name": "Rosa Delgado"})) == "hh-wong"
    assert memory.match_household(relay_run, {"address": "3714 104th St"}) == "hh-delgado"  # the dwelling, exactly
    assert memory.match_household(relay_run, {"name": "Zed Nobody"}) is None  # a loose fuzzy hit is refused
    assert memory.match_household(other_run, {"name": "Mei Chen"}) is None  # only in the other run


def test_retrieval_is_scoped_to_the_run_and_its_past(relay):
    db, tag = relay
    memory = DemoMemory(db, fuzzy=True)
    scenario, relay_run, baseline = f"{tag}-s1", f"{tag}-relay", f"{tag}-baseline"

    def event(name, ts, text, run_id="scenario"):
        return {"_id": f"{tag}-{name}", "run_id": run_id, "scenario_id": scenario, "ts": ts,
                "source": "visit_note", "text": text}

    for doc in (event("e1", 1.0, "Landlord promised to fix the broken boiler by Thursday."),
                event("e2", 2.0, "Street flooding reported near the subway entrance."),
                event("e3", 50.0, "The boiler is still not fixed and the apartment is freezing.")):
        record_event(RunScope.scenario(db), doc)
    record_event(RunScope(db, relay_run), event("r1", 3.0, "Resident said the heating failed again.", relay_run))
    record_event(RunScope(db, baseline), event("b1", 3.0, "Baseline note: radiator is cold.", baseline))

    def found(run_id, as_of_ts):
        return [e["_id"].removeprefix(f"{tag}-") for e in
                memory.search_events(run_id, scenario, "no heat, the boiler is broken", as_of_ts, 10)]

    assert len(found(relay_run, 100.0)) == 4
    assert set(found(relay_run, 100.0)) == {"e1", "e2", "e3", "r1"}  # never the baseline's b1
    assert set(found(relay_run, 10.0)) == {"e1", "e2", "r1"}  # e3 is in the future at ts 10
    assert len(found(baseline, 100.0)) == 4
    assert set(found(baseline, 100.0)) == {"e1", "e2", "e3", "b1"}  # never Relay's r1


def test_lessons_are_stored_and_shared_only_after_approval(relay):
    db, tag = relay
    lessons = LessonStore(db)
    lesson = {"lesson_id": f"{tag}-l1", "text": "Check in a day before a landlord's deadline",
              "metric_values": {"promises_on_time_pct": 0.4}, "approved": False}
    assert lessons.add(lesson, run_id=f"{tag}-relay", scenario_id=f"{tag}-s0", ts=30.0)
    assert lessons.approve(f"{tag}-l1")
    assert not lessons.add({**lesson, "text": "rewritten"}, run_id=f"{tag}-relay", scenario_id=f"{tag}-s0", ts=30.0)
    visible = [item for item in lessons.visible(f"{tag}-next", f"{tag}-s1", 0.0) if item["lesson_id"].startswith(tag)]
    assert [(item["lesson_id"], item["approved"], item["text"]) for item in visible] == [
        (f"{tag}-l1", True, lesson["text"])]
