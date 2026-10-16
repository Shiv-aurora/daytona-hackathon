// Replay adapter: reads a completed run through the read-only replay API (/api/replay, served from
// recorded snapshots through the API) and keeps the viewer's decisions in a sandboxed copy in
// this browser tab. Nothing is ever written back; reloading the page starts the replay fresh.
import { MockAdapter, type ConsoleAdapter, type ConsoleSnapshot } from "../adapter";
import { LiveAdapter } from "../live/client";

export const REPLAY_API = "/api/replay";

export class ReplayAdapter implements ConsoleAdapter {
  private readonly reader: LiveAdapter;
  private readonly sandboxes = new Map<string, Promise<MockAdapter>>();

  constructor(base = REPLAY_API, fetchImpl?: typeof fetch) {
    this.reader = new LiveAdapter(base, fetchImpl);
  }

  runs() {
    return this.reader.runs();
  }

  private sandbox(runId: string) {
    let s = this.sandboxes.get(runId);
    if (!s) {
      // LiveAdapter.load rejects any payload carrying another run's documents.
      s = this.reader.load(runId).then((snap: ConsoleSnapshot) => new MockAdapter(snap));
      s.catch(() => this.sandboxes.delete(runId)); // a failed read can be retried
      this.sandboxes.set(runId, s);
    }
    return s;
  }

  async load(runId: string) {
    return (await this.sandbox(runId)).load(runId);
  }

  async decide(runId: string, proposalId: string, status: "approved" | "dismissed", reason?: string, at?: number) {
    return (await this.sandbox(runId)).decide(runId, proposalId, status, reason, at);
  }

  async escalate(runId: string, callId: string) {
    return (await this.sandbox(runId)).escalate(runId, callId);
  }
}
