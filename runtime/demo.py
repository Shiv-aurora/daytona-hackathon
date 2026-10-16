"""Run the retained offline recovery scenario with local or demo storage.

Both stores are in-process. No database connection is opened. A configured model key is
optional; without it the deterministic extraction path runs. Calls use scripted residents.
"""

from __future__ import annotations

import argparse
import functools
import json
import os
import sys
from collections import Counter
from collections.abc import Callable
from pathlib import Path

from calls.agent import CallAgent, result_event_id
from calls.responders import ScriptedResponder
from calls.safety import safety_check
from runtime.llm import CachedLLM, OpenRouterClient
from runtime.local import LocalStore
from runtime.loop import Runtime, TickFailed
from runtime.scenario import Scenario, ScenarioError, load_scenario, seed_local
from runtime.state import new_run_state
from schemas import CallRequest

HERO = "Mei Chen"
CONTACT_SOURCES = ("visit_note",)
CONTACT_TRUTH = "contact_truth.json"  # hidden: only the call simulator reads it, never the runtime
DEFAULT_CALLBACK_NUMBER = "+1-555-0100"  # fictional; W3's live bridge uses RELAY_CALLBACK_NUMBER
SIMULATED_APPROVAL = "Simulated coordinator approval for the demo"


class LocalBackend:
    """Everything on one `LocalStore`."""

    def __init__(self, run_id: str, scenario: Scenario):
        self.store = LocalStore()
        seed_local(self.store, run_id, scenario)
        self.memory = self.calls = self.ledger = self.retrieval = self.cache = self.store

    def save_state(self, state: dict) -> bool:
        return False  # in-process: nothing outlives the process to resume from

    def load_state(self, run_id: str) -> dict | None:
        return None

    def proposals(self, run_id: str) -> list[dict]:
        return self.store.run_proposals(run_id)

    def approve(self, run_id: str, proposal_id: str, ts: float) -> bool:
        return self.store.decide(run_id, proposal_id, "approved", ts)

    def call_requests(self, run_id: str) -> list[dict]:
        return [request for (rid, _), request in self.store.call_requests.items() if rid == run_id]

    def call_simulator(self, residents, callback_number: str) -> CallSimulator:
        return CallSimulator(self.store, self.store, residents, callback_number)


class CallSimulator:
    """Places due queued calls with W3's merged `CallAgent`, the way W3 would in production.

    `residents(request)` is the W3 `Transport` for one call (offline: a scripted resident). W3's
    `CallLedger` claims each request once (queued -> dialing -> done), so placing the same request
    again, or replaying this step, never dials twice or writes a second `call_result`.
    """

    def __init__(self, backend, ledger, residents: Callable[[dict], object], callback_number: str):
        self.backend, self.ledger = backend, ledger  # W3's CallBackend and CallLedger
        self.residents, self.callback_number = residents, callback_number
        self.responder = ScriptedResponder()  # W3's deterministic questions from the household's promises

    @staticmethod
    def due(requests: list[dict], until_ts: float) -> list[dict]:
        """Queued requests whose time has come, oldest first, as the CallRequests W3 receives."""
        queued = sorted((r for r in requests if r.get("status") == "queued" and r["requested_ts"] <= until_ts),
                        key=lambda r: (r["requested_ts"], r["_id"]))
        return [{key: r[key] for key in CallRequest.__annotations__ if key in r} for r in queued]

    def place(self, request: dict) -> dict:
        agent = CallAgent(self.backend, self.residents(request), self.responder, self.callback_number, self.ledger)
        return agent.start(request)


def scripted_residents(scenario_dir: str | Path) -> Callable[[dict], object] | None:
    """W5's simulated residents over the scenario's hidden contact truth, if the scenario ships it."""
    path = Path(scenario_dir) / CONTACT_TRUTH
    if not path.is_file():
        return None
    from data.contact import ScriptedResident, load  # W5's call simulator

    truth = load(path)
    return lambda request: ScriptedResident(truth, now_ts=request["requested_ts"])


