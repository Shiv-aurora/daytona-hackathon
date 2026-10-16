"""W4-C2 harness: run Relay and the baseline through one evaluation and score both the same way.

Both systems are advanced through the same event window and stopped at the same probe times
(`scorer.probe_times`), where each gets the same question about the same households. Both runs are
then scored by `score_run` over one document pool, one truth and one window; only the run_id
differs. What may legitimately differ between the two systems (how often each decides, and which
model each uses) is declared in the `EvalConfig`, checked against the systems before they run, and
reported with every result, so a difference is never accidental or hidden.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from eval.scorer import probe_times, score_run
from schemas import SCENARIO_RUN_ID

TRUTH_KEYS = frozenset({"needles", "decoys", "promises", "registry"})


@dataclass(frozen=True)
class EvalConfig:
    scenario_id: str
    until_ts: float
    household_ids: tuple[str, ...]  # probe targets, asked of both systems in this order
    relay_decision_every_hours: float  # Relay's runtime tick
    baseline_decision_every_hours: float  # how often the baseline is asked for escalations
    relay_model: str | None  # None: Relay runs without a model (its deterministic path)
    baseline_model: str

    @property
    def probe_times(self) -> list[float]:
        return probe_times(self.until_ts)

    def conditions(self) -> dict:
        return {"scenario_id": self.scenario_id, "as_of": self.until_ts, "probe_times": self.probe_times,
                "household_ids": list(self.household_ids),
                "decision_every_hours": {"relay": self.relay_decision_every_hours,
                                         "baseline": self.baseline_decision_every_hours},
                "same_decision_schedule": self.relay_decision_every_hours == self.baseline_decision_every_hours,
                "model": {"relay": self.relay_model, "baseline": self.baseline_model},
                "same_model": self.relay_model == self.baseline_model}


class ProbedSystem(Protocol):
    run_id: str
    decision_every_hours: float

    @property
    def now(self) -> float: ...

    @property
    def model(self) -> str | None: ...

    def advance_to(self, ts: float) -> None: ...

    def probe(self, ts: float, household_ids: list[str]) -> list[dict]: ...


class RelaySystem:
    """Relay under the harness: W1's runtime moves the clock, and the memory port answers each probe
    from Relay's own open promises, named by their source event."""

    def __init__(self, runtime, memory, state: dict):
        self.runtime, self.memory, self.state = runtime, memory, state
        self.run_id, self.decision_every_hours = state["run_id"], runtime.tick_hours

    @property
    def now(self) -> float:
        return self.state["now_ts"]

    @property
    def model(self) -> str | None:
        return self.runtime.llm.model if self.runtime.llm is not None else None

    def advance_to(self, ts: float) -> None:
        self.state = self.runtime.run(self.state, until_ts=ts)

    def probe(self, ts: float, household_ids: list[str]) -> list[dict]:
        return [{"run_id": self.run_id, "probe_ts": ts, "household_id": household_id,
                 "source_event_ids": sorted({promise["source_event_id"] for promise
                                             in self.memory.open_promises(self.run_id, household_id=household_id)})}
                for household_id in household_ids]


def run_both(relay: ProbedSystem, baseline: ProbedSystem, config: EvalConfig) -> dict[str, list[dict]]:
    """Check both systems match what the config declares, then run each through the same window."""
    declared = {"relay": (relay, config.relay_decision_every_hours, config.relay_model),
                "baseline": (baseline, config.baseline_decision_every_hours, config.baseline_model)}
    for role, (system, hours, model) in declared.items():
        if system.decision_every_hours != hours or system.model != model:
            raise ValueError(f"{role} {system.run_id!r} decides every {system.decision_every_hours:g}h with model "
                             f"{system.model!r}, but the config declares {hours:g}h and {model!r}")
    return {role: run_window(system, config) for role, (system, _, _) in declared.items()}


def run_window(system: ProbedSystem, config: EvalConfig) -> list[dict]:
    """Advance `system` through the window; return its answer to every probe, in schedule order."""
    answers: list[dict] = []
    for ts in config.probe_times:
        _advance(system, ts)
        for answer in system.probe(ts, list(config.household_ids)):
            if answer["run_id"] != system.run_id or answer["probe_ts"] != ts:
                raise ValueError(f"{system.run_id} answered the hour-{ts:g} probe as {answer['run_id']!r} "
                                 f"at hour {answer['probe_ts']:g}")
            answers.append(answer)
    _advance(system, config.until_ts)
    return answers


def _advance(system: ProbedSystem, ts: float) -> None:
    system.advance_to(ts)
    if system.now != ts:  # a probe taken late would have seen events the other system had not
        raise ValueError(f"{system.run_id} stopped at hour {system.now:g}, not {ts:g}: its step must divide "
                         "the probe interval")


def score_comparison(config: EvalConfig, *, relay_run_id: str, baseline_run_id: str, truth: dict,
                     proposals: list[dict], contacts: list[dict], probes: list[dict]) -> dict:
    """Score both runs with one scorer over one document pool, one truth and one window."""
    run_ids = {relay_run_id, baseline_run_id}
    if len(run_ids) != 2 or SCENARIO_RUN_ID in run_ids or not all(run_ids):
        raise ValueError("Relay and the baseline need two different run_ids, neither of them the scenario")
    if set(truth) != TRUTH_KEYS:
        raise ValueError(f"truth must have exactly {sorted(TRUTH_KEYS)}, got {sorted(truth)}")
    shared = {"scenario_id": config.scenario_id, "as_of": config.until_ts, "proposals": proposals,
              "contacts": contacts, "probes": probes, **truth}
    return {**config.conditions(), "relay": score_run(relay_run_id, **shared),
            "baseline": score_run(baseline_run_id, **shared)}
