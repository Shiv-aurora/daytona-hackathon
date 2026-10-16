// MockApi: a faithful in-browser stand-in for the Relay API, used for the offline/"Simulated" mode.
// It mirrors the state rules of api/demo_store.py (same statuses, 409/400/404 cases, event names) and is seeded
// from data/demo/seed.json. A page reload resets it. The evaluation result is a recorded real backend run
// (compare_fixture.json), never computed or invented here.
import seed from "./seed.json";
import compareFixture from "./compare_fixture.json";
import { SEEDED_RUNS } from "./http";
import {
  RelayError,
  type Board,
  type CompareResult,
  type Disaster,
  type Health,
  type Lesson,
  type Recommendation,
  type RelayApi,
  type RelayCall,
  type RelayRequest,
  type ReportResult,
  type RunInfo,
  type ScriptedAnswer,
  type SystemEvent,
  type Verification,
} from "./types";

type Data = typeof seed;

// Code-owned in the backend (calls/safety.py). Rendered verbatim; the real server fills in its callback number,
// so the simulated mode shows a clearly marked stand-in instead of inventing a phone number.
export const FIXED_DISCLOSURE =
  "This is an automated call from Relay for the recovery team. To confirm this call is real, call us back at [demo callback number].";
const EMERGENCY_LINE = "Please hang up and call 911 now. I'm alerting a person on the recovery team.";

const NEEDS: Record<string, string[]> = {
  food: ["food", "meal", "groceries", "water"],
  supplies: ["supplies", "blanket", "blankets", "diaper", "hygiene"],
  transportation: ["transport", "ride", "bus"],
  shelter: ["shelter", "housing"],
  repairs: ["repair", "roof"],
  medicine: ["medicine", "medication"],
};
// Mirror of the English emergency phrases in calls/safety.py. Emergency detection runs before anything else.
const EMERGENCY = [
  "i fell", "i've fallen", "i have fallen", "fell down", "can't get up", "cant get up", "cannot get up",
  "can't breathe", "cant breathe", "cannot breathe", "trouble breathing", "hard to breathe", "not breathing",
  "chest pain", "my chest hurts", "heart attack", "stroke", "unconscious", "passed out", "bleeding", "smell gas",
  "gas leak", "fire", "call 911", "ambulance", "emergency", "kill myself", "want to die", "overdose",
];
const NOT_EMERGENCIES = ["i fell asleep", "i fell behind"];

