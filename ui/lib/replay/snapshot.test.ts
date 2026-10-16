import { describe, expect, it } from "vitest";
import { mockSnapshot as m } from "../mock";
import { listRuns, readConsole } from "./snapshot";
import { fakeDb } from "./fake-db";

const RUN = m.run.run_id;
// W2-shaped collections holding the mock run, a second run, and scenario inputs.
function db() {
  const other = (d: Record<string, unknown>) => ({ ...d, run_id: "other-run" });
  return fakeDb({
    run_state: [
      { _id: RUN, run_id: RUN, scenario_id: "s1", tick: 50, now_ts: m.now_ts },
      { _id: "other-run", run_id: "other-run", scenario_id: "s1", tick: 1, now_ts: 6 },
    ],
    households: [...m.households, other({ ...m.households[0]!, name: "OTHER RUN" })],
    promises: m.promises,
    proposals: [...m.proposals, other({ ...m.proposals[0]!, _id: "other-prop" })],
    call_requests: m.call_requests,
    system_events: [...m.system_events].reverse(),
    metrics: m.metrics,
    policy_changes: m.policy_changes,
    events: [...m.events, other({ ...m.events[0]!, _id: "other-event", source: "call_result" }), { ...m.events[0]!, _id: "unrelated-scenario-event" }],
    registry: m.registry.map((r) => ({ ...r, _id: r.household_id })),
    needles: (m.needles ?? []).map((n) => ({ ...n, scenario_id: "s1" })),
  });
}

describe("replay from recorded snapshots (read-only, run-scoped)", () => {
  it("lists runs, most complete first", async () => {
    expect((await listRuns(db())).map((r) => r.run_id)).toEqual([RUN, "other-run"]);
  });

  it("returns only this run's documents and the scenario inputs it used", async () => {
    const s = (await readConsole(db(), RUN))!;
    expect(s.run).toEqual({ run_id: RUN, scenario_id: "s1", day0: m.run.day0, mode: "replay" });
    expect(s.now_ts).toBe(m.now_ts);
    expect(s.start_ts).toBe(0);
    expect(s.households).toHaveLength(m.households.length);
    expect(JSON.stringify(s)).not.toContain("OTHER RUN");
    expect(s.proposals.map((p) => p._id)).not.toContain("other-prop");
    expect(s.events.map((e) => e._id).sort()).toEqual(m.events.map((e) => e._id).sort());
    expect(s.system_events.map((e) => e.ts)).toEqual([...m.system_events].map((e) => e.ts).sort((a, b) => a - b));
    expect(s.needles).toHaveLength(m.needles!.length);
    expect(s.comparison).toBeNull();
  });

  it("never returns callback numbers", async () => {
    const s = (await readConsole(db(), RUN))!;
    expect(s.registry.length).toBeGreaterThan(0);
    expect(JSON.stringify(s.registry)).not.toContain("callback_number");
  });

  it("rebuilds decisions from proposals and the coordinator's recorded reasons", async () => {
    const s = (await readConsole(db(), RUN))!;
    expect(s.decisions["prop-s1_h_012"]).toMatchObject({ status: "dismissed", reason: "Already handled by another team" });
    expect(s.decisions["prop-s1_h_001"]).toBeUndefined(); // still pending
  });

  it("is null for an unknown run", async () => {
    expect(await readConsole(db(), "nope")).toBeNull();
  });
});
