// @vitest-environment jsdom
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LiveAdapter } from "@/lib/live/client";
import { FakeRelay, relabel } from "@/lib/live/fake-relay";
import { mockSnapshot } from "@/lib/mock";
import { Console } from "./Console";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/console" }));
afterEach(cleanup);

const BASE = "http://relay.test";
function setup() {
  const relay = new FakeRelay({ "run-a": relabel(mockSnapshot, "run-a", "RUN-A"), "run-b": relabel(mockSnapshot, "run-b", "RUN-B") });
  const utils = render(<Console adapter={new LiveAdapter(BASE, relay.fetch)} initialRun="run-a" />);
  return { relay, ...utils };
}
const pageText = () => document.body.textContent ?? "";
const inbox = () => screen.getByRole("heading", { name: /awaiting approval/i });
const picker = () => screen.getByRole("combobox");

describe("live console: run isolation", () => {
  it("clears run A before run B renders, and never mixes their proposals or timeline events", async () => {
    const { relay } = setup();
    await waitFor(() => expect(pageText()).toContain("RUN-A: Visited Mrs. Chen, 82"));
    relay.holdRuns.add("run-b");
    fireEvent.change(picker(), { target: { value: "run-b" } });
    await waitFor(() => expect(screen.getByText(/Loading run run-b/)).toBeTruthy());
    expect(pageText()).not.toContain("RUN-A"); // A's proposals and timeline are gone before B arrives
    await act(async () => relay.release("run-b"));
    await waitFor(() => expect(pageText()).toContain("RUN-B: Visited Mrs. Chen, 82"));
    expect(pageText()).not.toContain("RUN-A");
  });

  it("drops a late response for run A after the user moved to run B", async () => {
    const relay = new FakeRelay({ "run-a": relabel(mockSnapshot, "run-a", "RUN-A"), "run-b": relabel(mockSnapshot, "run-b", "RUN-B") });
    relay.holdRuns.add("run-a");
    render(<Console adapter={new LiveAdapter(BASE, relay.fetch)} initialRun="run-a" />);
    await waitFor(() => expect(relay.held.length).toBe(1));
    await waitFor(() => expect(screen.getAllByRole("option").length).toBe(2));
    fireEvent.change(picker(), { target: { value: "run-b" } });
    await waitFor(() => expect(pageText()).toContain("RUN-B: Visited Mrs. Chen, 82"));
    await act(async () => relay.release("run-a")); // A's answer arrives late
    expect(pageText()).toContain("RUN-B");
    expect(pageText()).not.toContain("RUN-A");
  });
});

describe("live console: decisions", () => {
  it("sends run and proposal ids, disables controls while pending, then reconciles", async () => {
    const { relay } = setup();
    await waitFor(() => expect(inbox().textContent).toContain("3 awaiting approval"));
    relay.holdDecisions = true;
    const card = screen.getAllByRole("article")[0];
    const id = card.id.replace("proposal-", "");
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByText(/sending decision/i)).toBeTruthy());
    for (const b of screen.getAllByRole("button", { name: "Approve" })) expect(b).toHaveProperty("disabled", true);
    const post = relay.requests.find((r) => r.method === "POST")!;
    expect(post).toMatchObject({ url: `${BASE}/runs/run-a/proposals/${id}/decision`, body: { status: "approved" } });
    await act(async () => relay.release("decision:run-a"));
    await waitFor(() => expect(inbox().textContent).toContain("2 awaiting approval"));
    const reads = relay.requests.filter((r) => r.method === "GET" && r.url.endsWith("/runs/run-a/console"));
    expect(reads.length).toBeGreaterThanOrEqual(2); // reloaded from the backend after the action
  });

  it("shows a backend rejection and keeps the proposal pending", async () => {
    const { relay } = setup();
    await waitFor(() => expect(inbox().textContent).toContain("3 awaiting approval"));
    relay.rejectDecisions = "proposal is already approved";
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("proposal is already approved"));
    expect(inbox().textContent).toContain("3 awaiting approval");
  });
});