class DemoBackend:
    """In-process document store used by the reference demo and regression tests."""

    def __init__(self, db, run_id: str, scenario: Scenario):
        from db.bootstrap import ensure_indexes
        from memory.adapter import DemoMemory
        from memory.calls import DemoCallBackend, DemoCallLedger
        from memory.startup import start_run

        ensure_indexes(db)
        self.db = db
        load_inputs(db, scenario)
        start_run(db, run_id, scenario.scenario_id, scenario.day0)  # idempotent; seeds the run's registry
        self.memory = self.ledger = self.retrieval = self.cache = DemoMemory(db, file_unregistered=True)
        self.calls = DemoCallLedger(db)  # the runtime's calls port, and W3's ledger
        self.call_backend = DemoCallBackend(db)

    def save_state(self, state: dict) -> bool:
        return self.memory.save_run_state(state)  # W2's on_tick hook; the saved tick only moves forward

    def load_state(self, run_id: str) -> dict | None:
        return self.memory.load_run_state(run_id)

    def proposals(self, run_id: str) -> list[dict]:
        return self.memory.run_proposals(run_id)

    def approve(self, run_id: str, proposal_id: str, ts: float) -> bool:
        from db.scope import RunScope
        from db.writes import decide_proposal

        return decide_proposal(RunScope(self.db, run_id), proposal_id, "approved", ts)

    def call_requests(self, run_id: str) -> list[dict]:
        from db.bootstrap import CALL_REQUESTS
        from db.scope import RunScope

        return RunScope(self.db, run_id).find(CALL_REQUESTS, sort=[("requested_ts", 1), ("_id", 1)])

    def call_simulator(self, residents, callback_number: str) -> CallSimulator:
        return CallSimulator(self.call_backend, self.calls, residents, callback_number)


def load_inputs(db, scenario: Scenario) -> int:
    """Load the scenario's events and registry into W2's collections, only what is missing. Returns how
    many events were new. A database holding other inputs for the same scenario id is refused."""
    from db.bootstrap import EVENTS, REGISTRY
    from db.events import record_event
    from db.scope import RunScope
    from memory.adapter import DemoMemory

    inputs = RunScope.scenario(db)
    loaded = {event["_id"] for event in inputs.find(EVENTS, {"scenario_id": scenario.scenario_id})}
    foreign = loaded - {event["_id"] for event in scenario.events}
    registered = {entry["household_id"]: entry for entry in DemoMemory(db).registry_entries(scenario.scenario_id)}
    changed = [e["household_id"] for e in scenario.registry
               if e["household_id"] in registered and registered[e["household_id"]] != e]
    if foreign or changed:
        raise ScenarioError(f"the database holds other inputs for scenario {scenario.scenario_id!r} "
                            f"({len(foreign)} events, {len(changed)} registry entries); refusing to mix them")
    new = [event for event in scenario.events if event["_id"] not in loaded]
    for event in new:
        record_event(inputs, event)  # insert-once by _id
    for entry in scenario.registry:
        if entry["household_id"] not in registered:
            db[REGISTRY].update_one({"household_id": entry["household_id"]}, {"$setOnInsert": entry}, upsert=True)
    return len(new)


def open_backend(kind: str, run_id: str, scenario: Scenario):
    if kind == "local":
        return LocalBackend(run_id, scenario)
    if kind == "demo":
        from db.fakes import FakeDatabase

        return DemoBackend(FakeDatabase(), run_id, scenario)
    raise ValueError(f"unknown store {kind!r}")


def default_model(cache) -> CachedLLM | None:
    """OpenRouter behind the cache when a key is configured; otherwise None (the regex path)."""
    client = OpenRouterClient.from_env()
    return CachedLLM(cache, client) if client is not None and cache is not None else None


