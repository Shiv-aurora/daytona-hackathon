import pytest

from db.bootstrap import (
    CALL_REQUESTS,
    EVENTS,
    HOUSEHOLDS,
    INDEXES,
    PROPOSALS,
    REGISTRY,
    SYSTEM_EVENTS,
    ensure_indexes,
)
from db.checkpoint import (
    StateTooLarge,
    check_small_state,
    thread_config,
)
from db.config import ConfigError, Settings, load_settings
from db.scope import RunIsolationError

URI = "ws://localhost:8000/rpc"


def test_settings_need_a_supported_service_url():
    with pytest.raises(ConfigError):
        load_settings(env={}, dotenv=None)
    with pytest.raises(ConfigError):
        load_settings(env={"SURREAL_URL": "localhost:27017"}, dotenv=None)


def test_settings_keep_the_uri_out_of_reprs():
    settings = load_settings(env={"SURREAL_URL": URI}, dotenv=None)
    assert settings == Settings(URI, "relay")
    assert URI not in repr(settings)


def test_dotenv_fills_gaps_and_the_environment_wins(tmp_path):
    dotenv = tmp_path / ".env"
    dotenv.write_text(f'# local only\nSURREAL_URL="{URI}"\nexport SURREAL_DATABASE=from_file\n')
    assert load_settings(env={}, dotenv=dotenv) == Settings(URI, "from_file")
    assert load_settings(env={"SURREAL_DATABASE": "from_env"}, dotenv=dotenv).db_name == "from_env"


def test_bootstrap_creates_run_scoped_indexes_idempotently(database):
    ensure_indexes(database)  # the fixture already ran it once
    households = database[HOUSEHOLDS].index_information()["run_household_unique"]
    assert households["key"] == [("run_id", 1), ("household_id", 1)] and households["unique"]
    assert database[EVENTS].index_information()["run_ts"]["key"] == [("run_id", 1), ("ts", 1)]
    call_requests = database[CALL_REQUESTS].index_information()["run_proposal_unique"]
    assert call_requests["key"] == [("run_id", 1), ("proposal_id", 1)] and call_requests["unique"]


# Indexes created by hand before bootstrap ran, plus one equivalent index
# under a name of someone's choosing. The reference store rejects a second index on the same keys.
HAND_MADE_INDEXES = {
    HOUSEHOLDS: [("run_household_unique", [("run_id", 1), ("household_id", 1)], {"unique": True})],
    REGISTRY: [("household_unique", [("household_id", 1)], {"unique": True})],
    PROPOSALS: [("run_ts", [("run_id", 1), ("ts", 1)], {}), ("run_status", [("run_id", 1), ("status", 1)], {})],
    EVENTS: [("scenario_ts_id", [("scenario_id", 1), ("ts", 1), ("_id", 1)], {}),
             ("events_by_run", [("run_id", 1), ("ts", 1)], {})],
    SYSTEM_EVENTS: [("run_ts", [("run_id", 1), ("ts", 1)], {})],
}


def test_bootstrap_adopts_indexes_that_already_exist(unbootstrapped_database):
    db = unbootstrapped_database
    for collection, indexes in HAND_MADE_INDEXES.items():
        for name, keys, options in indexes:
            db[collection].create_index(keys, name=name, **options)
    ensure_indexes(db)
    ensure_indexes(db)
    for collection, indexes in INDEXES.items():
        present = {tuple(map(tuple, info["key"])): bool(info.get("unique"))
                   for info in db[collection].index_information().values()}
        for _, keys, options in indexes:
            assert present[tuple(keys)] == bool(options.get("unique")), (collection, keys)
    with pytest.raises(Exception) as clash:  # The reference store's rule the bootstrap works around
        db[EVENTS].create_index([("run_id", 1), ("ts", 1)], name="another_name")
    assert clash.value.code == 85


def test_one_household_document_per_run(database):
    database[HOUSEHOLDS].insert_one({"run_id": "run-a", "household_id": "hh-chen"})
    database[HOUSEHOLDS].insert_one({"run_id": "run-b", "household_id": "hh-chen"})
    with pytest.raises(Exception) as duplicate:
        database[HOUSEHOLDS].insert_one({"run_id": "run-a", "household_id": "hh-chen"})
    assert duplicate.value.code == 11000


def test_checkpoints_are_one_small_thread_per_run():
    assert thread_config("run-a") == {"configurable": {"thread_id": "run-a"}}
    for reserved in ("", "scenario"):
        with pytest.raises(RunIsolationError):
            thread_config(reserved)
    check_small_state({"run_id": "run-a", "scenario_id": "s1", "tick": 3, "now_ts": 72.0, "cursor_ts": 70.5,
                       "cursor_id": "s1_e_000042", "pending_proposal_ids": [], "pending_call_ids": [],
                       "policy_version": 1})  # graph_state.GraphState
    with pytest.raises(StateTooLarge):
        check_small_state({"households": [{"notes": "x" * 40_000}]})


def test_saver_refuses_oversized_state_before_writing(database):
    from db.runs import load_run_state, save_run_state

    small = {"run_id": "run-a", "scenario_id": "s1", "tick": 1, "cursor_ts": 3.0}
    assert save_run_state(database, small)
    with pytest.raises(StateTooLarge):
        save_run_state(database, {**small, "tick": 2, "households": ["x" * 40_000]})
    assert load_run_state(database, "run-a") == small
