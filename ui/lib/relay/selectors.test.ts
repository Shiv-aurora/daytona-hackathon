import { describe, expect, it } from "vitest";
import {
  canCall,
  eventText,
  lessonStatus,
  outcomeLabel,
  relTime,
  requestStory,
  sortRequests,
} from "./selectors";
import type { Board, CallOutcome, Lesson, RelayCall, RelayRequest, RequestStatus, Survivor, SystemEvent, Verification } from "./types";

const RUN = "run-a";
const DISASTER = "disaster-a";
const core = (id: string, created_at = "2026-10-16T12:00:00Z") => ({ id, run_id: RUN, disaster_id: DISASTER, created_at });

const req = (id: string, over: Partial<RelayRequest> = {}): RelayRequest => ({
  ...core(id),
  survivor_id: "s1",
  category: "food",
  description: "Synthetic request.",
  status: "open",
  due_at: null,
  organization_id: null,
  promised_at: null,
  source_report_id: `report-${id}`,
  ...over,
});

const survivor = (id: string, call_opt_in: boolean, display_name = `Household ${id}`): Survivor => ({
  ...core(id),
  display_name,
  language: "en",
  call_opt_in,
});

const call = (id: string, request_id: string, over: Partial<RelayCall> = {}): RelayCall => ({
  ...core(id),
  request_id,
  survivor_id: "s1",
  status: "completed",
  provider_conversation_id: null,
  outcome: "no_answer",
  summary: "",
  evidence_ids: [],
  ...over,
});

const verification = (id: string, request_id: string, created_at: string, received: boolean | null = true): Verification => ({
  ...core(id, created_at),
  request_id,
  received,
  source: "human_review",
  evidence_ids: [],
  notes: "",
});

const event = (id: string, module: string, action: string, subject_id: string, created_at: string, details: Record<string, unknown> = {}): SystemEvent => ({
  ...core(id, created_at),
  module,
  action,
  subject_id,
  details,
});

const board = (over: Partial<Board> = {}): Board => ({
  run_id: RUN,
  disaster: { id: DISASTER, name: "Disaster A", kind: "storm", region: "Region", started_at: "2026-10-15T00:00:00Z" },
  organizations: [],
  survivors: [],
  requests: [],
  calls: [],
  verifications: [],
  lessons: [],
  evaluations: [],
  system_events: [],
  ...over,
});

