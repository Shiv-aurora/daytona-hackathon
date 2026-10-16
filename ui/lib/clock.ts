// Playback clock. A snapshot holds everything recorded up to its now_ts (the run head). atTime shows
// the run as it stood at an earlier sim time: later documents are hidden and later status changes
// are rolled back, so the timeline, inbox, goal row and counters all advance together.
import type { ConsoleSnapshot } from "./adapter";

export function atTime(snap: ConsoleSnapshot, t: number): ConsoleSnapshot {
  if (t >= snap.now_ts) return snap;
  const eventTs = new Map(snap.events.map((e) => [e._id, e.ts]));
  return {
    ...snap,
    now_ts: t,
    events: snap.events.filter((e) => e.ts <= t),
    households: snap.households.map((h) => ({ ...h, applied_event_ids: h.applied_event_ids.filter((id) => (eventTs.get(id) ?? Infinity) <= t) })),
    promises: snap.promises
      .filter((p) => p.made_ts <= t)
      .map((p) => {
        if (p.status === "open" || (p.status_ts ?? p.due_ts) <= t) return p;
        const reopened = { ...p, status: "open" as const };
        delete reopened.status_ts;
        return reopened;
      }),
    proposals: snap.proposals
      .filter((p) => p.ts <= t)
      .map((p) => {
        const at = snap.decisions[p._id]?.ts ?? p.status_ts;
        return p.status !== "pending" && at !== undefined && at > t ? { ...p, status: "pending" } : p;
      }),
    decisions: Object.fromEntries(Object.entries(snap.decisions).filter(([, d]) => d.ts <= t)),
    registry: snap.registry.filter((r) => r.registered_ts === undefined || r.registered_ts <= t),
    call_requests: snap.call_requests.filter((c) => c.requested_ts <= t),
    system_events: snap.system_events.filter((s) => s.ts <= t),
    metrics: snap.metrics.filter((m) => m.ts <= t),
    policy_changes: snap.policy_changes.filter((c) => c.ts <= t),
  };
}

/**
 * When each needle becomes visible: its last required record, or Relay's proposal right after it.
 * A run without needle data jumps from proposal to proposal instead.
 */
export function needleTimes(snap: ConsoleSnapshot): number[] {
  if (!snap.needles?.length) return [...new Set(snap.proposals.map((p) => p.ts))].sort((a, b) => a - b);
  const eventTs = new Map(snap.events.map((e) => [e._id, e.ts]));
  const times: number[] = [];
  for (const n of snap.needles ?? []) {
    const ready = Math.max(...n.required_event_ids.map((id) => eventTs.get(id) ?? Infinity));
    if (!Number.isFinite(ready)) continue;
    const raised = snap.proposals.filter((p) => p.household_id === n.household_id && p.ts >= ready).sort((a, b) => a.ts - b.ts)[0];
    times.push(raised && raised.ts - ready <= 24 ? raised.ts : ready);
  }
  return times.sort((a, b) => a - b);
}

export const nextNeedle = (snap: ConsoleSnapshot, t: number) => needleTimes(snap).find((x) => x > t + 1e-6) ?? null;
