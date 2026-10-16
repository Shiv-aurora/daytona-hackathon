import { describe, expect, it } from "vitest";
import { MockAdapter } from "./adapter";
import { mockSnapshot } from "./mock";

const RUN = mockSnapshot.run.run_id;
const pendingId = () => mockSnapshot.proposals.find((p) => p.status === "pending")!._id;

describe("MockAdapter", () => {
  it("approves a pending proposal and records the decision", async () => {
    const a = new MockAdapter();
    const p = await a.decide(RUN, pendingId(), "approved");
    expect(p.status).toBe("approved");
    const snap = await a.load(RUN);
    expect(snap.proposals.find((x) => x._id === p._id)?.status).toBe("approved");
    expect(snap.decisions[p._id]).toEqual({ status: "approved", ts: snap.now_ts, reason: null });
  });

  it("requires a reason to dismiss", async () => {
    const a = new MockAdapter();
    await expect(a.decide(RUN, pendingId(), "dismissed")).rejects.toThrow(/reason/);
    await expect(a.decide(RUN, pendingId(), "dismissed", "  ")).rejects.toThrow(/reason/);
    const p = await a.decide(RUN, pendingId(), "dismissed", "Duplicate of another proposal");
    expect((await a.load(RUN)).decisions[p._id].reason).toBe("Duplicate of another proposal");
  });

  it("never resets a decided proposal", async () => {
    const a = new MockAdapter();
    const id = pendingId();
    await a.decide(RUN, id, "approved");
    await expect(a.decide(RUN, id, "dismissed", "Wrong household match")).rejects.toThrow(/already approved/);
  });

  it("stamps status_ts and traces each decision", async () => {
    const a = new MockAdapter();
    const id = pendingId();
    const p = await a.decide(RUN, id, "approved");
    const snap = await a.load(RUN);
    expect(p.status_ts).toBe(snap.now_ts);
    expect(snap.system_events.at(-1)).toMatchObject({ run_id: RUN, module: "ui", action: "proposal_decided", proposal_id: id });
  });

  it("escalates a call to a person once", async () => {
    const a = new MockAdapter();
    const call = mockSnapshot.call_requests[0]._id;
    const p = await a.escalate(RUN, call);
    await a.escalate(RUN, call);
    const snap = await a.load(RUN);
    expect(p).toMatchObject({ kind: "human_escalation", status: "pending", urgent: true });
    expect(snap.proposals.filter((x) => x._id === p._id)).toHaveLength(1);
    await expect(a.escalate(RUN, "no-such-call")).rejects.toThrow(/no call/);
  });

  it("is run-scoped", async () => {
    const a = new MockAdapter();
    await expect(a.load("another-run")).rejects.toThrow(/unknown run/);
    await expect(a.decide("another-run", pendingId(), "approved")).rejects.toThrow(/unknown run/);
  });

  it("hands out copies, so callers cannot mutate its state", async () => {
    const a = new MockAdapter();
    const snap = await a.load(RUN);
    snap.proposals.forEach((p) => (p.status = "approved"));
    expect((await a.load(RUN)).proposals.filter((p) => p.status === "pending")).toHaveLength(3);
    expect(mockSnapshot.proposals.filter((p) => p.status === "pending")).toHaveLength(3);
  });
});