def run_demo(scenario_dir: str | Path, *, store: str = "local", run_id: str = "relay-demo", hero: str = HERO,
             tick_hours: float = 1.0, until_ts: float | None = None, stop_at_escalation: bool = True,
             llm=None, residents: Callable[[dict], object] | None = None, say=print,
             progress: Callable[[str], None] | None = None) -> dict:
    """Fast-forward the scenario; returns a summary with the hero's chain, step by step.

    `residents` gives the W3 `Transport` for each call; by default, W5's scripted residents when the
    scenario ships contact truth. The checkpoint is saved after every tick, and a run with a saved
    checkpoint (W2 stores) continues from it. `progress` gets one line per simulated day.
    """
    scenario = load_scenario(scenario_dir)
    backend = open_backend(store, run_id, scenario)
    llm = llm if llm is not None else default_model(backend.cache)
    # W3's phrase check runs before any model sees a note.
    runtime = Runtime(backend.memory, backend.calls, scenario.day0, tick_hours=tick_hours, llm=llm,
                      safety=safety_check, ledger=backend.ledger, retrieval=backend.retrieval)
    residents = residents or scripted_residents(scenario_dir)
    callback = os.environ.get("RELAY_CALLBACK_NUMBER") or scenario.callback_number or DEFAULT_CALLBACK_NUMBER
    simulator = backend.call_simulator(residents, callback) if residents else None
    hero_id = next((e["household_id"] for e in scenario.registry if e.get("name") == hero), None)
    state = backend.load_state(run_id) or new_run_state(run_id, 0.0, scenario.scenario_id)
    end = until_ts or scenario.end_ts
    seen: set[str] = set()
    chain: list[dict] = []
    escalated, unread = False, set()

    def step(ts: float, what: str, detail: str = "") -> None:
        chain.append({"ts": round(ts, 2), "what": what, "detail": detail})
        say(f"  h{ts:>7g}  {what}{': ' + detail if detail else ''}")

    def read_by_runtime(call_id: str) -> bool:
        household = backend.memory.household(run_id, hero_id) or {}
        return result_event_id(call_id) in (household.get("applied_event_ids") or [])

    say(f"Scenario {scenario.scenario_id}: {len(scenario.events)} events, {len(scenario.registry)} registered; "
        f"hero {hero} ({hero_id}); model: {'OpenRouter (cached)' if llm else 'regex fallback'}; store: {store}; "
        f"calls: {'placed by W3 against scripted residents' if simulator else 'queued only (no call simulator)'}")
    if state["tick"]:  # continuing a saved run: what the hero already has is not new
        mine = [p for p in backend.proposals(run_id) if p["household_id"] == hero_id]
        seen.update(p["_id"] for p in mine)
        seen.update(p["_id"] for p in backend.memory.run_promises(run_id) if p["household_id"] == hero_id)
        seen.update(r["_id"] for r in backend.call_requests(run_id) if r["household_id"] == hero_id)
        escalated = any(p["kind"] == "escalation" for p in mine)
        step(state["now_ts"], "continuing from the saved checkpoint", f"tick {state['tick']}")
    while state["now_ts"] < end and not (escalated and stop_at_escalation):
        state = runtime.tick(state)
        backend.save_state(state)
        now = state["now_ts"]
        if progress is not None and state["tick"] % 24 == 0:
            progress(f"  ... h{now:g} ({state['tick']} ticks)")
        for call_id in sorted(unread):
            if read_by_runtime(call_id):
                unread.discard(call_id)
                step(now, "runtime read the call result", result_event_id(call_id))
        for promise in (backend.memory.open_promises(run_id, household_id=hero_id) if hero_id else []):
            if promise["_id"] not in seen:
                seen.add(promise["_id"])
                step(promise["made_ts"], "promise recorded", f'{promise["text"][:90]} (due h{promise["due_ts"]:g})')
        pending = backend.memory.proposals_with_status(run_id, "pending")  # every new proposal starts pending
        for proposal in sorted(pending, key=lambda p: (p["ts"], p["_id"])):
            if proposal["household_id"] != hero_id or proposal["_id"] in seen:
                continue
            seen.add(proposal["_id"])
            step(proposal["ts"], f'{proposal["kind"]} proposed',
                 f'{proposal["reason"][:110]} [cites {", ".join(proposal["cited_event_ids"])}]')
            escalated |= proposal["kind"] == "escalation"
        for proposal in pending:
            if (proposal["household_id"] == hero_id and proposal["kind"] == "check_in"
                    and backend.approve(run_id, proposal["_id"], now)):
                backend.memory.system_event({"_id": f"demo:proposal_decided:{proposal['_id']}", "run_id": run_id,
                                             "module": "demo", "action": "proposal_decided", "ts": now,
                                             "proposal_id": proposal["_id"], "decision": "approved",
                                             "reason": SIMULATED_APPROVAL})
                step(now, "coordinator approves (simulated for the demo)", proposal["_id"])
        requests = backend.call_requests(run_id)
        for request in requests:
            if request["household_id"] == hero_id and request["_id"] not in seen:
                seen.add(request["_id"])
                step(now, "call request queued for W3", f'{request["_id"]} (not before h{request["requested_ts"]:g})')
        for request in (simulator.due(requests, now + tick_hours) if simulator else []):
            result = simulator.place(request)  # before the next tick, which reads its call_result
            if request["household_id"] == hero_id:
                unread.add(request["_id"])
                heard = next((line[len("resident: "):] for line in result["text"].splitlines()
                              if line.startswith("resident: ")), "")
                step(request["requested_ts"], f'W3 call outcome: {result["outcome"]}',
                     f'answered={result["answered"]}' + (f' "{heard[:80]}"' if heard else ""))

    proposals, requests = backend.proposals(run_id), backend.call_requests(run_id)
    summary = {"run_id": run_id, "scenario_id": scenario.scenario_id, "store": store, "ended_at_ts": state["now_ts"],
               "ticks": state["tick"], "hero_household_id": hero_id, "hero_escalated": escalated,
               "proposals_by_kind": dict(Counter(p["kind"] for p in proposals)), "calls_queued": len(requests),
               "call_outcomes": dict(Counter(r["result"]["outcome"] for r in requests if r.get("result"))),
               "hero_chain": chain, "model": bool(llm),
               "checkpoint": {k: (len(v) if isinstance(v, list) else v) for k, v in state.items()}}
    summary["_proposals"] = proposals
    return summary


