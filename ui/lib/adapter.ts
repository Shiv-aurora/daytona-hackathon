// Console data adapter. MockAdapter runs without a backend; LiveAdapter (lib/live/client.ts)
// reads and writes one run through the Relay run API documented there. Both are run-scoped.
import { PROPOSAL_STATUS, type Proposal } from "./contracts";
import { mockSnapshot, type ConsoleSnapshot } from "./mock";

export type { ConsoleSnapshot, Decision } from "./mock";

export interface ConsoleAdapter {
  /** Runs the user can pick from. */
  runs(): Promise<{ run_id: string; scenario_id?: string; now_ts?: number }[]>;
  /** Everything the console shows for one run. */
  load(runId: string): Promise<ConsoleSnapshot>;
  /**
   * Coordinator decision. Forward-only: a decided proposal is never reset. `at` is the sim time
   * of a decision made while playing back a recorded run; a live relay stamps its own time.
   */
  decide(runId: string, proposalId: string, status: "approved" | "dismissed", reason?: string, at?: number): Promise<Proposal>;
  /** Human escalation from Call View: an urgent pending proposal for a person to act on. */
  escalate(runId: string, callId: string): Promise<Proposal>;
}

export const humanEscalationId = (callId: string) => `${callId}:human`;

/** In-memory adapter over the mock run. Decisions live only in this browser tab. */
export class MockAdapter implements ConsoleAdapter {
  private state: ConsoleSnapshot;

  constructor(snapshot: ConsoleSnapshot = mockSnapshot) {
    this.state = structuredClone(snapshot);
  }

  private checkRun(runId: string) {
    if (runId !== this.state.run.run_id) throw new Error(`unknown run ${runId}`);
  }

  private trace(action: string, subject: string, detail: Record<string, unknown>, ts = this.state.now_ts) {
    const s = this.state;
    s.system_events.push({ _id: `ui:${action}:${subject}`, run_id: s.run.run_id, module: "ui", action, ts, ...detail });
  }

  async runs() {
    return [{ run_id: this.state.run.run_id, scenario_id: this.state.run.scenario_id, now_ts: this.state.now_ts }];
  }

  async load(runId: string) {
    this.checkRun(runId);
    return structuredClone(this.state);
  }

  async decide(runId: string, proposalId: string, status: "approved" | "dismissed", reason?: string, at?: number) {
    this.checkRun(runId);
    const p = this.state.proposals.find((x) => x._id === proposalId && x.run_id === runId);
    if (!p) throw new Error(`no proposal ${proposalId} in run ${runId}`);
    const when = Math.min(at ?? this.state.now_ts, this.state.now_ts);
    // During playback a recorded decision that lies in the future has not happened yet.
    const recorded = this.state.decisions[proposalId]?.ts ?? p.status_ts;
    if (p.status !== PROPOSAL_STATUS.pending && !(recorded !== undefined && recorded > when)) throw new Error(`proposal ${proposalId} is already ${p.status}`);
    if (status === "dismissed" && !reason?.trim()) throw new Error("a dismissal needs a reason");
    const why = status === "dismissed" ? reason!.trim() : null;
    Object.assign(p, { status, status_ts: when });
    this.state.decisions[proposalId] = { status, ts: when, reason: why };
    this.trace("proposal_decided", proposalId, { proposal_id: proposalId, decision: status, ...(why ? { reason: why } : {}) }, when);
    return structuredClone(p);
  }

  async escalate(runId: string, callId: string) {
    this.checkRun(runId);
    const s = this.state;
    const call = s.call_requests.find((c) => c._id === callId && c.run_id === runId);
    if (!call) throw new Error(`no call ${callId} in run ${runId}`);
    const id = humanEscalationId(callId);
    let p = s.proposals.find((x) => x._id === id);
    if (!p) {
      const result = s.events.find((e) => (e as { call_id?: string }).call_id === callId);
      p = {
        _id: id, run_id: runId, scenario_id: s.run.scenario_id, household_id: call.household_id, kind: "human_escalation",
        status: PROPOSAL_STATUS.pending, reason: "Coordinator asked for a person to follow up from Call View.",
        ts: s.now_ts, cited_event_ids: result ? [result._id] : [], due_ts: s.now_ts + 1, queue: "welfare_check", urgent: true,
      };
      s.proposals.push(p);
      this.trace("human_escalation_requested", callId, { call_request_id: callId, proposal_id: id });
    }
    return structuredClone(p);
  }
}
