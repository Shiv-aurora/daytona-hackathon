// Pure data shaping for the charts. No React, no fetching: everything here is derived from a Board the server
// already scoped to one run and disaster, so no chart can show a record from another run. Unit-tested in viz.test.ts.
import type { Board, RelayCall, RelayRequest, RequestStatus, Verification } from "./types";

export type StatusCounts = Record<RequestStatus, number>;

export const emptyCounts = (): StatusCounts => ({ open: 0, claimed: 0, awaiting_verification: 0, reopened: 0, resolved: 0 });

/** Alias kept for call sites that read better as "status counts of …". */
export const statusCountsOf = (requests: RelayRequest[]) => countByStatus(requests);

export function countByStatus(requests: RelayRequest[]): StatusCounts {
  const out = emptyCounts();
  for (const r of requests) out[r.status] += 1;
  return out;
}

/* ------------------------------------------------------------------ lifecycle funnel */

export interface FunnelStage {
  id: "reported" | "claimed" | "delivered" | "verified";
  label: string;
  count: number;
}
export interface Funnel {
  total: number;
  stages: FunnelStage[];
  /** Delivered by an organization but not (yet) confirmed received. The product's core gap. */
  unverified: number;
  /** Delivered, then reported not received: back with a human. */
  reopened: number;
  /** Share of delivered requests whose receipt is confirmed; null until something has been delivered. */
  verifiedRate: number | null;
}

/**
 * "Reached stage" counts. A reopened request had a delivery report, so it counts as delivered, but never as
 * verified: an organization's report is not receipt.
 */
export function funnel(requests: RelayRequest[]): Funnel {
  const c = countByStatus(requests);
  const total = requests.length;
  const claimed = total - c.open;
  const delivered = c.awaiting_verification + c.resolved + c.reopened;
  const verified = c.resolved;
  return {
    total,
    stages: [
      { id: "reported", label: "Reported", count: total },
      { id: "claimed", label: "Claimed", count: claimed },
      { id: "delivered", label: "Delivery reported", count: delivered },
      { id: "verified", label: "Receipt verified", count: verified },
    ],
    unverified: delivered - verified,
    reopened: c.reopened,
    verifiedRate: delivered ? verified / delivered : null,
  };
}

/* ------------------------------------------------------------------ needs by category */

export interface CategoryRow {
  category: string;
  total: number;
  counts: StatusCounts;
}

export function categoryBreakdown(requests: RelayRequest[]): CategoryRow[] {
  const rows = new Map<string, CategoryRow>();
  for (const r of requests) {
    const row = rows.get(r.category) ?? { category: r.category, total: 0, counts: emptyCounts() };
    row.total += 1;
    row.counts[r.status] += 1;
    rows.set(r.category, row);
  }
  return [...rows.values()].sort((a, b) => b.total - a.total || a.category.localeCompare(b.category));
}

/* ------------------------------------------------------------------ per-request journey */

export type NodeState = "done" | "current" | "todo" | "bad";
export interface JourneyNode {
  id: "requested" | "claimed" | "delivered" | "verified";
  label: string;
  state: NodeState;
}

/** Four-node lane for one request. The last node is the independent check: it is never "done" from a delivery report. */
export function journey(request: RelayRequest): JourneyNode[] {
  const s = request.status;
  const verified: NodeState = s === "resolved" ? "done" : s === "reopened" ? "bad" : s === "awaiting_verification" ? "current" : "todo";
  return [
    { id: "requested", label: "Requested", state: "done" },
    { id: "claimed", label: "Claimed", state: s === "open" ? "current" : "done" },
    { id: "delivered", label: "Delivered", state: s === "open" ? "todo" : s === "claimed" ? "current" : "done" },
    { id: "verified", label: s === "reopened" ? "Not received" : "Verified", state: verified },
  ];
}

/* ------------------------------------------------------------------ promise clock */

export interface PromiseClock {
  /** 0..1 of the way from claim to promised time; >1 means overdue. */
  progress: number;
  overdue: boolean;
  minutesLeft: number;
}

/** Elapsed share of a promise window. Null when the request has no promise or the start time is unusable. */
export function promiseClock(request: RelayRequest, claimedAt: string | null, now: number): PromiseClock | null {
  if (request.status !== "claimed" || !request.promised_at) return null;
  const end = Date.parse(request.promised_at);
  const start = Date.parse(claimedAt ?? request.created_at);
  if (Number.isNaN(end) || Number.isNaN(start) || end <= start) return null;
  const progress = Math.max(0, (now - start) / (end - start));
  return { progress, overdue: now > end, minutesLeft: Math.round((end - now) / 60000) };
}

/** The time a request was claimed, taken from the audit trail (the claim event), when present. */
export function claimedAt(board: Board, request: RelayRequest): string | null {
  const e = board.system_events
    .filter((x) => x.subject_id === request.id && x.action === "request_claimed")
    .sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  return e?.created_at ?? null;
}

/* ------------------------------------------------------------------ organizations */

export interface CoverageCell {
  capable: boolean;
  /** Requests of this category currently assigned to this organization and still in motion. */
  active: number;
  resolved: number;
}
export interface Coverage {
  categories: string[];
  orgs: { id: string; name: string }[];
  cells: Record<string, Record<string, CoverageCell>>; // [category][orgId]
  /** Categories with an unresolved request and no organization able to supply them. */
  unmet: string[];
  /** Unresolved requests per category nobody has claimed. */
  unclaimed: Record<string, number>;
}

const IN_MOTION: RequestStatus[] = ["claimed", "awaiting_verification", "reopened"];

