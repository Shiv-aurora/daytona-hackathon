import { describe, expect, it } from "vitest";
import seed from "./seed.json";
import { FIXED_DISCLOSURE, categoriesOf, detectEmergency } from "./mock";
import { FOLLOW_UP_SAMPLES, INTAKE_SAMPLES, SAMPLE_TRANSCRIPTS } from "./samples";
import type { Core, Lesson, RelayCall, RelayRequest, Verification } from "./types";

const runs = new Map(seed.runs.map((r) => [r.run_id, r.disaster_id]));
const requests = seed.requests as RelayRequest[];
const calls = seed.calls as RelayCall[];
const verifications = seed.verifications as Verification[];
const lessons = seed.lessons as Lesson[];
const scoped = [...seed.survivors, ...requests, ...calls, ...verifications, ...seed.evaluations, ...seed.system_events] as Core[];
const STATUSES = ["open", "claimed", "awaiting_verification", "resolved", "reopened"];

describe("seed data integrity", () => {
  it("every operational record carries a run_id and disaster_id that match", () => {
    for (const r of scoped) expect(runs.get(r.run_id), r.id).toBe(r.disaster_id);
  });

  it("ids are unique per table", () => {
    for (const rows of [seed.survivors, requests, calls, verifications, lessons, seed.system_events, seed.organizations]) {
      const ids = rows.map((r) => r.id);
      expect(new Set(ids).size).toBe(ids.length);
    }
  });

  it("has no survivor contact fields or contact values anywhere", () => {
    const text = JSON.stringify(seed);
    expect(text).not.toMatch(/"(phone|email|address|callback|contact)[a-z_]*"\s*:/i);
    expect(text).not.toMatch(/[\w.+-]+@[\w.-]+\.\w+|(?:\+?\d[ ().-]*){9,}/);
  });

  it("keeps request statuses, organizations and categories consistent with the contract", () => {
    const orgs = new Map(seed.organizations.map((o) => [o.id, o]));
    const survivors = new Map(seed.survivors.map((s) => [s.id, s]));
    for (const r of requests) {
      expect(STATUSES).toContain(r.status);
      expect(survivors.get(r.survivor_id)?.run_id, r.id).toBe(r.run_id);
      if (r.status === "open") expect([r.organization_id, r.promised_at], r.id).toEqual([null, null]);
      else expect(orgs.get(r.organization_id ?? "")?.capabilities, r.id).toContain(r.category);
      const vs = verifications.filter((v) => v.request_id === r.id);
      if (r.status === "resolved") expect(vs.some((v) => v.received === true), r.id).toBe(true);
      if (r.status === "reopened") expect(vs.some((v) => v.received === false), r.id).toBe(true);
      if (r.status === "claimed") expect(vs, r.id).toEqual([]);
    }
    for (const status of STATUSES) {
      expect(requests.filter((r) => r.run_id === "demo-current" && r.status === status).length, status).toBeGreaterThan(1);
    }
  });

  it("keeps the anchor records the demo script depends on", () => {
    const status = (id: string) => requests.find((r) => r.id === id)?.status;
    expect(status("current-food-1")).toBe("open");
    expect(status("current-supplies-1")).toBe("awaiting_verification");
    expect(status("current-transport-1")).toBe("reopened");
    expect(status("history-food-1")).toBe("resolved");
    expect(seed.survivors.find((s) => s.id === "current-survivor-3")?.call_opt_in).toBe(false);
    expect(calls.find((c) => c.id === "current-no-answer-1")?.outcome).toBe("no_answer");
  });

  it("only seeds calls for opted-in survivors, in their own run, and covers every outcome", () => {
    const optIn = new Map(seed.survivors.map((s) => [s.id, s.call_opt_in]));
    for (const c of calls) {
      expect(optIn.get(c.survivor_id), c.id).toBe(true);
      expect(c.run_id).toBe(requests.find((r) => r.id === c.request_id)!.run_id);
    }
    const outcomes = new Set(calls.map((c) => c.outcome));
    for (const o of ["verified_received", "not_received", "no_answer", "unverified", "emergency_escalated", "pending"]) {
      expect(outcomes.has(o), o).toBe(true);
    }
    expect(calls.filter((c) => c.outcome === "emergency_escalated")).toHaveLength(1);
  });

  it("lesson sources exist in their own run and lessons are de-identified", () => {
    const names = seed.survivors.map((s) => s.display_name.toLowerCase());
    for (const l of lessons) {
      expect(runs.get(l.source_run_id)).toBe(l.source_disaster_id);
      for (const id of l.source_outcome_ids) {
        const v = verifications.find((x) => x.id === id);
        expect(v, `${l.id} -> ${id}`).toBeTruthy();
        expect(v!.run_id).toBe(l.source_run_id);
      }
      expect(l.approved, l.id).toBe(l.approved_at !== null);
      const text = `${l.summary} ${l.recommendation} ${l.conditions.join(" ")}`.toLowerCase();
      for (const n of names) expect(text).not.toContain(n);
    }
    expect(lessons.filter((l) => l.approved).length).toBeGreaterThan(1);
    expect(lessons.some((l) => !l.approved)).toBe(true);
  });

  it("added events use known modules, stay within ~36 hours and are chronological per run", () => {
    const extra = seed.system_events.filter((e) => e.id.startsWith("seed-extra-event-"));
    expect(extra.length).toBeGreaterThan(40);
    for (const e of extra) expect(["intake", "recovery", "calls"]).toContain(e.module);
    for (const run of ["demo-current", "demo-history"]) {
      const times = extra.filter((e) => e.run_id === run).map((e) => Date.parse(e.created_at));
      expect(times).toEqual([...times].sort((a, b) => a - b));
    }
    const current = extra.filter((e) => e.run_id === "demo-current").map((e) => Date.parse(e.created_at));
    expect(Math.max(...current) - Math.min(...current)).toBeLessThanOrEqual(36 * 3600_000);
  });

  it("spreads deadlines so sorting shows variety", () => {
    const due = new Set(requests.filter((r) => r.run_id === "demo-current" && r.due_at).map((r) => r.due_at));
    expect(due.size).toBeGreaterThan(8);
  });
});

describe("sample transcripts", () => {
  it("has 3 intake and 4 follow-up scripts with unique ids", () => {
    expect(INTAKE_SAMPLES).toHaveLength(3);
    expect(FOLLOW_UP_SAMPLES.map((s) => s.outcome).sort()).toEqual(["no_answer", "not_received", "unverified", "verified_received"]);
    expect(new Set(SAMPLE_TRANSCRIPTS.map((s) => s.id)).size).toBe(7);
  });

  it("opens every follow-up with the fixed disclosure and never includes contact details", () => {
    for (const s of FOLLOW_UP_SAMPLES) expect(s.lines[0].text).toBe(FIXED_DISCLOSURE);
    for (const s of SAMPLE_TRANSCRIPTS) expect(JSON.stringify(s)).not.toMatch(/@|\d{3}[ -]\d{3,4}/);
  });

  it("the emergency intake is caught by the code-owned detector and the others are not", () => {
    for (const s of INTAKE_SAMPLES) {
      const caller = s.lines.filter((l) => l.speaker === "caller").map((l) => l.text).join(" ");
      expect(Boolean(detectEmergency(caller)), s.id).toBe(Boolean(s.emergency));
      if (!s.emergency) expect(categoriesOf(caller)).not.toEqual(["other"]);
    }
  });
});
