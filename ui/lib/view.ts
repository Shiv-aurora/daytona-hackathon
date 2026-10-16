// Pure selectors over a ConsoleSnapshot (mock or live). Definitions follow the runtime/DB code on main
// so the UI shows what the agent measures: runtime/goals.py goal_metrics, W2 last-contact semantics.
import type { CallResultEvent, Event, SystemEvent } from "./contracts";
import type { ConsoleSnapshot } from "./mock";


export const isCallResult = (e: Event): e is CallResultEvent => e.source === "call_result";

// ---- goal ------------------------------------------------------------------------------------
/** W1 goal state at its latest daily scoring (runtime.goals + runtime.silence metrics). Never invented:
 *  no goal metrics -> not scored; a scoring without promises_on_time_pct (nothing due) -> N/A. */
export type Goal = {
  scoredAt: number | null;
  onTimePct: number | null;
  due: number | null;
  met: number | null;
  open: number | null;
  silent: number | null;
  silentHouseholds: { household_id: string; name: string }[];
  policy: { version: number; leadHours: number | null; whatChanged: string } | null;
};

export function goalOf(snap: ConsoleSnapshot): Goal {
  const goalMetrics = snap.metrics.filter((m) => m.scope === "goal" && m.ts <= snap.now_ts);
  const scoredAt = goalMetrics.length ? Math.max(...goalMetrics.map((m) => m.ts)) : null;
  const at = new Map(goalMetrics.filter((m) => m.ts === scoredAt).map((m) => [m.name, m.value]));
  const pick = (name: string) => (at.has(name) ? at.get(name)! : null);
  const latestPolicy = [...snap.policy_changes].filter((c) => c.ts <= snap.now_ts).sort((a, b) => b.version - a.version)[0];
  const names = new Map(snap.households.map((h) => [h.household_id, h.name ?? h.household_id]));
  return {
    scoredAt,
    onTimePct: pick("promises_on_time_pct"),
    due: pick("promises_due"),
    met: pick("promises_met"),
    open: pick("promises_open"),
    silent: pick("silent_households"),
    silentHouseholds: snap.proposals
      .filter((p) => p.kind === "silence_check_in" && p.status === "pending")
      .map((p) => ({ household_id: p.household_id, name: names.get(p.household_id) ?? p.household_id })),
    policy: latestPolicy
      ? { version: latestPolicy.version, leadHours: latestPolicy.params.lead_hours ?? null, whatChanged: latestPolicy.what_changed }
      : null,
  };
}

// ---- trace -----------------------------------------------------------------------------------
export const STAGES = [
  ["event_in", "event in"],
  ["extracted", "extracted"],
  ["matched", "matched"],
  ["promise", "promise updated"],
  ["scheduled", "proposal / call scheduled"],
  ["policy", "policy adjusted"],
] as const;
export type Stage = (typeof STAGES)[number][0];

export function stageOf(s: SystemEvent): Stage {
  const purpose = String(s.purpose ?? "");
  switch (s.action) {
    case "llm_call":
    case "llm_output_rejected":
    case "llm_unavailable":
      return purpose === "decide" ? "scheduled" : "extracted";
    case "household_matched":
    case "household_unmatched":
      return "matched";
    case "promise_created":
    case "promise_kept":
      return "promise";
    case "status_changed":
      return s.collection === "promises" ? "promise" : "scheduled";
    case "policy_changed":
    case "goal_scored":
      return "policy";
    case "proposal_created":
    case "proposal_decided":
    case "call_scheduled":
    case "call_queued":
    case "call_skipped_no_opt_in":
    case "silence_escalated":
    case "emergency_escalated":
    case "human_escalation_requested":
    case "call_started": // W3 calls/agent.py
    case "call_refused_no_opt_in":
    case "call_failed":
      return "scheduled";
    default:
      return "event_in";
  }
}

/** Row category for the compact trace: every state pairs a glyph with a word. */
export type TraceKind = "tick" | "matched" | "promise" | "proposal" | "silence" | "cross" | "call" | "emergency" | "policy" | "goal" | "decision" | "model";
export const TRACE_KIND: Record<TraceKind, { glyph: string; label: string; cls: string }> = {
  tick: { glyph: "·", label: "Tick", cls: "text-muted-foreground" },
  matched: { glyph: "⇢", label: "Matched", cls: "text-ink" },
  promise: { glyph: "◯", label: "Promise", cls: "text-promise-open" },
  proposal: { glyph: "▣", label: "Proposal", cls: "text-agent" },
  silence: { glyph: "◔", label: "Silence", cls: "text-promise-due-soon" },
  cross: { glyph: "⧉", label: "Cross-service", cls: "text-promise-escalated" },
  call: { glyph: "☏", label: "Call", cls: "text-ink" },
  emergency: { glyph: "!", label: "Emergency", cls: "text-safety-tripped" },
  policy: { glyph: "◆", label: "Policy", cls: "text-agent" },
  goal: { glyph: "◎", label: "Goal", cls: "text-agent" },
  decision: { glyph: "✓", label: "Coordinator", cls: "text-promise-kept" },
  model: { glyph: "λ", label: "Model", cls: "text-muted-foreground" },
};

