import { describe, expect, it } from "vitest";
import { mockSnapshot } from "../mock";
import { LiveAdapter, RelayError } from "./client";
import { FakeRelay, relabel } from "./fake-relay";

const BASE = "http://relay.test/api";
const setup = () => {
  const relay = new FakeRelay({ "run-a": relabel(mockSnapshot, "run-a", "A"), "run-b": relabel(mockSnapshot, "run-b", "B") });
  return { relay, adapter: new LiveAdapter(BASE, relay.fetch) };
};
const pendingId = (runId: string, relay: FakeRelay) => relay.runs[runId].proposals.find((p) => p.status === "pending")!._id;

describe("LiveAdapter (Relay run API)", () => {
  it("names the run in every read and mutation", async () => {
    const { relay, adapter } = setup();
    await adapter.load("run-a");
    const id = pendingId("run-a", relay);
    await adapter.decide("run-a", id, "approved");
    await adapter.decide("run-a", pendingId("run-a", relay), "dismissed", "Duplicate of another proposal");
    const runScoped = relay.requests.filter((r) => !r.url.endsWith("/runs"));
    expect(runScoped.length).toBe(3);
    for (const r of runScoped) expect(r.url.startsWith(`${BASE}/runs/run-a/`)).toBe(true);
    expect(relay.requests[1]).toMatchObject({ method: "POST", url: `${BASE}/runs/run-a/proposals/${id}/decision`, body: { status: "approved" } });
    expect(relay.requests[2].body).toEqual({ status: "dismissed", reason: "Duplicate of another proposal" });
  });

  it("never sends a dismissal without a reason", async () => {
    const { relay, adapter } = setup();
    await expect(adapter.decide("run-a", pendingId("run-a", relay), "dismissed", "  ")).rejects.toThrow(/reason/);
    expect(relay.requests).toHaveLength(0);
  });

  it("rejects a payload that mixes in another run's documents", async () => {
    const { relay, adapter } = setup();
    relay.runs["run-a"].proposals.push(structuredClone(relay.runs["run-b"].proposals[0]));
    await expect(adapter.load("run-a")).rejects.toThrow(/proposals contains a document from run run-b/);
    const { relay: r2, adapter: a2 } = setup();
    r2.runs["run-a"].events.push(r2.runs["run-b"].events.find((e) => e.run_id === "run-b")!);
    await expect(a2.load("run-a")).rejects.toThrow(/events contain a document from run run-b/);
    const { relay: r3, adapter: a3 } = setup();
    r3.runs["run-a"].run.run_id = "run-b";
    await expect(a3.load("run-a")).rejects.toThrow(/asked for run run-a/);
  });

  it("surfaces backend rejections and outages as errors", async () => {
    const { relay, adapter } = setup();
    const id = pendingId("run-a", relay);
    await adapter.decide("run-a", id, "approved");
    await expect(adapter.decide("run-a", id, "dismissed", "x")).rejects.toThrow(/already approved/);
    const down = new LiveAdapter(BASE, async () => {
      throw new TypeError("Failed to fetch");
    });
    await expect(down.load("run-a")).rejects.toMatchObject({ status: 0 });
    await expect(down.load("run-a")).rejects.toBeInstanceOf(RelayError);
  });
});
