// Scripted "Start demo" story. Everything about the phone line, speech-to-text, the triage model and the
// helper agents is SAMPLE content and is labelled that way in the UI. Only the state changes go through the
// real RelayApi (the in-browser MockApi in demo mode), so the board, drawer, Calls and Intelligence pages agree.
import { FIXED_DISCLOSURE, categoriesOf, conditionsOf, detectEmergency } from "./mock";
import type { CompareResult, Lesson, RelayApi, RelayRequest } from "./types";

export const DEMO_RUN = "demo-current";
export const DEMO_DISASTER = "demo-storm-2026";
export const DEMO_SURVIVOR = "current-survivor-1";

export interface TranscriptLine {
  speaker: "caller" | "agent" | "system";
  text: string;
  /** Offset from the start of the call, in ms at 1x. */
  atMs: number;
}

export interface Triage {
  needs: string[];
  conditions: string[];
  deadline: string;
  workload: string;
}

export type HelperStatus = "idle" | "working";
export interface HelperView {
  id: string;
  role: string;
  sandbox: string;
  status: HelperStatus;
  lastAction: string;
}
export type OrgPhase = "idle" | "tagging" | "claimed" | "delivered";

export interface Scene {
  callActive: boolean;
  callLines: number;
  emergency: "idle" | "checking" | "clear" | "tripped";
  emergencyMessage: string | null;
  triageLoading: boolean;
  triage: Triage | null;
  triageSkipped: boolean;
  requestIds: string[];
  orgs: Record<string, { phase: OrgPhase; category: string | null }>;
  helpers: HelperView[];
  followActive: boolean;
  followLines: number;
  followOutcome: "not_received" | null;
  alert: string | null;
  humanReview: boolean;
  lesson: Lesson | null;
  compare: CompareResult | null;
}

// Sample roles (not a real deployment).
export const HELPER_ROLES: Pick<HelperView, "id" | "role" | "sandbox">[] = [
  { id: "intake", role: "Intake", sandbox: "sbx-intake" },
  { id: "triage", role: "Triage", sandbox: "sbx-triage" },
  { id: "matcher", role: "Matcher", sandbox: "sbx-match" },
  { id: "caller", role: "Follow-up caller", sandbox: "sbx-caller" },
  { id: "verifier", role: "Verifier", sandbox: "sbx-verify" },
];

export const initialScene = (): Scene => ({
  callActive: false,
  callLines: 0,
  emergency: "idle",
  emergencyMessage: null,
  triageLoading: false,
  triage: null,
  triageSkipped: false,
  requestIds: [],
  orgs: {},
  helpers: HELPER_ROLES.map((h) => ({ ...h, status: "idle", lastAction: "Idle" })),
  followActive: false,
  followLines: 0,
  followOutcome: null,
  alert: null,
  humanReview: false,
  lesson: null,
  compare: null,
});

export interface DemoMemory {
  requests: RelayRequest[];
  orgFor: Record<string, string>;
}

export interface DemoCtx {
  api: RelayApi;
  runId: string;
  disasterId: string;
  survivorId: string;
  /** Merge into the on-screen scene. */
  patch: (p: Partial<Scene> | ((s: Scene) => Partial<Scene>)) => void;
  /** Pausable, speed-aware, skippable delay (instant in the headless runner). */
  wait: (ms: number) => Promise<void>;
  /** Reload the board after a state change. */
  refresh: () => Promise<void>;
  onEscalation?: (message: string) => void;
  mem: DemoMemory;
}

export interface DemoStep {
  id: string;
  stage: string;
  label: string;
  /** Dwell after the step finishes, so the audience can read it (ms at 1x). */
  delayMs: number;
  run: (ctx: DemoCtx) => Promise<void>;
}

export interface DemoScript {
  id: "main" | "safety";
  title: string;
  call: TranscriptLine[];
  followUp: TranscriptLine[];
  steps: DemoStep[];
}

// ---------------------------------------------------------------- sample transcripts

export const MAIN_CALL: TranscriptLine[] = [
  { speaker: "system", text: "Incoming call", atMs: 0 },
  { speaker: "agent", text: "Relay line. What do you need?", atMs: 1600 },
  { speaker: "caller", text: "We need food and blankets for the family.", atMs: 4400 },
  { speaker: "caller", text: "The road is blocked so we can't get out.", atMs: 7600 },
];

