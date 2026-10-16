import { describe, expect, it } from "vitest";
import { atTime, needleTimes, nextNeedle } from "./clock";
import { mockSnapshot as m } from "./mock";

describe("playback clock", () => {
  it("is the snapshot itself at or after the run head", () => {
    expect(atTime(m, m.now_ts)).toBe(m);
    expect(atTime(m, m.now_ts + 100)).toBe(m);
  });

  it("hides everything recorded after t and rolls later status changes back", () => {
    const t = 150; // after Wei's promise lapsed (145), before Chen's check-in call results
    const s = atTime(m, t);
    expect(s.now_ts).toBe(t);
    for (const key of ["events", "system_events", "metrics", "policy_changes"] as const) {
      expect((s[key] as { ts: number }[]).every((d) => d.ts <= t)).toBe(true);
    }
    expect(s.proposals.every((p) => p.ts <= t)).toBe(true);
    expect(s.call_requests.every((c) => c.requested_ts <= t)).toBe(true);
    expect(Object.values(s.decisions).every((d) => d.ts <= t)).toBe(true);
    expect(s.promises.find((p) => p._id === "s1_h_001_p1")?.status).toBe("lapsed");
    // Chen's first check-in (created 158) and the escalation (303) don't exist yet.
    expect(s.proposals.some((p) => p.household_id === "s1_h_001")).toBe(false);
    const chen = s.households.find((h) => h.household_id === "s1_h_001")!;
    expect(chen.applied_event_ids).toEqual(["s1_e_000407"]);
  });

  it("reopens a promise that lapses later and re-pends a proposal decided later", () => {
    const early = atTime(m, 100);
    const wei = early.promises.find((p) => p._id === "s1_h_001_p1")!;
    expect(wei.status).toBe("open");
    expect(wei.status_ts).toBeUndefined();
    const s = atTime(m, 158.2); // Chen's first check-in exists (158.0) but is approved at 158.5
    expect(s.proposals.find((p) => p._id === "prop-checkin-s1_h_001-1")?.status).toBe("pending");
    expect(s.decisions["prop-checkin-s1_h_001-1"]).toBeUndefined();
  });

  it("jumps needle to needle, landing on Relay's proposal for each", () => {
    expect(needleTimes(m).map((t) => t.toFixed(1))).toEqual(["44.2", "287.5", "303.1", "325.2"]);
    expect(nextNeedle(m, m.start_ts!)).toBeCloseTo(287.52);
    expect(nextNeedle(m, 287.52)).toBeCloseTo(303.12);
    expect(nextNeedle(m, 325.2)).toBeNull();
    expect(atTime(m, 303.12).proposals.find((p) => p._id === "prop-s1_h_001")?.status).toBe("pending");
  });
});
