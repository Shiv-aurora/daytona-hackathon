"""Collection names and indexes. `python -m db.bootstrap` checks the local reference store."""

from __future__ import annotations

HOUSEHOLDS = "households"
EVENTS = "events"
PROMISES = "promises"
PROPOSALS = "proposals"
CALL_REQUESTS = "call_requests"
REGISTRY = "registry"
SYSTEM_EVENTS = "system_events"
METRICS = "metrics"
RUNS = "runs"  # schemas.RunMeta per run, keyed by run_id
POLICY_CHANGES = "policy_changes"
RUN_STATE = "run_state"  # one small state per run, keyed by run_id
LLM_CACHE = "llm_cache"  # keyed by a hash of model + prompt
LESSONS = "lessons"

# Reference store indexes. Per-run indexes lead with run_id.
INDEXES = {
    HOUSEHOLDS: [("run_household_unique", [("run_id", 1), ("household_id", 1)], {"unique": True})],
    EVENTS: [
        ("run_ts", [("run_id", 1), ("ts", 1)], {}),
        ("scenario_ts_id", [("scenario_id", 1), ("ts", 1), ("_id", 1)], {}),  # the event cursor
    ],
    PROMISES: [("run_status_due", [("run_id", 1), ("status", 1), ("due_ts", 1), ("_id", 1)], {})],
    PROPOSALS: [("run_status", [("run_id", 1), ("status", 1)], {})],
    # One queued call per proposal, whatever request _id or tick the caller used.
    CALL_REQUESTS: [("run_proposal_unique", [("run_id", 1), ("proposal_id", 1)], {"unique": True})],
    REGISTRY: [("household_unique", [("household_id", 1)], {"unique": True})],
    SYSTEM_EVENTS: [("run_ts", [("run_id", 1), ("ts", 1)], {})],
    METRICS: [("run_ts", [("run_id", 1), ("ts", 1)], {})],
    # One change per policy version; a second change claiming a version is refused.
    POLICY_CHANGES: [("run_version_unique", [("run_id", 1), ("version", 1)], {"unique": True})],
}


def ensure_indexes(db) -> None:
    """Create every collection's indexes. Idempotent, so it is safe on every startup.

    The reference store refuses a second index on the same keys under another name, so an equivalent index
    that already exists (same keys and uniqueness, any name) is adopted rather than recreated.
    """
    for collection, indexes in INDEXES.items():
        existing = {tuple(map(tuple, info["key"])): bool(info.get("unique"))
                    for info in db[collection].index_information().values()}
        for name, keys, options in indexes:
            if existing.get(tuple(keys)) != bool(options.get("unique")):
                db[collection].create_index(keys, name=name, **options)


def main() -> None:
    from db.fakes import FakeDatabase

    db = FakeDatabase()
    ensure_indexes(db)
    print(f"local indexes ready: {', '.join(INDEXES)}")


if __name__ == "__main__":
    main()