describe("sortRequests", () => {
  it("orders by deadline first, using due_at then promised_at, with no-deadline requests last", () => {
    const sorted = sortRequests([
      req("none"),
      req("late", { due_at: "2026-10-16T18:00:00Z" }),
      req("promised", { status: "claimed", promised_at: "2026-10-16T15:00:00Z" }),
      req("soon", { due_at: "2026-10-16T13:00:00Z" }),
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["soon", "promised", "late", "none"]);
  });

  it("breaks deadline ties by workflow status, then by arrival", () => {
    const sorted = sortRequests([
      req("resolved", { status: "resolved" }),
      req("awaiting", { status: "awaiting_verification" }),
      req("claimed", { status: "claimed" }),
      req("open-late", { status: "open", created_at: "2026-10-16T14:00:00Z" }),
      req("open-early", { status: "open", created_at: "2026-10-16T10:00:00Z" }),
      req("reopened", { status: "reopened" }),
    ]);
    expect(sorted.map((r) => r.id)).toEqual(["reopened", "open-early", "open-late", "claimed", "awaiting", "resolved"]);
  });

  it("lets an earlier deadline beat a more urgent-looking status", () => {
    const sorted = sortRequests([req("reopened-no-deadline", { status: "reopened" }), req("open-with-deadline", { due_at: "2026-10-16T13:00:00Z" })]);
    expect(sorted.map((r) => r.id)).toEqual(["open-with-deadline", "reopened-no-deadline"]);
  });

  it("never uses survivor identity: relabeling survivors does not change the order", () => {
    const base = [
      req("a", { survivor_id: "s1", due_at: "2026-10-16T13:00:00Z" }),
      req("b", { survivor_id: "s2", status: "claimed" }),
      req("c", { survivor_id: "s3", status: "open", created_at: "2026-10-16T09:00:00Z" }),
      req("d", { survivor_id: "s4", status: "open", created_at: "2026-10-16T08:00:00Z" }),
    ];
    const relabeled = base.map((r, i) => ({ ...r, survivor_id: ["zed", "alpha", "mid", "beta"][i] }));
    expect(sortRequests(relabeled).map((r) => r.id)).toEqual(sortRequests(base).map((r) => r.id));
    expect(sortRequests(base).map((r) => r.id)).toEqual(["a", "d", "c", "b"]);
  });

  it("returns a new array and leaves the input untouched", () => {
    const input = [req("b", { due_at: "2026-10-16T18:00:00Z" }), req("a", { due_at: "2026-10-16T13:00:00Z" })];
    const sorted = sortRequests(input);
    expect(sorted).not.toBe(input);
    expect(input.map((r) => r.id)).toEqual(["b", "a"]);
  });
});

describe("requestStory", () => {
  const r1 = req("r1", { source_report_id: "report-1" });
  const r2 = req("r2", { source_report_id: "report-2" });
  const b = board({
    requests: [r1, r2],
    verifications: [
      verification("v-late", "r1", "2026-10-16T15:00:00Z", true),
      verification("v-early", "r1", "2026-10-16T13:00:00Z", false),
      verification("v-other", "r2", "2026-10-16T14:00:00Z", true),
    ],
    calls: [call("c1", "r1"), call("c2", "r2")],
    system_events: [
      event("e-r2", "recovery", "request_claimed", "r2", "2026-10-16T12:30:00Z"),
      event("e-call", "calls", "follow_up_finished", "c1", "2026-10-16T14:30:00Z"),
      event("e-r1", "recovery", "request_claimed", "r1", "2026-10-16T12:10:00Z"),
      event("e-report", "intake", "report_received", "s1", "2026-10-16T12:00:00Z", { report_id: "report-1" }),
      event("e-unrelated", "recovery", "request_claimed", "r-other", "2026-10-16T12:20:00Z"),
    ],
  });

  it("keeps verifications, calls and events separate per request", () => {
    const story = requestStory(b, r1);
    expect(story.verifications.map((v) => v.id)).toEqual(["v-early", "v-late"]);
    expect(story.calls.map((c) => c.id)).toEqual(["c1"]);
    expect(story.events.map((e) => e.id)).toEqual(["e-report", "e-r1", "e-call"]);

    const other = requestStory(b, r2);
    expect(other.verifications.map((v) => v.id)).toEqual(["v-other"]);
    expect(other.calls.map((c) => c.id)).toEqual(["c2"]);
    expect(other.events.map((e) => e.id)).toEqual(["e-r2"]);
  });

  it("returns the newest verification as latest and null when there is none", () => {
    expect(requestStory(b, r1).latestVerification?.id).toBe("v-late");
    expect(requestStory(board({ requests: [r1] }), r1).latestVerification).toBeNull();
  });

  it("treats delivery as reported by status or by a delivery_reported event, never by a claim alone", () => {
    const claimed = req("claimed", { status: "claimed" });
    expect(requestStory(board({ requests: [claimed] }), claimed).delivered).toBe(false);
    for (const status of ["awaiting_verification", "resolved"] as RequestStatus[]) {
      expect(requestStory(board({ requests: [req("x", { status })] }), req("x", { status })).delivered).toBe(true);
    }
    const reopened = req("again", { status: "reopened" });
    const withEvent = board({ requests: [reopened], system_events: [event("e", "recovery", "delivery_reported", "again", "2026-10-16T13:00:00Z")] });
    expect(requestStory(withEvent, reopened).delivered).toBe(true);
  });
});

describe("canCall", () => {
  const optedIn = survivor("s-yes", true);
  const optedOut = survivor("s-no", false);
  const b = board({
    survivors: [optedIn, optedOut],
    calls: [call("q1", "r-queued", { status: "queued", outcome: "pending" }), call("done", "r-done", { status: "completed" })],
  });

  it("reflects the survivor's confirmed opt-in", () => {
    expect(canCall(b, req("r", { survivor_id: "s-yes", status: "awaiting_verification" })).optedIn).toBe(true);
    expect(canCall(b, req("r", { survivor_id: "s-no", status: "awaiting_verification" })).optedIn).toBe(false);
    expect(canCall(b, req("r", { survivor_id: "missing", status: "awaiting_verification" })).optedIn).toBe(false);
  });

  it("is unresolved only while awaiting verification or reopened", () => {
    const unresolvedByStatus = (["open", "claimed", "awaiting_verification", "reopened", "resolved"] as RequestStatus[]).map(
      (status) => [status, canCall(b, req("r", { survivor_id: "s-yes", status })).unresolved] as const,
    );
    expect(unresolvedByStatus).toEqual([
      ["open", false],
      ["claimed", false],
      ["awaiting_verification", true],
      ["reopened", true],
      ["resolved", false],
    ]);
  });

  it("finds a queued call for the request, and ignores completed calls", () => {
    expect(canCall(b, req("r-queued", { survivor_id: "s-yes" })).queued?.id).toBe("q1");
    expect(canCall(b, req("r-done", { survivor_id: "s-yes" })).queued).toBeUndefined();
    expect(canCall(b, req("r-none", { survivor_id: "s-yes" })).queued).toBeUndefined();
  });
});

describe("outcomeLabel", () => {
  // Typed as a Record so that adding a CallOutcome without covering it here fails type checking.
  const expected: Record<CallOutcome, "good" | "bad" | "neutral" | "alert"> = {
    pending: "neutral",
    verified_received: "good",
    not_received: "bad",
    unverified: "neutral",
    no_answer: "neutral",
    failed: "neutral",
    refused_no_opt_in: "alert",
    emergency_escalated: "alert",
  };

  it.each(Object.entries(expected))("covers %s with tone %s and a human label", (outcome, tone) => {
    const out = outcomeLabel(outcome);
    expect(out.tone).toBe(tone);
    expect(out.label).not.toBe(outcome);
    expect(out.label.length).toBeGreaterThan(0);
    expect(out.label).not.toMatch(/_/);
  });

  it("never presents no answer, unclear or failed calls as confirmation", () => {
    for (const outcome of ["no_answer", "unverified", "failed"]) {
      expect(outcomeLabel(outcome).label).toMatch(/still unverified/i);
    }
    expect(outcomeLabel("no_answer").tone).toBe("neutral");
  });

  it("flags emergencies as an alert that goes to a human", () => {
    expect(outcomeLabel("emergency_escalated")).toMatchObject({ tone: "alert", label: expect.stringMatching(/human/i) });
  });

  it("falls back to a readable neutral label for an unknown outcome", () => {
    expect(outcomeLabel("something_new")).toEqual({ label: "something new", tone: "neutral" });
  });
});

describe("eventText", () => {
  it("maps known module/action pairs", () => {
    expect(eventText(event("e", "recovery", "request_claimed", "r", "2026-10-16T12:00:00Z"))).toBe("Claimed by an organization with a promised time");
    expect(eventText(event("e", "intake", "human_escalation", "s", "2026-10-16T12:00:00Z"))).toMatch(/human escalation recorded before any other processing/);
    expect(eventText(event("e", "recovery", "delivery_reported", "r", "2026-10-16T12:00:00Z"))).toMatch(/not proof of receipt/);
  });

  it("describes seed events by their action", () => {
    expect(eventText(event("e", "demo_seed", "verification_reopened", "r", "2025-09-03T12:00:00Z"))).toBe("Seeded: verification reopened");
    expect(eventText(event("e", "demo_seed", "record_seeded", "r", "2025-09-03T12:00:00Z"))).toBe("Seeded: record seeded");
  });

  it("falls back to module and action for unknown events, without raw underscores", () => {
    expect(eventText(event("e", "calls", "something_else", "r", "2026-10-16T12:00:00Z"))).toBe("calls: something else");
  });
});

describe("relTime", () => {
  const now = Date.parse("2026-10-16T12:00:00Z");
  const at = (minutes: number) => new Date(now + minutes * 60_000).toISOString();

  it("formats future times as due", () => {
    expect(relTime(at(45), now)).toBe("due in 45 min");
    expect(relTime(at(0), now)).toBe("due in 0 min");
    expect(relTime(at(180), now)).toBe("due in 3 h");
  });

  it("formats past times as overdue", () => {
    expect(relTime(at(-30), now)).toBe("30 min overdue");
    expect(relTime(at(-120), now)).toBe("2 h overdue");
    expect(relTime(at(-119), now)).toBe("119 min overdue");
  });

  it("handles a missing or invalid time", () => {
    expect(relTime(null, now)).toBe("no time promised");
    expect(relTime(undefined, now)).toBe("no time promised");
    expect(relTime("not a date", now)).toBe("—");
  });
});

describe("lessonStatus", () => {
  const lesson = (over: Partial<Lesson>): Lesson => ({
    id: "l",
    source_disaster_id: DISASTER,
    source_run_id: RUN,
    source_outcome_ids: [],
    summary: "",
    conditions: [],
    recommendation: "",
    approved: false,
    approved_at: null,
    created_at: "2026-10-16T12:00:00Z",
    ...over,
  });

  it("labels other disasters as historical, and own lessons by approval", () => {
    const b = board();
    expect(lessonStatus(lesson({ source_disaster_id: "other", approved: true }), b)).toBe("historical");
    expect(lessonStatus(lesson({ approved: true }), b)).toBe("approved");
    expect(lessonStatus(lesson({ approved: false }), b)).toBe("draft");
  });
});