export function traceKind(s: SystemEvent): TraceKind {
  const kind = String(s.kind ?? "");
  switch (s.action) {
    case "tick_started":
    case "tick_completed":
      return "tick";
    case "household_matched":
    case "household_unmatched":
    case "event_applied":
      return "matched";
    case "promise_created":
    case "promise_kept":
      return "promise";
    case "status_changed":
      return s.collection === "promises" ? "promise" : "decision";
    case "silence_escalated":
      return "silence";
    case "proposal_created":
      return kind === "cross_service_check_in" ? "cross" : kind === "silence_check_in" ? "silence" : "proposal";
    case "emergency_escalated":
      return "emergency";
    case "policy_changed":
      return "policy";
    case "goal_scored":
      return "goal";
    case "proposal_decided":
    case "human_escalation_requested":
      return "decision";
    case "llm_call":
    case "llm_usage":
    case "llm_unavailable":
    case "llm_output_rejected":
    case "retrieval_filtered":
      return "model";
    default:
      return s.action.startsWith("call") ? "call" : "tick";
  }
}

/** Plain-language name of a trace step for coordinators and judges. */
export function traceLabel(s: SystemEvent): string {
  const d = s as Record<string, unknown>;
  switch (s.action) {
    case "household_matched":
      return "Matched to household";
    case "household_unmatched":
      return "No household match";
    case "event_applied":
      return "Added to memory";
    case "promise_created":
      return "Promise noted";
    case "promise_kept":
      return "Promise kept";
    case "status_changed":
      return d.collection === "promises" ? `Promise ${d.status}` : `Proposal ${d.status}`;
    case "proposal_created":
      return d.kind === "cross_service_check_in" ? "Several services flagged" : d.kind === "silence_check_in" ? "Silence check-in drafted" : "Proposal drafted";
    case "silence_escalated":
      return "Household gone quiet";
    case "call_scheduled":
      return "Call scheduled";
    case "call_queued":
      return "Call queued";
    case "call_started":
      return "Calling";
    case "call_result_logged":
      return `Call: ${String(d.outcome ?? "done").replaceAll("_", " ")}`;
    case "call_refused_no_opt_in":
    case "call_skipped_no_opt_in":
      return "Call blocked: no opt-in";
    case "call_failed":
      return "Call failed";
    case "emergency_escalated":
      return "Emergency: person paged";
    case "policy_changed":
      return `Policy v${d.version ?? "?"}`;
    case "goal_scored":
      return `Goal ${d.promises_on_time_pct == null ? "N/A" : `${fmtNum(d.promises_on_time_pct)}%`} on time`;
    case "proposal_decided":
      return `Coordinator ${d.decision}`;
    case "human_escalation_requested":
      return "Person follow-up requested";
    case "llm_call":
      return d.cached ? "Cache hit" : `Model: ${d.purpose ?? "call"}`;
    case "retrieval_filtered":
      return "Evidence retrieved";
    case "llm_output_rejected":
      return "Model output rejected";
    case "llm_unavailable":
      return "Model unavailable";
    default:
      return s.action.replaceAll("_", " ");
  }
}

const fmtNum = (v: unknown) => (typeof v === "number" ? (Number.isInteger(v) ? String(v) : v.toFixed(1)) : String(v));

/** One-line description of a trace entry from its detail fields. */
export function describe(s: SystemEvent): string {
  const d = s as Record<string, unknown>;
  const bits = [
    d.purpose && `${d.purpose}`,
    d.household_id && `household ${d.household_id}`,
    d.event_id && `event ${d.event_id}`,
    d.promise_id && `promise ${d.promise_id}`,
    d.proposal_id && `proposal ${d.proposal_id}`,
    d.call_request_id && `call ${d.call_request_id}`,
    d.decision && `${d.decision}`,
    d.reason && `"${d.reason}"`,
    d.outcome && `${d.outcome}`,
    d.matched_phrase && `heard "${d.matched_phrase}"`,
    d.what_changed && `${d.what_changed}`,
    d.metric_values && typeof d.metric_values === "object" &&
      `because ${Object.entries(d.metric_values as Record<string, unknown>).map(([k, v]) => `${k}=${fmtNum(v)}`).join(", ")}`,
    d.cached !== undefined && d.action === "llm_call" && (d.cached ? "cache hit" : "model call"),
    d.status && d.doc_id && `${d.doc_id} -> ${d.status}`,
    s.action === "goal_scored" &&
      `on time ${d.promises_on_time_pct == null ? "N/A" : `${fmtNum(d.promises_on_time_pct)}%`} · ${fmtNum(d.promises_met ?? 0)}/${fmtNum(d.promises_due ?? 0)} due met · ${fmtNum(d.silent_households ?? 0)} silent`,
  ].filter(Boolean);
  return bits.join(" · ");
}

