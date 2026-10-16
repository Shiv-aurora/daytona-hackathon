import { describe, expect, it } from "vitest";
import { CallRequest, CallResultEvent, Event, Household, Metric, Needle, PolicyChange, Proposal, RegistryEntry, RelayPromise, RunMeta, SCENARIO_RUN_ID, SystemEvent } from "./contracts";
import { mockSnapshot as m } from "./mock";

describe("mock run matches the shared contracts (schemas.py)", () => {
  const cases = [
    ["run", RunMeta, [m.run]],
    ["households", Household, m.households],
    ["events", Event, m.events],
    ["promises", RelayPromise, m.promises],
    ["proposals", Proposal, m.proposals],
    ["registry", RegistryEntry, m.registry],
    ["call_requests", CallRequest, m.call_requests],
    ["call results", CallResultEvent, m.events.filter((e) => e.source === "call_result")],
    ["system_events", SystemEvent, m.system_events],
    ["metrics", Metric, m.metrics],
    ["policy_changes", PolicyChange, m.policy_changes],
    ["needles", Needle, m.needles ?? []],
  ] as const;
  it.each(cases)("%s", (_name, schema, docs) => {
    for (const d of docs) expect(schema.safeParse(d).error?.issues ?? []).toEqual([]);
  });

  it("keeps run isolation: scenario inputs vs this run's documents", () => {
    const run = m.run.run_id;
    for (const e of m.events) {
      expect(e.scenario_id).toBe(m.run.scenario_id);
      expect(e.source === "call_result" ? e.run_id === run : e.run_id === SCENARIO_RUN_ID).toBe(true);
    }
    for (const d of [...m.households, ...m.promises, ...m.proposals, ...m.call_requests, ...m.system_events, ...m.metrics, ...m.policy_changes]) {
      expect(d.run_id).toBe(run);
    }
  });

  it("every reference resolves and no id repeats", () => {
    const ids = new Set(m.events.map((e) => e._id));
    expect(ids.size).toBe(m.events.length);
    expect(new Set(m.proposals.map((p) => p._id)).size).toBe(m.proposals.length);
    for (const h of m.households) for (const id of h.applied_event_ids) expect(ids.has(id)).toBe(true);
    for (const p of m.proposals) for (const id of p.cited_event_ids) expect(ids.has(id)).toBe(true);
    for (const p of m.promises) expect(ids.has(p.source_event_id)).toBe(true);
    for (const id of Object.keys(m.decisions)) expect(m.proposals.find((p) => p._id === id)?.status).toBe(m.decisions[id].status);
  });

  it("puts synthetic households on fictional streets, never the old real-street fixture values", () => {
    const OLD_REAL_STREETS = [/\b41(st)? (ave|av|avenue)\b/i, /\b169(th)? (st|street)\b/i, /\bxenia\b/i,
      /\b33(rd)? (ave|avenue)\b/i, /\b87(th)? (st|street)\b/i, /\b25(th)? dr\b/i];
    const FICTIONAL = ["Lanternwick", "Quillmoor", "Fernhollow", "Marigold Crest", "Tinderbox", "Thistlewood"];
    const texts = [...m.households.map((h) => h.address ?? ""), ...m.events.map((e) => e.text), ...m.proposals.map((p) => p.reason)];
    for (const t of texts) for (const re of OLD_REAL_STREETS) expect(t).not.toMatch(re);
    for (const h of m.households) expect(FICTIONAL.some((f) => h.address?.includes(f))).toBe(true);
  });

  it("only calls opted-in households, for approved proposals, and escalates emergencies", () => {
    const optedIn = new Set(m.registry.filter((r) => r.opt_in).map((r) => r.household_id));
    for (const c of m.call_requests) {
      expect(optedIn.has(c.household_id)).toBe(true);
      expect(m.proposals.find((p) => p._id === c.proposal_id)?.status).toBe("approved");
    }
    for (const e of m.events.filter((x) => x.source === "call_result") as CallResultEvent[]) {
      expect(m.call_requests.some((c) => c._id === e.call_id)).toBe(true);
      if (e.outcome === "emergency_escalated") expect(m.proposals.some((p) => p._id === `${e.call_id}:emergency` && p.urgent)).toBe(true);
    }
  });

  it("has needles over this run's events and a playback start before the first open one", () => {
    const ids = new Set(m.events.map((e) => e._id));
    expect(m.needles?.length).toBeGreaterThan(0);
    for (const n of m.needles!) for (const id of n.required_event_ids) expect(ids.has(id)).toBe(true);
    expect(m.start_ts).toBeGreaterThanOrEqual(0);
    expect(m.start_ts).toBeLessThan(m.now_ts);
    expect(m.comparison ?? null).toBeNull(); // no invented evaluator output: "Prove it" says "Not yet measured"
  });

  it("has pending proposals with neutral, amber, and red deadlines", () => {
    const left = m.proposals.filter((p) => p.status === "pending").map((p) => p.due_ts! - m.now_ts).sort((a, b) => a - b);
    expect(left).toHaveLength(3);
    expect(left[0]).toBeLessThan(1);
    expect(left[1]).toBeGreaterThan(1);
    expect(left[1]).toBeLessThan(24);
    expect(left[2]).toBeGreaterThan(24);
  });
});
