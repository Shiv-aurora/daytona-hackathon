// Test double for the Relay run API documented in client.ts. Serves in-memory run snapshots,
// records every request, can hold a run's responses until released, and applies decisions with
// the same forward-only rule the backend enforces (the UI must reconcile, not assume).
import type { ConsoleSnapshot } from "../adapter";

type Held = { runId: string; release: () => void };

export class FakeRelay {
  requests: { method: string; url: string; body?: unknown }[] = [];
  held: Held[] = [];
  holdRuns = new Set<string>();
  rejectDecisions: string | null = null;
  holdDecisions = false;

  constructor(public runs: Record<string, ConsoleSnapshot>) {}

  private json(status: number, body: unknown) {
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }

  fetch = async (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    const url = String(input);
    const method = init?.method ?? "GET";
    const body = init?.body ? JSON.parse(String(init.body)) : undefined;
    this.requests.push({ method, url, body });
    const parts = new URL(url).pathname.split("/").filter(Boolean).map(decodeURIComponent);
    const path = parts.slice(parts.indexOf("runs")); // ignore the base URL's own path
    if (path[0] !== "runs") return this.json(404, { error: "not found" });
    if (path.length === 1) return this.json(200, { runs: Object.values(this.runs).map((s) => ({ run_id: s.run.run_id, now_ts: s.now_ts })) });
    const snap = this.runs[path[1]];
    if (!snap) return this.json(404, { error: `run ${path[1]} not found` });
    if (path[2] === "console") {
      if (this.holdRuns.has(path[1])) await new Promise<void>((release) => this.held.push({ runId: path[1], release }));
      return this.json(200, structuredClone(snap));
    }
    if (path[2] === "proposals" && path[4] === "decision") {
      if (this.holdDecisions) await new Promise<void>((release) => this.held.push({ runId: `decision:${path[1]}`, release }));
      const p = snap.proposals.find((x) => x._id === path[3]);
      if (!p) return this.json(404, { error: "no such proposal in this run" });
      if (this.rejectDecisions) return this.json(409, { error: this.rejectDecisions });
      if (p.status !== "pending") return this.json(409, { error: `proposal is already ${p.status}` });
      if (body.status === "dismissed" && !body.reason) return this.json(400, { error: "reason required" });
      Object.assign(p, { status: body.status, status_ts: snap.now_ts });
      snap.decisions[p._id] = { status: body.status, ts: snap.now_ts, reason: body.reason ?? null };
      return this.json(200, p);
    }
    return this.json(404, { error: "not found" });
  };

  release(runId: string) {
    for (const h of this.held.filter((x) => x.runId === runId)) h.release();
    this.held = this.held.filter((x) => x.runId !== runId);
  }
}

/** A copy of `base` relabelled as another run, so two runs have distinguishable content. */
export function relabel(base: ConsoleSnapshot, runId: string, marker: string): ConsoleSnapshot {
  const s = structuredClone(base);
  s.run.run_id = runId;
  for (const key of ["households", "promises", "proposals", "call_requests", "system_events", "metrics", "policy_changes"] as const) {
    for (const d of s[key] as { run_id: string }[]) d.run_id = runId;
  }
  for (const e of s.events) if (e.run_id !== "scenario") e.run_id = runId;
  for (const p of s.proposals) p.reason = `${marker}: ${p.reason}`;
  for (const e of s.events) e.text = `${marker}: ${e.text}`;
  return s;
}
