import { describe, expect, it, vi } from "vitest";
import { mockSnapshot as m } from "../mock";
import { ReplayAdapter } from "./adapter";

const RUN = m.run.run_id;
function api(snapshot = m) {
  const fetchImpl = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
    const path = String(url);
    if (init?.method && init.method !== "GET") return new Response("{}", { status: 405 });
    if (path.endsWith("/runs")) return Response.json({ runs: [{ run_id: RUN, now_ts: m.now_ts }] });
    return Response.json(snapshot);
  });
  return { adapter: new ReplayAdapter("/api/replay", fetchImpl as unknown as typeof fetch), fetchImpl };
}

describe("ReplayAdapter", () => {
  it("reads the run once and keeps decisions in a sandbox, never writing back", async () => {
    const { adapter, fetchImpl } = api();
    expect((await adapter.runs()).map((r) => r.run_id)).toEqual([RUN]);
    await adapter.load(RUN);
    const p = await adapter.decide(RUN, "prop-s1_h_001", "approved", undefined, 303.2);
    expect(p).toMatchObject({ status: "approved", status_ts: 303.2 });
    const again = await adapter.load(RUN);
    expect(again.decisions["prop-s1_h_001"]?.status).toBe("approved");
    expect(fetchImpl.mock.calls.map(([, init]) => init?.method ?? "GET")).toEqual(["GET", "GET"]);
    expect(fetchImpl).toHaveBeenCalledTimes(2); // runs + one console read
    await expect(adapter.decide(RUN, "prop-s1_h_001", "dismissed", "Wrong household match")).rejects.toThrow(/already approved/);
  });

  it("escalates from Call View inside the sandbox", async () => {
    const { adapter } = api();
    const p = await adapter.escalate(RUN, "call-s1_h_001-1");
    expect(p).toMatchObject({ kind: "human_escalation", status: "pending", urgent: true });
    expect((await adapter.load(RUN)).proposals.some((x) => x._id === p._id)).toBe(true);
  });

  it("rejects a payload carrying another run's documents", async () => {
    const leaky = { ...m, proposals: [...m.proposals, { ...m.proposals[0]!, _id: "x", run_id: "other-run" }] };
    const { adapter } = api(leaky);
    await expect(adapter.load(RUN)).rejects.toThrow(/other-run/);
  });
});