/** Token counters from runtime "llm_call" trace entries (W1-C2): climbing total, per-call context. */
export function tokenSeries(trace: SystemEvent[]) {
  let total = 0;
  return trace
    .filter((s) => s.action === "llm_call")
    .map((s) => {
      const prompt = Number(s.prompt_tokens ?? 0);
      total += prompt + Number(s.completion_tokens ?? 0);
      return { ts: s.ts, total, context: prompt };
    });
}

// ---- calls -----------------------------------------------------------------------------------
export type Turn = { speaker: "relay" | "resident" | string; text: string };

export function parseTranscript(text: string): Turn[] {
  return text
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .map((line) => {
      const i = line.indexOf(": ");
      return i > 0 ? { speaker: line.slice(0, i), text: line.slice(i + 2) } : { speaker: "relay", text: line };
    });
}

export function callsOf(snap: ConsoleSnapshot, householdId?: string) {
  const results = new Map(snap.events.filter(isCallResult).map((e) => [e.call_id, e]));
  return snap.call_requests
    .filter((c) => !householdId || c.household_id === householdId)
    .map((request) => ({ request, result: results.get(request._id) ?? null }))
    .sort((a, b) => a.request.requested_ts - b.request.requested_ts);
}

export function callView(snap: ConsoleSnapshot, callId: string) {
  const call = callsOf(snap).find((c) => c.request._id === callId);
  if (!call) return null;
  const { request, result } = call;
  const household = snap.households.find((h) => h.household_id === request.household_id);
  const registry = snap.registry.find((r) => r.household_id === request.household_id);
  const proposal = snap.proposals.find((p) => p._id === request.proposal_id);
  const promise = snap.promises.find((p) => p._id === (request.promise_id ?? proposal?.promise_id));
  const events = new Map(snap.events.map((e) => [e._id, e]));
  // A transcript is shown only if it belongs to this run (defense in depth over the adapter check).
  const own = result && result.run_id === snap.run.run_id ? result : null;
  const turns = own ? parseTranscript(own.text) : [];
  const endTs = (result && result.run_id === snap.run.run_id ? result.ts : undefined) ?? request.requested_ts;
  return {
    request,
    result: own,
    status: (own?.outcome ?? "queued") as "queued" | CallResultEvent["outcome"],
    household,
    language: registry?.language ?? household?.language ?? null,
    promise: promise ?? null,
    turns,
    safety: {
      optIn: registry?.opt_in === true && own?.outcome !== "refused_no_opt_in",
      disclosure: turns[0]?.speaker === "relay",
      emergency: own?.outcome === "emergency_escalated",
      phrase: own?.emergency_phrase ?? null,
    },
    memory: (proposal?.cited_event_ids ?? []).map((id) => events.get(id)).filter((e): e is Event => !!e && e.ts <= endTs),
    reason: proposal?.reason ?? null,
    promiseChanges: snap.promises.filter(
      (p) => p.household_id === request.household_id && p.status_ts !== undefined && p.status_ts >= endTs,
    ),
    escalations: snap.proposals.filter((p) => p._id === `${request._id}:emergency` || p._id === `${request._id}:human`),
  };
}

// ---- policy ----------------------------------------------------------------------------------
const PARAM_TEXT: Record<string, (now: string, was: string) => string> = {
  lead_hours: (n, w) => `Acting ${n}h before deadlines (was ${w}h)`,
  call_interval_hours: (n, w) => `Calling every ${n}h (was ${w}h)`,
  silence_hours: (n, w) => `Checking on quiet households after ${n}h (was ${w}h)`,
};
const METRIC_TEXT: Record<string, (value: string, target: string) => string> = {
  promises_on_time_pct: (v, t) => `only ${v}% of promises were on time against a ${t}% target`,
  silent_households: (v, t) => `${v} households went quiet (limit ${t})`,
};

/**
 * One line on what the policy learner changed and why, from W1's own `what_changed` text
 * ("lead_hours 0 -> 12 (promises_on_time_pct 40 < 90 target)"). Unknown shapes are shown as-is.
 */
export function policyLine(c: { what_changed: string }): string {
  const m = c.what_changed.match(/^(\w+)\s+([\d.]+)\s*->\s*([\d.]+)\s*(?:\((.*)\))?$/);
  if (!m) return c.what_changed;
  const [, param, was, now, why] = m;
  const what = PARAM_TEXT[param!]?.(now!, was!) ?? `${param!.replace(/_/g, " ")} ${now} (was ${was})`;
  const r = why?.match(/^(\w+)\s+([\d.]+)\s*[<>]\s*([\d.]+)/);
  const because = r ? (METRIC_TEXT[r[1]!]?.(r[2]!, r[3]!) ?? why) : why;
  return because ? `${what} — ${because}` : what;
}
