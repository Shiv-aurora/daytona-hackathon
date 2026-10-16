import { describe, expect, it } from "vitest";
import { MockApi } from "./mock";
import type { Board, RelayRequest } from "./types";
import { categoryBreakdown, countByStatus, coverage, funnel, journey, metricDelta, orgLoad, outcomeMix, promiseClock, provenance, verificationMix } from "./viz";

const req = (over: Partial<RelayRequest>): RelayRequest => ({
  id: "r",
  run_id: "demo-current",
  disaster_id: "demo-storm-2026",
  created_at: "2026-10-16T12:00:00Z",
  survivor_id: "s",
  category: "food",
  description: "",
  status: "open",
  due_at: null,
  organization_id: null,
  promised_at: null,
  source_report_id: "x",
  ...over,
});

async function board(runId = "demo-current"): Promise<Board> {
  return new MockApi().board(runId);
}

describe("funnel", () => {
  it("counts reached stages; a delivery report is never a verification", () => {
    const f = funnel([
      req({ id: "a", status: "open" }),
      req({ id: "b", status: "claimed" }),
      req({ id: "c", status: "awaiting_verification" }),
      req({ id: "d", status: "reopened" }),
      req({ id: "e", status: "resolved" }),
    ]);
    expect(f.stages.map((s) => s.count)).toEqual([5, 4, 3, 1]);
    expect(f.unverified).toBe(2);
    expect(f.reopened).toBe(1);
    expect(f.verifiedRate).toBeCloseTo(1 / 3);
  });
  it("has no verified rate until something is delivered", () => {
    expect(funnel([req({ status: "open" })]).verifiedRate).toBeNull();
    expect(funnel([]).stages.every((s) => s.count === 0)).toBe(true);
  });
});

describe("category breakdown", () => {
  it("groups by category with per-status counts, largest first", () => {
    const rows = categoryBreakdown([req({ id: "a" }), req({ id: "b", status: "resolved" }), req({ id: "c", category: "supplies" })]);
    expect(rows.map((r) => [r.category, r.total])).toEqual([
      ["food", 2],
      ["supplies", 1],
    ]);
    expect(rows[0].counts.resolved).toBe(1);
  });
});

describe("journey", () => {
  it("never marks the verification node done from a delivery report", () => {
    expect(journey(req({ status: "awaiting_verification" })).map((n) => n.state)).toEqual(["done", "done", "done", "current"]);
    expect(journey(req({ status: "reopened" })).at(-1)).toMatchObject({ state: "bad", label: "Not received" });
    expect(journey(req({ status: "resolved" })).map((n) => n.state)).toEqual(["done", "done", "done", "done"]);
    expect(journey(req({ status: "open" })).map((n) => n.state)).toEqual(["done", "current", "todo", "todo"]);
    expect(journey(req({ status: "claimed" })).map((n) => n.state)).toEqual(["done", "done", "current", "todo"]);
  });
});

describe("promiseClock", () => {
  const claimed = req({ status: "claimed", promised_at: "2026-10-16T14:00:00Z" });
  it("reports elapsed share and overdue", () => {
    const c = promiseClock(claimed, "2026-10-16T12:00:00Z", Date.parse("2026-10-16T13:00:00Z"))!;
    expect(c.progress).toBeCloseTo(0.5);
    expect(c.overdue).toBe(false);
    expect(c.minutesLeft).toBe(60);
    expect(promiseClock(claimed, "2026-10-16T12:00:00Z", Date.parse("2026-10-16T15:00:00Z"))!.overdue).toBe(true);
  });
  it("is null without a promise or for other statuses", () => {
    expect(promiseClock(req({ status: "claimed" }), null, 0)).toBeNull();
    expect(promiseClock(req({ status: "open", promised_at: "2026-10-16T14:00:00Z" }), null, 0)).toBeNull();
  });
});

describe("with the seeded board", () => {
  it("coverage lists organizations' capabilities and flags unmet categories", async () => {
    const b = await board();
    const cov = coverage(b);
    expect(cov.orgs.length).toBe(b.organizations.length);
    for (const org of b.organizations) for (const cap of org.capabilities) expect(cov.cells[cap][org.id].capable).toBe(true);
    expect(cov.unmet).toEqual([]);
  });
  it("flags a need nobody can supply", async () => {
    const b = await board();
    b.requests.push(req({ id: "x", category: "childcare" }));
    expect(coverage(b).unmet).toContain("childcare");
  });
  it("org load sums to the assigned requests", async () => {
    const b = await board();
    const loads = orgLoad(b);
    expect(loads.reduce((n, l) => n + l.total, 0)).toBe(b.requests.filter((r) => r.organization_id).length);
    expect(countByStatus(b.requests).open).toBe(b.requests.filter((r) => r.status === "open").length);
  });
  it("outcome mix groups every call; verification mix separates sources", async () => {
    const b = await board();
    const mix = outcomeMix(b.calls);
    expect(Object.values(mix).reduce((a, c) => a + c, 0)).toBe(b.calls.length);
    const v = verificationMix(b.verifications);
    expect(v.call + v.human).toBe(b.verifications.length);
  });
  it("an approved lesson from another disaster applies by condition; its own disaster never does", async () => {
    const cur = await board();
    const links = provenance(cur);
    const link = links.find((l) => l.lessonId === "lesson-confirm-handoff")!;
    expect(link.outcomeIds.length).toBeGreaterThan(0);
    expect(link.appliesTo.every((a) => a.matched.length > 0)).toBe(true);
    const hist = await board("demo-history");
    expect(provenance(hist).every((l) => l.appliesTo.length === 0)).toBe(true);
  });
});

describe("metricDelta", () => {
  it("reads direction per metric polarity", () => {
    expect(metricDelta("groundedness", 0.5, 0.75).direction).toBe("better");
    expect(metricDelta("groundedness", 0.5, 0.75).delta).toBe(25);
    expect(metricDelta("false_closure", 0, 0.25, true).direction).toBe("worse");
    expect(metricDelta("false_closure", 0.25, 0, true).direction).toBe("better");
    expect(metricDelta("x", 0.5, 0.5).direction).toBe("same");
    expect(metricDelta("x", null, 0.5).direction).toBe("unmeasured");
  });
});
