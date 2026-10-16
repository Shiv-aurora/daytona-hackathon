"""Test stand-ins for the baseline: a scripted `runtime.llm.LLMClient`, W2's real `DemoMemory` over
its in-memory database, and a deliberately broken port. No network or external database."""

from __future__ import annotations

from db.bootstrap import EVENTS, ensure_indexes
from db.fakes import FakeDatabase
from db.scope import RunScope
from eval.baseline import PROBE_SYSTEM
from memory.adapter import DemoMemory
from memory.households import seed_household
from runtime.llm import LLMResponse


class ScriptedLLM:
    """An `LLMClient`: answers decisions and probes from a script, records every prompt, never the network."""

    def __init__(self, decide=None, probe=None, model="test/scripted"):
        self.model = model
        self.decide = decide or (lambda prompt: '{"escalations": []}')
        self.probe = probe or (lambda prompt: '{"open_promises": {}}')
        self.prompts: list[str] = []

    def complete(self, messages, max_tokens):
        system, prompt = messages[0]["content"], messages[-1]["content"]
        self.prompts.append(prompt)
        reply = (self.probe if system == PROBE_SYSTEM else self.decide)(prompt)
        return LLMResponse(reply, self.model, prompt_tokens=len(prompt) // 4, completion_tokens=len(reply) // 4)


def shared_memory(events, households):
    """W2's `DemoMemory` over its in-memory database, holding `events` and each run's households,
    given as {run_id: {household_id: {"name": ..., "address": ...}}}."""
    db = FakeDatabase()
    ensure_indexes(db)
    for event in events:
        db[EVENTS].insert_one(dict(event))
    for run_id, known in households.items():
        for household_id, identity in known.items():
            seed_household(RunScope(db, run_id), household_id, **identity)
    return DemoMemory(db)


def run_docs(memory, collection, run_id, module=None):
    docs = memory.db[collection].find({"run_id": run_id}, sort=[("ts", 1), ("_id", 1)])
    return [doc for doc in docs if module is None or doc.get("module") == module]


class LeakyEvents:
    """A broken port that hands out every event, whatever its run, scenario or time."""

    def __init__(self, events):
        self.events = sorted(events, key=lambda event: (event["ts"], event["_id"]))

    def events_after(self, run_id, scenario_id, after, until_ts, limit):
        return [event for event in self.events if after is None or (event["ts"], event["_id"]) > after][:limit]

    def system_event(self, event):
        pass
