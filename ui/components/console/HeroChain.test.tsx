// @vitest-environment jsdom
// Mrs. Chen's chain recorded from a real local run (W5 data -> W1 runtime -> W2 decision -> W3 call).
import { cleanup, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { ConsoleSnapshot } from "@/lib/adapter";
import { CallRequest, CallResultEvent, Event, Household, Metric, PolicyChange, Proposal, RegistryEntry, RelayPromise, SystemEvent } from "@/lib/contracts";
import { LiveAdapter } from "@/lib/live/client";
import { FakeRelay } from "@/lib/live/fake-relay";
import recorded from "@/lib/live/fixtures/s1-hero-run.json";
import { CallView } from "@/components/call/CallView";
import { Console } from "./Console";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/console" }));
afterEach(cleanup);

const snap = recorded as unknown as ConsoleSnapshot;
const RUN = snap.run.run_id;
const adapter = () => new LiveAdapter("http://relay.test", new FakeRelay({ [RUN]: structuredClone(snap) }).fetch);
const callId = snap.call_requests[0]._id;

describe("Mrs. Chen hero chain from a recorded real run", () => {
  it("is valid against the shared contract shapes", () => {
    const check = (schema: { safeParse: (d: unknown) => { error?: { issues: unknown[] } } }, docs: unknown[]) => {
      for (const d of docs) expect(schema.safeParse(d).error?.issues ?? []).toEqual([]);
    };
    check(Household, snap.households);
    check(RelayPromise, snap.promises);
    check(Proposal, snap.proposals);
    check(CallRequest, snap.call_requests);
    check(SystemEvent, snap.system_events);
    check(Metric, snap.metrics);
    check(PolicyChange, snap.policy_changes);
    check(RegistryEntry, snap.registry);
    check(Event, snap.events.filter((e) => e.source !== "call_result"));
    check(CallResultEvent, snap.events.filter((e) => e.source === "call_result"));
    expect(JSON.stringify(snap)).not.toContain("callback_number");
  });

  it("renders household on Hollow Oak Lane -> lapsed promise -> approved proposal -> call result, with goal and policy", async () => {
    render(<Console adapter={adapter()} initialRun={RUN} />);
    await waitFor(() => expect(screen.getByRole("heading", { level: 2, name: "Mei Chen" })).toBeTruthy());
    const body = () => document.body.textContent ?? "";
    expect(body()).toContain("41-22 Hollow Oak Lane");
    expect(body()).toContain("Her son Wei is coming Tuesday");
    expect(screen.getAllByText("Lapsed").length).toBeGreaterThan(0);
    const decided = screen.getByRole("list", { name: "Decided proposals" });
    expect(within(decided).getByText("Mei Chen").closest("li")?.textContent).toContain("Approved");
    expect(within(screen.getByRole("list", { name: "Calls" })).getByText(/no answer/)).toBeTruthy();
    expect(screen.getByLabelText(/Promises on time/)).toBeTruthy();
    expect(body()).toContain("silent > 72h");
    expect(body()).toMatch(/Policy v\d+/);
  });

  it("opens the call with its motivating promise and cited visit note, from this run only", async () => {
    render(<CallView callId={callId} runId={RUN} adapter={adapter()} />);
    await waitFor(() => expect(screen.getByRole("heading", { level: 1 }).textContent).toContain("Mei Chen"));
    const body = document.body.textContent ?? "";
    expect(body).toContain("No answer");
    expect(body).toContain("Promise behind the call");
    expect(body).toContain("Visited Mrs. Chen, 82");
    expect(body).toContain("prefers Mandarin");
    expect(body).toContain("Opt-in confirmed");
  });
});
