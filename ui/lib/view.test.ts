import { describe, expect, it } from "vitest";
import { mockSnapshot as m } from "./mock";
import { callView, callsOf, goalOf, parseTranscript, policyLine, stageOf, tokenSeries } from "./view";

describe("view selectors over the mock run", () => {
  it("reads the goal only from W1 metrics at the latest scoring", () => {
    const g = goalOf(m);
    const latest = Math.max(...m.metrics.map((x) => x.ts));
    const at = (name: string) => m.metrics.find((x) => x.ts === latest && x.name === name)!.value;
    expect([g.scoredAt, g.onTimePct, g.due, g.met, g.silent]).toEqual([latest, at("promises_on_time_pct"), at("promises_due"), at("promises_met"), at("silent_households")]);
    expect(g.policy).toMatchObject({ version: 2 });
    const none = goalOf({ ...m, metrics: [] });
    expect([none.scoredAt, none.onTimePct, none.silent]).toEqual([null, null, null]); // not scored: nothing invented
  });

  it("maps W1/W2/W3 trace actions onto the pipeline", () => {
    const s = (action: string, extra = {}) => ({ run_id: "r", module: "runtime", action, ts: 0, ...extra });
    expect(stageOf(s("llm_call", { purpose: "extract" }))).toBe("extracted");
    expect(stageOf(s("llm_call", { purpose: "decide" }))).toBe("scheduled");
    expect(stageOf(s("household_matched"))).toBe("matched");
    expect(stageOf(s("status_changed", { collection: "promises" }))).toBe("promise");
    expect(stageOf(s("call_scheduled"))).toBe("scheduled");
    expect(stageOf(s("policy_changed"))).toBe("policy");
    expect(stageOf(s("call_started"))).toBe("scheduled");
    expect(stageOf(s("call_refused_no_opt_in"))).toBe("scheduled");
    expect(stageOf(s("tick_started"))).toBe("event_in");
  });

  it("climbs total tokens while context per call stays near-constant", () => {
    const t = tokenSeries(m.system_events);
    expect(t.length).toBeGreaterThan(10);
    expect(t.every((x, i) => i === 0 || x.total > t[i - 1].total)).toBe(true);
    const ctx = t.map((x) => x.context);
    expect(Math.max(...ctx) - Math.min(...ctx)).toBeLessThan(500);
  });

  it("parses W3 transcripts and builds call views with safety state", () => {
    expect(parseTranscript("relay: Hello: there\nresident: Hi")).toEqual([
      { speaker: "relay", text: "Hello: there" },
      { speaker: "resident", text: "Hi" },
    ]);
    const emergency = callView(m, "call-s1_h_013-1")!;
    expect([emergency.status, emergency.language]).toEqual(["emergency_escalated", "zh"]);
    expect(emergency.safety).toEqual({ optIn: true, disclosure: true, emergency: true, phrase: "I can't get up" });
    expect(emergency.escalations.map((p) => p.kind)).toEqual(["emergency"]);
    const missed = callView(m, "call-s1_h_001-1")!;
    expect([missed.turns.length, missed.safety.disclosure, missed.safety.emergency]).toEqual([0, false, false]);
    expect(callsOf(m, "s1_h_001").map((c) => c.result?.outcome)).toEqual(["no_answer", "no_answer"]);
  });
});

describe("policyLine", () => {
  it("says what the learner changed and why, from W1's what_changed", () => {
    expect(policyLine({ what_changed: "lead_hours 0 -> 12 (promises_on_time_pct 40 < 90 target)" })).toBe(
      "Acting 12h before deadlines (was 0h) — only 40% of promises were on time against a 90% target",
    );
    expect(policyLine({ what_changed: "call_interval_hours 72 -> 24" })).toBe("Calling every 24h (was 72h)");
    expect(policyLine({ what_changed: "something else entirely" })).toBe("something else entirely");
  });
});
