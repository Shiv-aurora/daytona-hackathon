import pytest

from db.bootstrap import HOUSEHOLDS, REGISTRY
from db.scope import RunScope
from memory.adapter import DemoMemory
from memory.households import (
    dwelling_key,
    file_household,
    match_household,
    name_words,
    seed_household,
)
from memory.startup import run_meta, start_run


@pytest.mark.parametrize("address, key", [
    ("42-05 Quailbrook St", "4205 quailbrook st"), ("4205 QUAILBROOK STREET", "4205 quailbrook st"),
    ("43-41 QUAILBROOK ST BSMT", "4341 quailbrook st bsmt"), ("4341 Quailbrook Street basement", "4341 quailbrook st bsmt"),
    ("51-99 LOOMHAVEN STREET APT 1F", "5199 loomhaven st 1f"), ("4869 Loomhaven St #2F", "4869 loomhaven st 2f"),
    ("45-18 162 STREET, 1F", "4518 162 st 1f"), ("37-14 104th St", "3714 104 st"),
    ("Tern Harbor Rd, basement", None), ("Hollow Oak Ln, 41-01 to 41-99, Sunnyside 11104", None),
    ("37-01 to 37-99 104th St", None)])
def test_one_dwelling_however_the_address_is_written(address, key):
    assert dwelling_key(address) == key


def test_descriptions_are_not_names():
    assert name_words("Mrs. Chen") == {"chen"} and name_words("Mrs. Chen's son") == {"chen"}
    assert name_words("SHU FEN ZHANG") == {"shu", "fen", "zhang"}
    assert name_words("elderly woman lives alone") == set() and name_words("Man in a wheelchair") == set()


def test_the_dwelling_decides_and_a_name_never_overrides_it(database):
    run = RunScope(database, "run-a")
    seed_household(run, "hh-guo", name="Guo Hua Wang", address="43-41 Quailbrook St Bsmt")
    seed_household(run, "hh-hong", name="Hong Wang", address="43-41 Quailbrook St 3F")
    seed_household(run, "hh-shu", name="Shu Fen Zhang", address="42-05 Quailbrook St")
    # The unit tells two Wangs in one building apart; with no unit, only an exact name could.
    assert match_household(run, {"name": "the Wangs", "address": "4341 QUAILBROOK ST BSMT"}) == "hh-guo"
    assert match_household(run, {"address": "43-41 Quailbrook St"}) is None
    assert match_household(run, {"name": "Hong Wang", "address": "43-41 Quailbrook St"}) == "hh-hong"
    # A unit nobody has on file still reaches a household that has no unit on file.
    assert match_household(run, {"name": "SHU FEN ZHANG", "address": "4205 QUAILBROOK STREET BSMT"}) == "hh-shu"
    # Someone else at a known dwelling is not that household; a dwelling nobody has isn't overridden.
    assert match_household(run, {"name": "Jose Rodrigez", "address": "42-05 Quailbrook St"}) is None
    assert match_household(run, {"name": "Shu Fen Zhang", "address": "1 Unknown Rd"}) is None
    # Without a dwelling, an exact name matches unless a street-only mention puts it elsewhere.
    assert match_household(run, {"name": "Shu Fen Zhang", "address": "Quailbrook St, rear"}) == "hh-shu"
    assert match_household(run, {"name": "Shu Fen Zhang", "address": "Tern Harbor Rd"}) is None


def test_filing_needs_a_name_at_a_dwelling(database):
    run = RunScope(database, "run-a")
    assert file_household(run, {"name": "elderly woman lives alone", "address": "45-18 162 Street 1F"}) is None
    assert file_household(run, {"name": "Jose Rodrigez", "address": "Pebblebrook Pl, basement"}) is None
    assert file_household(run, {"name": "Jose Rodrigez", "address": "25-61 Pebblebrook Pl, 25-01 to 25-99"}) is not None
    assert file_household(run, {"address": "2561 Pebblebrook Pl"}) is None
    assert run.count(HOUSEHOLDS) == 1


def test_a_filed_household_is_found_again_and_only_in_its_run(database):
    memory = DemoMemory(database, file_unregistered=True)
    first = memory.match_household("run-a", {"name": "JOSE RODRIGEZ", "address": "2561 PEBBLEBROOK PL"})
    assert first is not None and memory.household("run-a", first)["filed"] is True
    assert memory.match_household("run-a", {"name": "Man in a wheelchair", "address": "25-61 Pebblebrook Pl"}) == first
    assert memory.match_household("run-a", {"name": "JOSE RODRIGEZ", "address": "2561 PEBBLEBROOK PL"}) == first  # replay
    assert memory.match_household("run-a", {"name": "someone upstairs"}) is None  # nothing to file from
    assert DemoMemory(database).match_household("run-b", {"name": "JOSE RODRIGEZ"}) is None
    assert RunScope(database, "run-a").count(HOUSEHOLDS) == 1 and RunScope(database, "run-b").count(HOUSEHOLDS) == 0


def test_start_run_registers_the_run_and_seeds_its_registry_once(database):
    database[REGISTRY].insert_one({"household_id": "hh-chen", "scenario_id": "s1", "opt_in": True,
                                   "name": "Mei Chen", "address": "41-22 Hollow Oak Ln", "language": "zh"})
    database[REGISTRY].insert_one({"household_id": "hh-s2", "scenario_id": "s2", "opt_in": True, "name": "Other"})
    meta = start_run(database, "run-a", "s1", "2021-09-01T20:00:00-04:00", start_ts=12.0)
    assert meta == {"run_id": "run-a", "scenario_id": "s1", "day0": "2021-09-01T20:00:00-04:00", "mode": "live",
                    "start_ts": 12.0}
    assert start_run(database, "run-a", "s1", "another day0") == meta  # a restart changes nothing
    [household] = RunScope(database, "run-a").find(HOUSEHOLDS)
    assert (household["household_id"], household["name"], household["language"]) == ("hh-chen", "Mei Chen", "zh")
    assert run_meta(database, "run-b") is None
