"""Hidden contact truth (`scenarios/<id>/contact_truth.json`): how a registered resident answers the phone.

Call simulator and evaluator only; never give it to runtime decision logic. Every run (baseline and Relay) dials
the same residents, so both hear exactly the same behavior. A call's result is written by the calling run under
its own run_id (`calls.agent.CallTools.log_call_result`), never as scenario input.

    ledger.queue(request)          # W1 -> W2 `schedule_call`: W3 only ever places a queued request
    resident = ScriptedResident(load(path), now_ts=request["requested_ts"])
    CallAgent(backend, resident, responder, callback_number, ledger).start(request)   # W3-C2 contract
"""
from __future__ import annotations

import json
from pathlib import Path


def load(path: str | Path) -> dict[str, dict]:
    """Contact truth by household_id."""
    return {entry["household_id"]: entry for entry in json.loads(Path(path).read_text())["households"]}


def answers(entry: dict, ts: float) -> bool:
    """A call at `ts` connects unless it falls in a no_answer [from_ts, until_ts) interval."""
    return not any(i["from_ts"] <= ts < i["until_ts"] for i in entry["no_answer"])


def line(entry: dict, ts: float) -> str | None:
    """What the resident says when a call at `ts` connects: the last script line with from_ts <= ts."""
    said = [s["text"] for s in entry["script"] if s["from_ts"] <= ts]
    return said[-1] if said else None


class ScriptedResident:
    """A `calls.agent.Transport` for one call at simulated hour `now_ts`, driven by contact truth."""

    def __init__(self, truth: dict[str, dict], now_ts: float):
        self.truth, self.now_ts, self.pending = truth, now_ts, None

    def dial(self, household_id: str) -> bool:
        entry = self.truth.get(household_id)
        if entry is None or not answers(entry, self.now_ts):
            return False
        self.pending = line(entry, self.now_ts)
        return True

    def say(self, text: str) -> None:
        pass

    def listen(self) -> str | None:
        said, self.pending = self.pending, None  # one scripted answer, then the resident is done
        return said

    def hang_up(self) -> None:
        self.pending = None
