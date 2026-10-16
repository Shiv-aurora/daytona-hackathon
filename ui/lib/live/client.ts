// LiveAdapter: the console's only path to live data. It talks to the Relay run API below over
// fetch; the browser never connects to the database and holds no database credentials. The API is
// implemented outside ui/ (W2 relay over db/ and memory/); ui/ only consumes it.
//
// Relay run API v0 (base URL: NEXT_PUBLIC_RELAY_API_URL, JSON everywhere)
//   GET  /runs                                         -> { runs: { run_id, scenario_id, now_ts }[] }
//   GET  /runs/{run_id}/console                        -> ConsoleSnapshot for that run only:
//        run (RunMeta), now_ts, households, promises, proposals, call_requests, system_events,
//        metrics, policy_changes (all run_id == {run_id}); events visible to the run
//        (scenario inputs with run_id "scenario" + this run's own, e.g. W3 call_result; keep W5's
//        `origin` field so real 311 rows are tagged "Real 311");
//        registry entries for the run's households; decisions (proposal_id -> {status, ts, reason}).
//        Optional: needles (scenario truth, for "next needle"), start_ts (playback start for recorded
//        runs), comparison ({relay, baseline} W4 Score objects; omitted until the evaluator has run).
//   POST /runs/{run_id}/proposals/{proposal_id}/decision  body { status: "approved"|"dismissed", reason? }
//        -> 200 Proposal after W2 decide_proposal (pending -> decision, forward-only)
//        -> 409 { error } if not pending; 400 { error } if invalid (e.g. dismissal without reason)
//   POST /runs/{run_id}/calls/{call_id}/escalate      -> 200 Proposal (urgent human follow-up) | 4xx { error }
import type { Proposal } from "../contracts";
import type { ConsoleAdapter, ConsoleSnapshot } from "../adapter";

type Fetch = typeof fetch;
export type RunListing = { run_id: string; scenario_id?: string; now_ts?: number };

export class RelayError extends Error {
  constructor(message: string, readonly status: number) {
    super(message);
  }
}

const RUN_SCOPED = ["households", "promises", "proposals", "call_requests", "system_events", "metrics", "policy_changes"] as const;

/** Reject a payload that carries any other run's document. */
export function assertRunScoped(snap: ConsoleSnapshot, runId: string) {
  if (snap.run?.run_id !== runId) throw new RelayError(`asked for run ${runId}, got run ${snap.run?.run_id}`, 502);
  for (const key of RUN_SCOPED) {
    const foreign = (snap[key] as { run_id?: string }[]).find((d) => d.run_id !== runId);
    if (foreign) throw new RelayError(`${key} contains a document from run ${foreign.run_id}`, 502);
  }
  const foreignEvent = snap.events.find((e) => e.run_id !== "scenario" && e.run_id !== runId);
  if (foreignEvent) throw new RelayError(`events contain a document from run ${foreignEvent.run_id}`, 502);
}

export class LiveAdapter implements ConsoleAdapter {
  constructor(private readonly base: string, private readonly fetchImpl: Fetch = (...a) => fetch(...a)) {}

  private url(...parts: string[]) {
    return `${this.base.replace(/\/$/, "")}/${parts.map(encodeURIComponent).join("/")}`;
  }

  private async call<T>(url: string, init?: RequestInit): Promise<T> {
    let res: Response;
    try {
      res = await this.fetchImpl(url, { cache: "no-store", ...init });
    } catch (e) {
      throw new RelayError(`relay unreachable (${(e as Error).message})`, 0);
    }
    const body = await res.json().catch(() => ({}));
    if (!res.ok) throw new RelayError((body as { error?: string }).error ?? `${res.status} ${res.statusText}`, res.status);
    return body as T;
  }

  async runs(): Promise<RunListing[]> {
    return (await this.call<{ runs: RunListing[] }>(this.url("runs"))).runs;
  }

  async load(runId: string) {
    const snap = await this.call<ConsoleSnapshot>(this.url("runs", runId, "console"));
    assertRunScoped(snap, runId);
    return snap;
  }

  async decide(runId: string, proposalId: string, status: "approved" | "dismissed", reason?: string) {
    if (status === "dismissed" && !reason?.trim()) throw new RelayError("a dismissal needs a reason", 400);
    const p = await this.call<Proposal>(this.url("runs", runId, "proposals", proposalId, "decision"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(status === "dismissed" ? { status, reason: reason!.trim() } : { status }),
    });
    if (p.run_id !== runId || p._id !== proposalId) throw new RelayError(`decision came back for ${p.run_id}/${p._id}`, 502);
    return p;
  }

  async escalate(runId: string, callId: string) {
    const p = await this.call<Proposal>(this.url("runs", runId, "calls", callId, "escalate"), { method: "POST" });
    if (p.run_id !== runId) throw new RelayError(`escalation came back for run ${p.run_id}`, 502);
    return p;
  }
}

/** The configured relay, or null when this deployment has none (the console then uses the mock run). */
export function relayBase(): string | null {
  return process.env.NEXT_PUBLIC_RELAY_API_URL?.trim() || null;
}