export const SAFETY_CALL: TranscriptLine[] = [
  { speaker: "system", text: "Incoming call", atMs: 0 },
  { speaker: "agent", text: "Relay line. What do you need?", atMs: 1200 },
  { speaker: "caller", text: "My father fell down and can't get up.", atMs: 3200 },
];

export const FOLLOW_UP: TranscriptLine[] = [
  { speaker: "agent", text: FIXED_DISCLOSURE, atMs: 0 },
  { speaker: "agent", text: "Did the food arrive?", atMs: 3400 },
  { speaker: "caller", text: "No, nobody came. The road is still blocked.", atMs: 6200 },
  { speaker: "agent", text: "Thank you. I am alerting a person on the team now.", atMs: 9000 },
];

export const EMERGENCY_INSTRUCTION = "Please hang up and call 911 now. I'm alerting a person on the recovery team.";

export const callerText = (lines: TranscriptLine[]) =>
  lines
    .filter((l) => l.speaker === "caller")
    .map((l) => l.text)
    .join(" ");

// ---------------------------------------------------------------- helpers

const helper = (ctx: DemoCtx, id: string, status: HelperStatus, lastAction: string) =>
  ctx.patch((s) => ({ helpers: s.helpers.map((h) => (h.id === id ? { ...h, status, lastAction } : h)) }));

async function stream(ctx: DemoCtx, lines: TranscriptLine[], key: "callLines" | "followLines") {
  let at = 0;
  for (let i = 0; i < lines.length; i++) {
    await ctx.wait(Math.max(0, lines[i].atMs - at));
    at = lines[i].atMs;
    ctx.patch({ [key]: i + 1 });
  }
}

const promisedAt = (hours = 3) => new Date(Date.now() + hours * 3600_000).toISOString();

const mainRequests = (ctx: DemoCtx) => {
  if (!ctx.mem.requests.length) throw new Error("No requests were created from the call.");
  return ctx.mem.requests;
};

const foodRequest = (ctx: DemoCtx) => mainRequests(ctx).find((r) => r.category === "food") ?? mainRequests(ctx)[0];

// ---------------------------------------------------------------- shared steps

const callStep = (lines: TranscriptLine[], who: string): DemoStep => ({
  id: "call",
  stage: "Call",
  label: "Incoming call",
  delayMs: 1500,
  async run(ctx) {
    ctx.patch({ callActive: true });
    helper(ctx, "intake", "working", `Transcribing ${who}`);
    await stream(ctx, lines, "callLines");
    helper(ctx, "intake", "idle", "Transcript ready");
  },
});

// ---------------------------------------------------------------- main script

