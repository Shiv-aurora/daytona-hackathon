"""Shared document shapes for Relay.

Integration-owned. Workers may request changes in PR notes but should not edit this file directly.

All simulated timestamps are **hours since scenario day 0**.
Scenario input events use run_id == "scenario"; run-generated events use the active run_id.
"""

from typing import Literal, NotRequired, TypedDict

SCENARIO_RUN_ID = "scenario"
SimTime = float


class Event(TypedDict):
    _id: str
    run_id: str
    scenario_id: str
    ts: SimTime
    source: str
    text: str
    household_id: NotRequired[str]


class Household(TypedDict):
    run_id: str
    household_id: str
    name: NotRequired[str]
    address: NotRequired[str]
    language: NotRequired[str]
    applied_event_ids: list[str]


class Promise(TypedDict):
    _id: str
    run_id: str
    scenario_id: str
    household_id: str
    text: str
    keywords: list[str]
    made_ts: SimTime
    due_ts: SimTime
    status: Literal["open", "kept", "lapsed"]
    source_event_id: str
    status_ts: NotRequired[SimTime]
    evidence_event_ids: NotRequired[list[str]]


class RegistryEntry(TypedDict):
    household_id: str
    opt_in: bool
    language: NotRequired[str]
    first_name: NotRequired[str]
    callback_number: NotRequired[str]
    # Scenario/bootstrap matching hints. W5 may include these on the shared registry.
    scenario_id: NotRequired[str]
    name: NotRequired[str]
    address: NotRequired[str]
    registered_ts: NotRequired[SimTime]


class Proposal(TypedDict):
    _id: str
    run_id: str
    scenario_id: str
    household_id: str
    kind: str
    status: str
    reason: str
    ts: SimTime
    cited_event_ids: list[str]
    promise_id: NotRequired[str]
    due_ts: NotRequired[SimTime]
    queue: NotRequired[str]
    urgent: NotRequired[bool]
    early: NotRequired[bool]
    suggested_action: NotRequired[Literal["call", "visit"]]
    rationale: NotRequired[str]


class CallRequest(TypedDict):
    _id: str
    run_id: str
    scenario_id: str
    household_id: str
    proposal_id: str
    promise_id: NotRequired[str]
    purpose: str
    requested_ts: SimTime


class CallResult(TypedDict):
    run_id: str
    household_id: str
    outcome: Literal[
        "completed",
        "no_answer",
        "emergency_escalated",
        "refused_no_opt_in",
        "failed",
    ]
    scenario_id: NotRequired[str]
    call_id: NotRequired[str]
    ts: NotRequired[SimTime]
    answered: NotRequired[bool]
    text: NotRequired[str]


class SafetyVerdict(TypedDict):
    emergency: bool
    reason: NotRequired[str]


class Metric(TypedDict):
    _id: str
    run_id: str
    name: str
    value: float
    scope: str
    ts: SimTime


class PolicyChange(TypedDict):
    _id: str
    run_id: str
    version: int
    what_changed: str
    params: dict[str, float]
    metric_values: dict[str, float]
    ts: SimTime


class Lesson(TypedDict):
    lesson_id: str
    text: str
    metric_values: dict[str, float]
    approved: bool


class Needle(TypedDict):
    needle_id: str
    household_id: str
    required_event_ids: list[str]
    deadline: SimTime
    people_at_risk: int
    danger_at: SimTime
    response_hours: float
    kind: Literal["broken_promise", "cross_service_join", "silent_household"]


class Decoy(TypedDict):
    decoy_id: str
    household_id: str
    event_ids: list[str]


class RunMeta(TypedDict):
    run_id: str
    scenario_id: str
    day0: str
    mode: str


class ImpactMetrics(TypedDict):
    households_reached_in_time: int
    people_reached_in_time: int
    # Undefined when no needle was caught; render as N/A rather than a fake zero.
    days_warning_gained: float | None
    false_escalations: int


class GoalStatus(TypedDict):
    # Undefined when no promise is due at the scoring time.
    promises_on_time_pct: float | None
    silent_households: int


class TruthPromise(TypedDict):
    """Read-only scenario truth used by the deterministic evaluator."""

    household_id: str
    source_event_id: str
    made_ts: SimTime
    due_ts: SimTime
    status: NotRequired[Literal["kept", "lapsed"]]
    status_ts: NotRequired[SimTime]


class PromiseProbe(TypedDict):
    """One run's answer to an evaluator memory probe."""

    run_id: str
    probe_ts: SimTime
    household_id: str
    source_event_ids: list[str]


class PromiseRecallBucket(TypedDict):
    label: str
    min_days: float
    max_days: float | None
    open: int
    recalled: int
    recall: float | None


class PromiseRecall(TypedDict):
    probe_times: list[SimTime]
    open: int
    recalled: int
    recall: float | None
    named_not_open: int
    by_age: list[PromiseRecallBucket]


class Score(TypedDict):
    # Undefined only when the scenario has no needles.
    needle_recall: float | None
    impact: ImpactMetrics
    goal: GoalStatus
    promise_recall: PromiseRecall
    # W1/W2 add accounting later; W4-C1 does not require it yet.
    cost_per_simulated_day: NotRequired[float | None]


class SystemEvent(TypedDict):
    run_id: str
    module: str
    action: str
    ts: SimTime
    _id: NotRequired[str]
