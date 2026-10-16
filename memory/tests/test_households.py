from db.bootstrap import HOUSEHOLDS, SYSTEM_EVENTS
from db.scope import RunScope
from memory.households import (
    apply_event,
    get_household,
    match_household,
    seed_household,
)


def test_applying_the_same_event_twice_is_a_no_op(database):
    run = RunScope(database, "run-a")
    assert apply_event(run, "hh-chen", "s1_e_042", ts=3.0)
    assert not apply_event(run, "hh-chen", "s1_e_042", ts=3.0)

    household = get_household(run, "hh-chen")
    assert household["applied_event_ids"] == ["s1_e_042"] and household["last_event_ts"] == 3.0
    assert run.count(HOUSEHOLDS) == 1
    assert run.count(SYSTEM_EVENTS, {"action": "event_applied"}) == 1


def test_replaying_an_old_event_changes_nothing(database):
    run = RunScope(database, "run-a")
    assert apply_event(run, "hh-chen", "s1_e_042", ts=3.0)
    assert apply_event(run, "hh-chen", "s1_e_077", ts=8.0)
    assert not apply_event(run, "hh-chen", "s1_e_042", ts=3.0)
    household = get_household(run, "hh-chen")
    assert household["applied_event_ids"] == ["s1_e_042", "s1_e_077"] and household["last_event_ts"] == 8.0


def test_households_are_isolated_by_run(database):
    run_a, run_b = RunScope(database, "run-a"), RunScope(database, "run-b")
    assert apply_event(run_a, "hh-chen", "s1_e_042", ts=3.0)
    assert get_household(run_b, "hh-chen") is None
    # The same scenario event is new to run-b, so applying it there is not a replay.
    assert apply_event(run_b, "hh-chen", "s1_e_042", ts=3.0)
    assert run_a.count(HOUSEHOLDS) == run_b.count(HOUSEHOLDS) == 1


def test_seeding_happens_once_per_run(database):
    run = RunScope(database, "run-a")
    assert seed_household(run, "hh-chen", name="Mei Chen", address="12 Elm St")
    assert apply_event(run, "hh-chen", "s1_e_042", ts=3.0)
    assert not seed_household(run, "hh-chen", name="Someone Else")
    household = get_household(run, "hh-chen")
    assert household["name"] == "Mei Chen" and household["applied_event_ids"] == ["s1_e_042"]


def test_matching_is_exact_after_normalizing_address_first_then_name(database):
    run = RunScope(database, "run-a")
    seed_household(run, "hh-chen", name="Mei Chen", address="45-18 162 Street 1F")
    seed_household(run, "hh-chen-2", name="Mei Chen", address="9 Oak Ave")
    seed_household(run, "hh-delgado", name="Rosa Delgado", address="37-14 104th St Bsmt")

    assert match_household(run, {"address": "45-18 162 STREET, 1F"}) == "hh-chen"
    assert match_household(run, {"name": "rosa  delgado."}) == "hh-delgado"
    assert match_household(run, {"name": "Mei Chen"}) is None  # two households: never guess
    assert match_household(run, {"name": "Mei Chen", "address": "9 oak ave"}) == "hh-chen-2"
    assert match_household(run, {"address": "1 Unknown Rd", "name": "Rosa Delgado"}) is None  # no name override
    assert match_household(run, {"name": "Mrs. Delgado"}) is None  # fuzzy variants are C2
    assert match_household(run, {}) is None
    assert match_household(RunScope(database, "run-b"), {"name": "Rosa Delgado"}) is None