def score(scenario_dir: str | Path, summary: dict) -> dict:
    """W4's evaluator over the run's proposals, after the run. Apart from the call simulator's
    contact truth, this is the only place truth files are read."""
    from eval.scorer import score_run

    directory = Path(scenario_dir)
    truth = {name: json.loads((directory / f"{name}.json").read_text())
             for name in ("needles", "decoys", "promises", "registry", "event_truth")}
    events = load_scenario(directory).events
    contacts = [{**event, "household_id": truth["event_truth"][event["_id"]]["household_id"]} for event in events
                if event.get("source") in CONTACT_SOURCES and (truth["event_truth"].get(event["_id"]) or {}).get(
                    "household_id")]
    return score_run(summary["run_id"], scenario_id=summary["scenario_id"], proposals=summary["_proposals"],
                     needles=truth["needles"], decoys=truth["decoys"], promises=truth["promises"],
                     registry=truth["registry"], contacts=contacts, probes=[], as_of=summary["ended_at_ts"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scenario-dir", default="data/scenarios/s1")
    parser.add_argument("--store", choices=("local", "demo"), default="local")
    parser.add_argument("--run-id", default="relay-demo")
    parser.add_argument("--tick-hours", type=float, default=1.0)
    parser.add_argument("--until", type=float, default=None, help="simulated hour to stop at (default: scenario end)")
    parser.add_argument("--full", action="store_true", help="keep going after the hero's escalation")
    parser.add_argument("--score", action="store_true", help="score the run with W4's evaluator afterwards")
    parser.add_argument("--json", action="store_true", help="print the summary as JSON")
    args = parser.parse_args(argv)
    say = (lambda *a: None) if args.json else functools.partial(print, flush=True)
    progress = functools.partial(print, file=sys.stderr, flush=True) if args.store != "local" else None
    try:
        summary = run_demo(args.scenario_dir, store=args.store, run_id=args.run_id, tick_hours=args.tick_hours,
                           until_ts=args.until, stop_at_escalation=not args.full, say=say, progress=progress)
        result = {**summary, "score": score(args.scenario_dir, summary) if args.score else None}
    except (ScenarioError, TickFailed) as error:
        print(f"demo stopped: {error}", file=sys.stderr)
        return 2
    result.pop("_proposals")
    if args.json:
        print(json.dumps(result, indent=1, default=str))
    else:
        print(f"\nstopped at h{result['ended_at_ts']:g} after {result['ticks']} ticks; proposals "
              f"{result['proposals_by_kind']}; calls queued {result['calls_queued']}, W3 outcomes "
              f"{result['call_outcomes']}; "
              f"hero escalated: {result['hero_escalated']}")
        if result["score"]:
            s = result["score"]
            print(f"W4: needle recall {s['needle_recall']}, false escalations {s['impact']['false_escalations']}, "
                  f"goal {s['goal']}, caught {[n['needle_id'] for n in s['detail']['needles'] if n['caught']]}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