export function detectEmergency(text: string): string | null {
  let t = " " + text.toLowerCase().replace(/’/g, "'").replace(/[^\w']+/g, " ").trim().replace(/\s+/g, " ") + " ";
  for (const ok of NOT_EMERGENCIES) t = t.split(` ${ok} `).join(" ");
  return EMERGENCY.find((p) => t.includes(` ${p} `)) ?? null;
}

export function categoriesOf(text: string): string[] {
  const words = new Set(text.toLowerCase().match(/\w+/g) ?? []);
  const found = Object.entries(NEEDS).filter(([, triggers]) => triggers.some((t) => words.has(t))).map(([c]) => c);
  return found.length ? found : ["other"];
}

export function conditionsOf(text: string): string[] {
  const t = text.toLowerCase();
  return /\b(road|bridge|street|access)\b.*\b(blocked|flooded|closed|out)\b|\bblocked\b|\bcan'?t get out\b/.test(t) ? ["access_blocked"] : [];
}

const clone = <T,>(v: T): T => JSON.parse(JSON.stringify(v));
const nowIso = () => new Date().toISOString();
const wait = (ms = 140) => new Promise((r) => setTimeout(r, ms));

export class MockApi implements RelayApi {
  readonly kind = "mock" as const;
  private data: Data = clone(seed);
  private counter = 0;

  private id(prefix: string) {
    this.counter += 1;
    return `${prefix}-${Date.now().toString(36)}-${this.counter}`;
  }

  private disasterOf(runId: string): string {
    const run = this.data.runs.find((r) => r.run_id === runId);
    if (!run) throw new RelayError("unknown run", 404);
    return run.disaster_id;
  }

  private core(runId: string) {
    return { run_id: runId, disaster_id: this.disasterOf(runId), created_at: nowIso() };
  }

  private event(runId: string, module: string, action: string, subject: string, details: Record<string, unknown> = {}) {
    const e = { id: this.id("evt"), ...this.core(runId), module, action, subject_id: subject, details };
    (this.data.system_events as SystemEvent[]).push(e);
  }

  private request(runId: string, requestId: string): RelayRequest {
    const row = (this.data.requests as RelayRequest[]).find((r) => r.id === requestId && r.run_id === runId);
    if (!row) throw new RelayError("unknown or out-of-scope record", 404);
    return row;
  }

  async health(): Promise<Health | null> {
    return { ok: true, store: "mock", live: { elevenlabs: false, arize: false, surreal: false } };
  }

  async runs(): Promise<RunInfo[]> {
    return SEEDED_RUNS;
  }

  async disasters(): Promise<Disaster[]> {
    return clone(this.data.disasters) as Disaster[];
  }

  async board(runId: string): Promise<Board> {
    await wait(60);
    const disasterId = this.disasterOf(runId);
    const own = <T extends { run_id?: string; disaster_id?: string }>(rows: T[]) =>
      rows.filter((r) => r.run_id === runId && r.disaster_id === disasterId);
    const d = this.data;
    return clone({
      run_id: runId,
      disaster: d.disasters.find((x) => x.id === disasterId)!,
      organizations: d.organizations,
      survivors: own(d.survivors as Board["survivors"]).map(({ id, run_id, disaster_id, created_at, display_name, language, call_opt_in }) => ({
        id, run_id, disaster_id, created_at, display_name, language, call_opt_in,
      })),
      requests: own(d.requests as RelayRequest[]),
      calls: own(d.calls as RelayCall[]),
      verifications: own(d.verifications as Verification[]),
      lessons: (d.lessons as Lesson[]).filter(
        (l) => (l.source_run_id === runId && l.source_disaster_id === disasterId) || (l.source_disaster_id !== disasterId && l.approved === true && l.approved_at),
      ),
      evaluations: own(d.evaluations as Board["evaluations"]),
      system_events: own(d.system_events as SystemEvent[]),
      as_of: nowIso(),
    }) as Board;
  }

  async report(runId: string, input: { disaster_id: string; survivor_id: string; text: string }): Promise<ReportResult> {
    await wait();
    const disasterId = this.disasterOf(runId);
    if (input.disaster_id !== disasterId) throw new RelayError("out-of-scope disaster", 404);
    if (!input.text.trim()) throw new RelayError("text is required", 400);
    const survivor = (this.data.survivors as Board["survivors"]).find((s) => s.id === input.survivor_id && s.run_id === runId);
    if (!survivor) throw new RelayError("unknown survivor", 404);
    const reportId = this.id("report");
    const reason = detectEmergency(input.text);
    if (reason) {
      // Immediate human escalation, recorded before any extraction. Never creates or resolves a request.
      this.event(runId, "intake", "human_escalation", survivor.id, { reason, report_id: reportId });
      return { requests: [], escalated: true, message: EMERGENCY_LINE };
    }
    this.event(runId, "intake", "report_received", survivor.id, { report_id: reportId });
    const conditions = conditionsOf(input.text);
    const requests = categoriesOf(input.text).map((category) => {
      const row: RelayRequest = {
        id: this.id(`${runId.replace("demo-", "")}-${category}`),
        ...this.core(runId),
        survivor_id: survivor.id,
        category,
        description: `${category[0].toUpperCase()}${category.slice(1)} requested in survivor report.`,
        status: "open",
        due_at: null,
        organization_id: null,
        promised_at: null,
        source_report_id: reportId,
        conditions,
      };
      (this.data.requests as RelayRequest[]).push(row);
      this.event(runId, "recovery", "request_created", row.id);
      return clone(row);
    });
    return { requests };
  }

  async claim(runId: string, requestId: string, input: { organization_id: string; promised_at: string }) {
    await wait();
    const row = this.request(runId, requestId);
    const org = this.data.organizations.find((o) => o.id === input.organization_id);
    if (!org) throw new RelayError("unknown organization", 404);
    if (row.status !== "open" && row.status !== "reopened") throw new RelayError("request already claimed or closed", 409);
    if (!org.capabilities.includes(row.category)) throw new RelayError("organization does not support this category", 400);
    if (Number.isNaN(Date.parse(input.promised_at)) || !/(Z|[+-]\d\d:?\d\d)$/.test(input.promised_at)) {
      throw new RelayError("promised_at must be an ISO timestamp with timezone", 400);
    }
    Object.assign(row, { status: "claimed", organization_id: org.id, promised_at: input.promised_at });
    this.event(runId, "recovery", "request_claimed", requestId);
    return clone(row);
  }

  async deliver(runId: string, requestId: string, input: { organization_id: string; notes: string }) {
    await wait();
    const row = this.request(runId, requestId);
    if (row.status !== "claimed" || row.organization_id !== input.organization_id) {
      throw new RelayError("delivery requires the claiming organization", 409);
    }
    Object.assign(row, { status: "awaiting_verification", delivery_notes: input.notes });
    this.event(runId, "recovery", "delivery_reported", requestId);
    return clone(row);
  }

  private applyVerification(runId: string, row: RelayRequest, received: boolean | null, source: Verification["source"], notes: string, evidence: string[]) {
    const verification: Verification = {
      id: this.id("verification"),
      ...this.core(runId),
      request_id: row.id,
      received,
      source,
      evidence_ids: evidence,
      notes,
    };
    (this.data.verifications as Verification[]).push(verification);
    if (received === true) row.status = "resolved";
    else if (received === false) row.status = "reopened";
    this.event(runId, "recovery", "request_verified", row.id);
    if (received === false) this.event(runId, "recovery", "human_escalation", row.id, { reason: "delivery_not_received" });
    return verification;
  }

  async verify(runId: string, requestId: string, input: { received: boolean | null; notes: string }) {
    await wait();
    const row = this.request(runId, requestId);
    if (row.status !== "awaiting_verification" && row.status !== "reopened") throw new RelayError("request is not awaiting verification", 409);
    const verification = this.applyVerification(runId, row, input.received, "human_review", input.notes, []);
    return clone({ request: row, verification });
  }

  async queueFollowUp(runId: string, requestId: string): Promise<RelayCall> {
    await wait();
    const row = this.request(runId, requestId);
    if (row.status !== "awaiting_verification" && row.status !== "reopened") throw new RelayError("follow-up requires an unresolved delivery", 409);
    const survivor = (this.data.survivors as Board["survivors"]).find((s) => s.id === row.survivor_id)!;
    if (survivor.call_opt_in !== true) throw new RelayError("confirmed survivor call opt-in is required", 400);
    const call: RelayCall = {
      id: this.id("call"),
      ...this.core(runId),
      request_id: requestId,
      survivor_id: survivor.id,
      status: "queued",
      provider_conversation_id: null,
      outcome: "pending",
      summary: "",
      evidence_ids: [],
      mode: "scripted",
      disclosure: FIXED_DISCLOSURE,
    };
    (this.data.calls as RelayCall[]).push(call);
    this.event(runId, "recovery", "call_saved", call.id);
    return clone(call);
  }

  async startCall(runId: string, callId: string, answer: ScriptedAnswer) {
    await wait(260);
    const call = (this.data.calls as RelayCall[]).find((c) => c.id === callId && c.run_id === runId);
    if (!call) throw new RelayError("unknown call", 404);
    if (call.status !== "queued") throw new RelayError("call is not queued, or attempt remains active; do not redial", 409);
    const row = this.request(runId, call.request_id);
    const survivor = (this.data.survivors as Board["survivors"]).find((s) => s.id === row.survivor_id)!;
    if (survivor.call_opt_in !== true) throw new RelayError("confirmed survivor call opt-in is required", 409);
    if (row.status !== "awaiting_verification" && row.status !== "reopened") throw new RelayError("request is not awaiting verification", 409);
    this.event(runId, "calls", "follow_up_started", row.id);
    const outcome = answer === "yes" ? "verified_received" : answer === "no" ? "not_received" : "no_answer";
    const received = answer === "yes" ? true : answer === "no" ? false : null;
    const summaries: Record<string, string> = {
      verified_received: "Survivor explicitly confirmed receipt of all promised assistance.",
      not_received: "Survivor reported assistance did not arrive; human follow-up required.",
      no_answer: "No survivor answer; receipt remains unverified.",
    };
    const evidence = answer === "no_answer" ? [] : [`${callId}:utterance:1`];
    Object.assign(call, { status: "completed", outcome, summary: summaries[outcome], evidence_ids: evidence, mode: "scripted", disclosure: FIXED_DISCLOSURE });
    this.event(runId, "calls", "follow_up_finished", row.id, { outcome, received });
    if (received !== null) this.applyVerification(runId, row, received, "survivor_call", summaries[outcome], evidence);
    return clone({ call, request: row });
  }

  async recommendations(runId: string, requestId: string): Promise<Recommendation[] | null> {
    await wait(80);
    const row = this.request(runId, requestId);
    const disasterId = this.disasterOf(runId);
    const have = new Set([row.category, ...(row.conditions ?? [])]);
    return (this.data.lessons as Lesson[])
      .filter((l) => l.source_disaster_id !== disasterId && l.approved === true && l.approved_at)
      .map((l) => ({ lesson: l, matched: l.conditions.filter((c) => have.has(c)) }))
      .filter((m) => m.matched.length > 0)
      .map(({ lesson, matched }) => ({
        lesson_id: lesson.id,
        summary: lesson.summary,
        recommendation: lesson.recommendation,
        matched_conditions: matched,
        source_disaster_id: lesson.source_disaster_id,
        source_outcomes: lesson.source_outcome_ids.flatMap((id) => {
          const v = (this.data.verifications as Verification[]).find((x) => x.id === id);
          return v ? [{ id: v.id, received: v.received, notes: v.notes, source: v.source }] : [];
        }),
        applicability: `Applies to: ${lesson.conditions.join(" + ")}. Matched here: ${matched.join(", ")}.`,
      }));
  }

  async draftLesson(runId: string, input: { source_outcome_ids: string[]; summary: string; conditions: string[]; recommendation: string }) {
    await wait();
    const disasterId = this.disasterOf(runId);
    if (!input.source_outcome_ids.length) throw new RelayError("lesson requires verified source outcomes", 400);
    const outcomes = input.source_outcome_ids.map((id) => {
      const v = (this.data.verifications as Verification[]).find((x) => x.id === id && x.run_id === runId);
      if (!v) throw new RelayError("unknown or out-of-scope record", 404);
      return v;
    });
    if (!outcomes.some((v) => v.received === true)) throw new RelayError("lesson requires at least one confirmed receipt", 400);
    if (!input.summary.trim() || !input.recommendation.trim()) throw new RelayError("summary and recommendation are required", 400);
    const text = `${input.summary} ${input.recommendation} ${input.conditions.join(" ")}`;
    const names = (this.data.survivors as Board["survivors"]).map((s) => s.display_name.toLowerCase());
    if (/[\w.+-]+@[\w.-]+|(?:\+?\d[ ().-]*){7,}/.test(text) || names.some((n) => text.toLowerCase().includes(n))) {
      throw new RelayError("lesson must be de-identified", 400);
    }
    const lesson: Lesson = {
      id: this.id("lesson"),
      source_run_id: runId,
      source_disaster_id: disasterId,
      source_outcome_ids: input.source_outcome_ids,
      summary: input.summary,
      conditions: input.conditions,
      recommendation: input.recommendation,
      approved: false,
      approved_at: null,
      created_at: nowIso(),
    };
    (this.data.lessons as Lesson[]).push(lesson);
    this.event(runId, "recovery", "lesson_drafted", lesson.id);
    return clone(lesson);
  }

  async approveLesson(runId: string, lessonId: string) {
    await wait();
    const lesson = (this.data.lessons as Lesson[]).find((l) => l.id === lessonId && l.source_run_id === runId);
    if (!lesson) throw new RelayError("unknown lesson", 404);
    Object.assign(lesson, { approved: true, approved_at: nowIso() });
    this.event(runId, "recovery", "lesson_approved", lessonId);
    return clone(lesson);
  }

  async compare(runId: string): Promise<CompareResult> {
    await wait(500);
    const disasterId = this.disasterOf(runId);
    if (disasterId !== "demo-storm-2026") throw new RelayError("no evaluation cases for this run", 400);
    const recorded = clone(compareFixture) as CompareResult;
    // Recorded output of the real backend comparison over data/demo/held_out.json (not computed in the browser).
    const evaluations = recorded.evaluations.map((e) => ({ ...e, ...this.core(runId), id: this.id("evaluation") }));
    const board = this.data.evaluations as Board["evaluations"];
    if (!board.some((e) => e.run_id === runId)) {
      board.push(...evaluations);
      this.event(runId, "recovery", "evaluation_saved", evaluations[0].experiment_id);
    }
    return { ...recorded, evaluations: board.filter((e) => e.run_id === runId) };
  }

  async reset(): Promise<boolean> {
    this.data = clone(seed);
    return true;
  }
}

/** Held-out cases the recorded comparison was run on (for display only). */
export const HELD_OUT_COUNT = (compareFixture as CompareResult).case_count ?? 0;
