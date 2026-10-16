"""Shared cross-worker interfaces.

Integration-owned. Implementations live in worker-owned folders.

Critical isolation rule:
- scenario input events have run_id == "scenario"
- run-generated events have run_id == the active run
- a run may read only matching-scenario input events plus its own generated events
- it must never read another run's generated events
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Protocol

from schemas import (
    SCENARIO_RUN_ID,
    CallRequest,
    Event,
    Household,
    RegistryEntry,
    SafetyVerdict,
)

Cursor = tuple[float, str]


class MemoryPort(Protocol):
    def events_after(
        self,
        run_id: str,
        scenario_id: str,
        after: Cursor | None,
        until_ts: float,
        limit: int,
    ) -> list[Event]:
        """Return ordered events after cursor through until_ts.

        The implementation must return only:
        1. scenario inputs where run_id == SCENARIO_RUN_ID and scenario_id matches, plus
        2. run-generated events where run_id == the requested run_id and scenario_id matches.
        """

    def match_household(self, run_id: str, identity_hint: dict[str, str]) -> str | None:
        """Resolve an identity hint within the active run."""

    def household(self, run_id: str, household_id: str) -> Household | None:
        """Return run-scoped household memory."""

    def apply_household_event(
        self, run_id: str, household_id: str, event: Event
    ) -> bool:
        """Apply one event idempotently. True only when newly applied."""

    def registry_entry(self, household_id: str) -> RegistryEntry | None:
        """Read shared opt-in registry data."""

    def insert_promise(self, promise: dict) -> bool:
        """Insert a promise once by deterministic id."""

    def open_promises(
        self,
        run_id: str,
        household_id: str | None = None,
        due_before: float | None = None,
    ) -> list[dict]:
        """Return open run-scoped promises ordered by due time then id."""

    def set_promise_status(
        self, run_id: str, promise_id: str, status: str, ts: float
    ) -> bool:
        """Forward-only transition from open to kept/lapsed."""

    def insert_proposal(self, proposal: dict) -> bool:
        """Insert with set-on-insert semantics; never reset coordinator status."""

    def proposals_with_status(self, run_id: str, status: str) -> list[dict]:
        """Return run-scoped proposals."""

    def system_event(self, event: dict) -> None:
        """Write one trace event idempotently when it has a deterministic id."""


class LedgerPort(Protocol):
    """Run-scoped goal, policy and accounting storage implemented by W2."""

    def run_promises(self, run_id: str) -> list[dict]:
        """Every promise in the run, any status, ordered by (due_ts, _id)."""

    def run_proposals(self, run_id: str) -> list[dict]:
        """Every proposal in the run, any status."""

    def registry_entries(self, scenario_id: str) -> list[RegistryEntry]:
        """Visible registry entries for scenario bootstrap / silence tracking."""

    def last_contact_by_household(
        self, run_id: str, scenario_id: str, as_of_ts: float
    ) -> dict[str, float]:
        """Latest person-contact time visible to the run for each household."""

    def record_metric(self, metric: dict) -> None: ...

    def record_policy_change(self, change: dict) -> None: ...

    def policy_change(self, run_id: str, version: int) -> dict | None: ...


class RetrievalPort(Protocol):
    def search_events(
        self,
        run_id: str,
        scenario_id: str,
        query: str,
        as_of_ts: float,
        limit: int,
    ) -> list[Event]:
        """Time-filtered relevant search over events visible to this run."""


class LLMCachePort(Protocol):
    def llm_cache_get(self, key: str) -> dict | None: ...

    def llm_cache_put(self, key: str, value: dict) -> None: ...


SafetyCheck = Callable[[str], SafetyVerdict]


class CallsPort(Protocol):
    def schedule_call(self, request: CallRequest) -> bool:
        """Queue one call request idempotently. W3 re-checks opt-in before dialing."""


class CallBackend(Protocol):
    def registry_entry(self, household_id: str) -> RegistryEntry | None: ...

    def household_context(self, run_id: str, household_id: str) -> dict: ...

    def write_event(self, event: Event) -> bool: ...

    def escalate(self, proposal: dict) -> bool: ...

    def system_event(self, event: dict) -> None: ...


def event_visible_to_run(event: Event, run_id: str, scenario_id: str) -> bool:
    """Canonical run isolation predicate used by tests/adapters."""
    return event["scenario_id"] == scenario_id and event["run_id"] in {
        SCENARIO_RUN_ID,
        run_id,
    }