const MAIN_STEPS: DemoStep[] = [
  callStep(MAIN_CALL, "call"),
  {
    id: "emergency",
    stage: "Emergency check",
    label: "Emergency check first",
    delayMs: 2000,
    async run(ctx) {
      ctx.patch({ emergency: "checking", callActive: false });
      await ctx.wait(1400);
      // The same code-owned check the backend runs, before any model sees the text.
      const hit = detectEmergency(callerText(MAIN_CALL));
      if (hit) throw new Error(`Unexpected emergency phrase in the main script: ${hit}`);
      ctx.patch({ emergency: "clear" });
    },
  },
  {
    id: "triage",
    stage: "Triage",
    label: "AI triage",
    delayMs: 2500,
    async run(ctx) {
      ctx.patch({ triageLoading: true });
      helper(ctx, "triage", "working", "Reading the transcript");
      await ctx.wait(3200);
      const text = callerText(MAIN_CALL);
      const needs = categoriesOf(text);
      const triage: Triage = {
        needs,
        conditions: conditionsOf(text),
        deadline: "Today, by 6 pm",
        workload: `${needs.length} deliveries · about ${needs.length * 1.5} h`,
      };
      ctx.patch({ triageLoading: false, triage });
      helper(ctx, "triage", "idle", `Found ${needs.length} needs`);
    },
  },
  {
    id: "dashboard",
    stage: "Dashboard",
    label: "Requests land",
    delayMs: 2500,
    async run(ctx) {
      const result = await ctx.api.report(ctx.runId, {
        disaster_id: ctx.disasterId,
        survivor_id: ctx.survivorId,
        text: callerText(MAIN_CALL),
      });
      if (result.escalated) throw new Error("The call was escalated; no requests were created.");
      ctx.mem.requests = result.requests;
      ctx.patch({ requestIds: result.requests.map((r) => r.id) });
      await ctx.refresh();
      helper(ctx, "matcher", "working", `Matching ${result.requests.length} requests to volunteers`);
      await ctx.wait(1200);
    },
  },
  {
    id: "claim",
    stage: "Volunteers claim",
    label: "Volunteers sign up",
    delayMs: 1800,
    async run(ctx) {
      const orgs = (await ctx.api.board(ctx.runId)).organizations;
      for (const request of mainRequests(ctx)) {
        const org = orgs.find((o) => o.capabilities.includes(request.category));
        if (!org) throw new Error(`No volunteer organization covers ${request.category}.`);
        ctx.patch((s) => ({ orgs: { ...s.orgs, [org.id]: { phase: "tagging", category: request.category } } }));
        helper(ctx, "matcher", "working", `Suggested ${org.name}`);
        await ctx.wait(2000);
        await ctx.api.claim(ctx.runId, request.id, { organization_id: org.id, promised_at: promisedAt() });
        ctx.mem.orgFor[request.id] = org.id;
        ctx.patch((s) => ({ orgs: { ...s.orgs, [org.id]: { phase: "claimed", category: request.category } } }));
        await ctx.refresh();
        await ctx.wait(1200);
      }
      helper(ctx, "matcher", "idle", "Matches confirmed by volunteers");
    },
  },
  {
    id: "delivery",
    stage: "Delivery",
    label: "Delivery reported",
    delayMs: 2000,
    async run(ctx) {
      for (const request of mainRequests(ctx)) {
        const orgId = ctx.mem.orgFor[request.id];
        await ctx.api.deliver(ctx.runId, request.id, { organization_id: orgId, notes: "Left at the door" });
        ctx.patch((s) => ({ orgs: { ...s.orgs, [orgId]: { phase: "delivered", category: request.category } } }));
        await ctx.refresh();
        await ctx.wait(1600);
      }
    },
  },
  {
    id: "helper-call",
    stage: "Helper call",
    label: "Helper calls the household",
    delayMs: 2500,
    async run(ctx) {
      const food = foodRequest(ctx);
      helper(ctx, "caller", "working", "Calling the household");
      const call = await ctx.api.queueFollowUp(ctx.runId, food.id);
      await ctx.refresh();
      ctx.patch({ followActive: true });
      await stream(ctx, FOLLOW_UP, "followLines");
      await ctx.api.startCall(ctx.runId, call.id, "no");
      ctx.patch({ followActive: false, followOutcome: "not_received" });
      await ctx.refresh();
      helper(ctx, "caller", "idle", "Household: food did not arrive");
      // Other households confirm in their own calls (sample): receipt is verified separately from delivery.
      for (const other of mainRequests(ctx).filter((r) => r.id !== food.id)) {
        const c = await ctx.api.queueFollowUp(ctx.runId, other.id);
        await ctx.api.startCall(ctx.runId, c.id, "yes");
      }
      await ctx.refresh();
    },
  },
  {
    id: "reopen",
    stage: "Reopen + alert",
    label: "Reopened, a person is alerted",
    delayMs: 1800,
    async run(ctx) {
      const food = foodRequest(ctx);
      ctx.patch({ alert: "Food did not arrive. A person was alerted." });
      helper(ctx, "verifier", "working", "Reopened the request");
      await ctx.wait(3600);
      // The organization re-delivers; the request is not closed until a person verifies it.
      const orgId = ctx.mem.orgFor[food.id];
      await ctx.api.claim(ctx.runId, food.id, { organization_id: orgId, promised_at: promisedAt(1) });
      ctx.patch((s) => ({ orgs: { ...s.orgs, [orgId]: { phase: "claimed", category: food.category } } }));
      await ctx.refresh();
      await ctx.wait(900);
      await ctx.api.deliver(ctx.runId, food.id, { organization_id: orgId, notes: "Re-delivered to the accessible handoff point" });
      ctx.patch((s) => ({ orgs: { ...s.orgs, [orgId]: { phase: "delivered", category: food.category } } }));
      await ctx.refresh();
    },
  },
  {
    id: "resolve",
    stage: "Resolve",
    label: "Human review resolves it",
    delayMs: 2000,
    async run(ctx) {
      const food = foodRequest(ctx);
      ctx.patch({ humanReview: true });
      await ctx.wait(2800);
      await ctx.api.verify(ctx.runId, food.id, { received: true, notes: "Coordinator confirmed receipt after re-delivery." });
      ctx.patch({ humanReview: false, alert: null });
      helper(ctx, "verifier", "idle", "Receipt confirmed by a person");
      await ctx.refresh();
    },
  },
  {
    id: "lesson",
    stage: "Lesson",
    label: "Lesson drafted and approved",
    delayMs: 2500,
    async run(ctx) {
      const food = foodRequest(ctx);
      const board = await ctx.api.board(ctx.runId);
      const ids = board.verifications.filter((v) => v.request_id === food.id).map((v) => v.id);
      const draft = await ctx.api.draftLesson(ctx.runId, {
        source_outcome_ids: ids,
        summary: "A reported delivery did not arrive where the road was blocked; a re-delivery was confirmed by a person.",
        conditions: ["food", "access_blocked"],
        recommendation: "Agree an accessible handoff point before delivery; verify receipt separately afterwards.",
      });
      await ctx.refresh();
      await ctx.wait(2500);
      const lesson = await ctx.api.approveLesson(ctx.runId, draft.id);
      ctx.patch({ lesson });
      await ctx.refresh();
    },
  },
  {
    id: "measure",
    stage: "Measure",
    label: "Measured with vs without history",
    delayMs: 3000,
    async run(ctx) {
      const compare = await ctx.api.compare(ctx.runId);
      ctx.patch({ compare });
      await ctx.refresh();
    },
  },
];