export function coverage(board: Board): Coverage {
  const categories = [...new Set([...board.organizations.flatMap((o) => o.capabilities), ...board.requests.map((r) => r.category)])].sort();
  const cells: Coverage["cells"] = {};
  for (const cat of categories) {
    cells[cat] = {};
    for (const org of board.organizations) {
      const mine = board.requests.filter((r) => r.category === cat && r.organization_id === org.id);
      cells[cat][org.id] = {
        capable: org.capabilities.includes(cat),
        active: mine.filter((r) => IN_MOTION.includes(r.status)).length,
        resolved: mine.filter((r) => r.status === "resolved").length,
      };
    }
  }
  const unresolved = board.requests.filter((r) => r.status !== "resolved");
  const unmet = categories.filter((cat) => unresolved.some((r) => r.category === cat) && !board.organizations.some((o) => o.capabilities.includes(cat)));
  const unclaimed: Record<string, number> = {};
  for (const r of board.requests) if (r.status === "open" || (r.status === "reopened" && !r.organization_id)) unclaimed[r.category] = (unclaimed[r.category] ?? 0) + 1;
  return { categories, orgs: board.organizations.map((o) => ({ id: o.id, name: o.name })), cells, unmet, unclaimed };
}

export interface OrgLoad {
  id: string;
  name: string;
  region: string;
  capabilities: string[];
  counts: StatusCounts;
  total: number;
  /** Resolved / (all requests the organization took on). Null with nothing assigned. */
  completion: number | null;
}

export function orgLoad(board: Board): OrgLoad[] {
  return board.organizations.map((o) => {
    const mine = board.requests.filter((r) => r.organization_id === o.id);
    const counts = countByStatus(mine);
    return {
      id: o.id,
      name: o.name,
      region: o.region,
      capabilities: o.capabilities,
      counts,
      total: mine.length,
      completion: mine.length ? counts.resolved / mine.length : null,
    };
  });
}

/* ------------------------------------------------------------------ calls and verification */

export type OutcomeGroup = "confirmed" | "not_received" | "unverified" | "queued" | "blocked";

export const OUTCOME_GROUP: Record<string, OutcomeGroup> = {
  verified_received: "confirmed",
  not_received: "not_received",
  unverified: "unverified",
  no_answer: "unverified",
  failed: "unverified",
  pending: "queued",
  refused_no_opt_in: "blocked",
  emergency_escalated: "blocked",
};

export const OUTCOME_GROUP_LABEL: Record<OutcomeGroup, string> = {
  confirmed: "Receipt confirmed",
  not_received: "Did not arrive",
  unverified: "Still unverified",
  queued: "Queued",
  blocked: "Stopped by a safeguard",
};

export function outcomeMix(calls: RelayCall[]): Record<OutcomeGroup, number> {
  const out: Record<OutcomeGroup, number> = { confirmed: 0, not_received: 0, unverified: 0, queued: 0, blocked: 0 };
  for (const c of calls) out[OUTCOME_GROUP[c.outcome] ?? "unverified"] += 1;
  return out;
}

export interface ConsentSplit {
  optedIn: number;
  declined: number;
}
export function consentSplit(board: Board): ConsentSplit {
  const optedIn = board.survivors.filter((s) => s.call_opt_in).length;
  return { optedIn, declined: board.survivors.length - optedIn };
}

/** How receipt was established: separate tracks, never merged with organization reports. */
export function verificationMix(verifications: Verification[]) {
  const out = { call: 0, human: 0, received: 0, notReceived: 0, unconfirmed: 0 };
  for (const v of verifications) {
    if (v.source === "survivor_call") out.call += 1;
    else out.human += 1;
    if (v.received === true) out.received += 1;
    else if (v.received === false) out.notReceived += 1;
    else out.unconfirmed += 1;
  }
  return out;
}

/* ------------------------------------------------------------------ lesson provenance */

export interface ProvenanceLink {
  lessonId: string;
  outcomeIds: string[];
  /** Requests in the viewed disaster whose category or conditions match the lesson. Never survivor data. */
  appliesTo: { id: string; category: string; matched: string[] }[];
}

/**
 * Which viewed-disaster requests an approved lesson from another disaster applies to, using only the lesson's
 * conditions and the request's category/conditions. Same-disaster lessons and drafts never apply anywhere.
 */
export function provenance(board: Board): ProvenanceLink[] {
  return board.lessons.map((l) => {
    const crosses = l.source_disaster_id !== board.disaster.id && l.approved;
    const appliesTo = crosses
      ? board.requests
          .filter((r) => r.status !== "resolved")
          .map((r) => {
            const have = new Set([r.category, ...(r.conditions ?? [])]);
            return { id: r.id, category: r.category, matched: l.conditions.filter((c) => have.has(c)) };
          })
          .filter((m) => m.matched.length > 0)
      : [];
    return { lessonId: l.id, outcomeIds: l.source_outcome_ids, appliesTo };
  });
}

/* ------------------------------------------------------------------ comparison */

export interface MetricDelta {
  metric: string;
  without: number | null;
  withHistory: number | null;
  /** Signed change in percentage points; null unless both were measured. */
  delta: number | null;
  direction: "better" | "worse" | "same" | "unmeasured";
}

/** `lowerIsBetter` metrics (false closures) flip the direction of improvement. */
export function metricDelta(metric: string, without: number | null | undefined, withHistory: number | null | undefined, lowerIsBetter = false): MetricDelta {
  const a = without ?? null;
  const b = withHistory ?? null;
  if (a === null || b === null) return { metric, without: a, withHistory: b, delta: null, direction: "unmeasured" };
  const delta = Math.round((b - a) * 1000) / 10;
  const direction = b === a ? "same" : (lowerIsBetter ? b < a : b > a) ? "better" : "worse";
  return { metric, without: a, withHistory: b, delta, direction };
}

