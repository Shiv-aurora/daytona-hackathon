// Pure view helpers for the workspace: no React, no fetching. Unit-tested in selectors.test.ts.
import type { Board, Lesson, RelayCall, RelayRequest, RequestStatus, SystemEvent, Verification } from "./types";

export const STATUSES: RequestStatus[] = ["open", "claimed", "awaiting_verification", "reopened", "resolved"];

export const STATUS_META: Record<RequestStatus, { label: string; hint: string; tone: string; dot: string }> = {
  open: {
    label: "Open",
    hint: "Waiting for an organization to claim it",
    tone: "border-promise-open/30 bg-promise-open/10 text-promise-open",
    dot: "bg-promise-open",
  },
  claimed: {
    label: "Claimed",
    hint: "An organization promised delivery",
    tone: "border-agent/30 bg-agent/10 text-agent",
    dot: "bg-agent",
  },
  awaiting_verification: {
    label: "Awaiting verification",
    hint: "Delivery reported; receipt not yet confirmed",
    tone: "border-promise-due-soon/40 bg-promise-due-soon/10 text-promise-due-soon",
    dot: "bg-promise-due-soon",
  },
  reopened: {
    label: "Reopened",
    hint: "Receipt not confirmed; needs a human",
    tone: "border-promise-lapsed/30 bg-promise-lapsed/10 text-promise-lapsed",
    dot: "bg-promise-lapsed",
  },
  resolved: {
    label: "Resolved",
    hint: "Receipt confirmed with evidence",
    tone: "border-promise-kept/30 bg-promise-kept/10 text-promise-kept",
    dot: "bg-promise-kept",
  },
};

export const CATEGORY_LABEL: Record<string, string> = {
  food: "Food",
  supplies: "Supplies",
  transportation: "Transportation",
  shelter: "Shelter",
  repairs: "Repairs",
  medicine: "Medicine",
  other: "Other",
};

export const categoryLabel = (c: string) => CATEGORY_LABEL[c] ?? c.replace(/_/g, " ");
export const conditionLabel = (c: string) => c.replace(/_/g, " ");

const GROUP_ORDER: Record<RequestStatus, number> = { reopened: 0, open: 1, claimed: 2, awaiting_verification: 3, resolved: 4 };

/**
 * Work order for coordinators: by deadline, then by workflow status, then arrival. It never ranks people:
 * only request status and deadlines are used.
 */
export function sortRequests(requests: RelayRequest[]): RelayRequest[] {
  const deadline = (r: RelayRequest) => Date.parse(r.due_at ?? r.promised_at ?? "") || Number.POSITIVE_INFINITY;
  return [...requests].sort(
    (a, b) =>
      deadline(a) - deadline(b) ||
      GROUP_ORDER[a.status] - GROUP_ORDER[b.status] ||
      Date.parse(a.created_at) - Date.parse(b.created_at) ||
      a.id.localeCompare(b.id),
  );
}

export const orgName = (board: Board, id: string | null) =>
  id ? (board.organizations.find((o) => o.id === id)?.name ?? id) : "Unclaimed";

export const householdOf = (board: Board, survivorId: string) => board.survivors.find((s) => s.id === survivorId);

/** Everything the detail drawer shows for one request, kept as separate evidence tracks. */
export function requestStory(board: Board, request: RelayRequest) {
  const verifications = board.verifications
    .filter((v) => v.request_id === request.id)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  const calls = board.calls.filter((c) => c.request_id === request.id);
  const events = board.system_events
    .filter((e) => e.subject_id === request.id || calls.some((c) => c.id === e.subject_id) || e.details?.report_id === request.source_report_id)
    .sort((a, b) => Date.parse(a.created_at) - Date.parse(b.created_at));
  const delivered = ["awaiting_verification", "resolved"].includes(request.status) || events.some((e) => e.action === "delivery_reported");
  return { verifications, calls, events, delivered, latestVerification: verifications.at(-1) ?? null };
}

export function canCall(board: Board, request: RelayRequest) {
  const survivor = householdOf(board, request.survivor_id);
  const unresolved = request.status === "awaiting_verification" || request.status === "reopened";
  const queued = board.calls.find((c) => c.request_id === request.id && c.status === "queued");
  return { survivor, unresolved, optedIn: survivor?.call_opt_in === true, queued };
}

export function outcomeLabel(outcome: string): { label: string; tone: "good" | "bad" | "neutral" | "alert" } {
  switch (outcome) {
    case "verified_received":
      return { label: "Survivor confirmed receipt", tone: "good" };
    case "not_received":
      return { label: "Survivor reported it did not arrive", tone: "bad" };
    case "no_answer":
      return { label: "No answer — still unverified", tone: "neutral" };
    case "unverified":
      return { label: "Unclear — still unverified", tone: "neutral" };
    case "failed":
      return { label: "Call failed — still unverified", tone: "neutral" };
    case "refused_no_opt_in":
      return { label: "Refused: no confirmed opt-in", tone: "alert" };
    case "emergency_escalated":
      return { label: "Emergency — escalated to a human", tone: "alert" };
    case "pending":
      return { label: "Queued — not started", tone: "neutral" };
    default:
      return { label: outcome.replace(/_/g, " "), tone: "neutral" };
  }
}

const EVENT_TEXT: Record<string, string> = {
  "intake/report_received": "Report received",
  "intake/human_escalation": "Emergency detected: human escalation recorded before any other processing",
  "recovery/request_created": "Request created from report",
  "recovery/request_claimed": "Claimed by an organization with a promised time",
  "recovery/delivery_reported": "Organization reported delivery (not proof of receipt)",
  "recovery/request_verified": "Verification recorded separately",
  "recovery/human_escalation": "Escalated to a human: delivery not received",
  "calls/human_escalation": "Emergency on a call: immediate human escalation",
  "recovery/call_saved": "Follow-up call queued (opt-in confirmed)",
  "calls/follow_up_started": "Call started: fixed disclosure read first",
  "calls/follow_up_finished": "Call finished",
  "recovery/lesson_drafted": "Lesson drafted (not shared until approved)",
  "recovery/lesson_approved": "Lesson approved by a coordinator",
  "recovery/evaluation_saved": "Measured comparison saved",
};

export function eventText(e: SystemEvent): string {
  const known = EVENT_TEXT[`${e.module}/${e.action}`];
  if (known) return known;
  if (e.module === "demo_seed") return `Seeded: ${e.action.replace(/_/g, " ")}`;
  return `${e.module}: ${e.action.replace(/_/g, " ")}`;
}

export const isEscalation = (e: SystemEvent) => e.action === "human_escalation";

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

/** "in 45 min", "2 h overdue" — relative to a reference time, for promised delivery times. */
export function relTime(iso: string | null | undefined, now: number): string {
  if (!iso) return "no time promised";
  const diff = Date.parse(iso) - now;
  if (Number.isNaN(diff)) return "—";
  const mins = Math.round(Math.abs(diff) / 60000);
  const span = mins >= 120 ? `${Math.round(mins / 60)} h` : `${mins} min`;
  return diff >= 0 ? `due in ${span}` : `${span} overdue`;
}

export function lessonStatus(lesson: Lesson, board: Board): "approved" | "draft" | "historical" {
  if (lesson.source_disaster_id !== board.disaster.id) return "historical";
  return lesson.approved ? "approved" : "draft";
}

export type EvidenceTrack = { requestId: string; verifications: Verification[]; calls: RelayCall[] };