// ---------------------------------------------------------------- safety script

const SAFETY_STEPS: DemoStep[] = [
  callStep(SAFETY_CALL, "call"),
  {
    id: "emergency",
    stage: "Emergency check",
    label: "Emergency check trips first",
    delayMs: 2500,
    async run(ctx) {
      ctx.patch({ emergency: "checking", callActive: false });
      await ctx.wait(1200);
      const text = callerText(SAFETY_CALL);
      if (!detectEmergency(text)) throw new Error("The safety script should trip the emergency check.");
      ctx.patch({ emergency: "tripped", emergencyMessage: EMERGENCY_INSTRUCTION, triageSkipped: true });
      // Recorded as an escalation before any triage; creates no request.
      const result = await ctx.api.report(ctx.runId, { disaster_id: ctx.disasterId, survivor_id: ctx.survivorId, text });
      if (!result.escalated) throw new Error("The backend did not escalate the emergency.");
      ctx.onEscalation?.(result.message ?? EMERGENCY_INSTRUCTION);
      await ctx.refresh();
    },
  },
  {
    id: "alert",
    stage: "Human alerted",
    label: "A person is alerted",
    delayMs: 3000,
    async run(ctx) {
      ctx.patch({ alert: "Emergency on the line. A person was alerted. No request created." });
      helper(ctx, "verifier", "working", "Paged a person");
      await ctx.wait(1500);
    },
  },
];

export const MAIN_SCRIPT: DemoScript = { id: "main", title: "Start demo", call: MAIN_CALL, followUp: FOLLOW_UP, steps: MAIN_STEPS };
export const SAFETY_SCRIPT: DemoScript = { id: "safety", title: "Safety demo", call: SAFETY_CALL, followUp: [], steps: SAFETY_STEPS };
export const SCRIPTS = { main: MAIN_SCRIPT, safety: SAFETY_SCRIPT } as const;

/** Nominal run time at 1x, in seconds (waits inside steps are not counted; see the runner for real time). */
export const totalDwellSeconds = (script: DemoScript) => script.steps.reduce((n, s) => n + s.delayMs, 0) / 1000;

/** Run a script to the end with no timers or UI: used by tests. Returns the final scene. */
export async function runScriptHeadless(
  script: DemoScript,
  base: { api: RelayApi; runId?: string; disasterId?: string; survivorId?: string },
): Promise<Scene> {
  let scene = initialScene();
  const ctx: DemoCtx = {
    api: base.api,
    runId: base.runId ?? DEMO_RUN,
    disasterId: base.disasterId ?? DEMO_DISASTER,
    survivorId: base.survivorId ?? DEMO_SURVIVOR,
    patch: (p) => {
      scene = { ...scene, ...(typeof p === "function" ? p(scene) : p) };
    },
    wait: async () => undefined,
    refresh: async () => undefined,
    mem: { requests: [], orgFor: {} },
  };
  for (const step of script.steps) await step.run(ctx);
  return scene;
}
