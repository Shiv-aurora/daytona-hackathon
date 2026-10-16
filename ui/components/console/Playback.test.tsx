// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MockAdapter } from "@/lib/adapter";
import { mockSnapshot } from "@/lib/mock";
import { Console } from "./Console";
import { ProveIt } from "./ProveIt";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/console" }));

afterEach(cleanup);

const clock = () => document.querySelector("header time")?.getAttribute("aria-label") ?? "";
const inbox = () => screen.getByRole("heading", { name: /awaiting approval/i }).textContent;

describe("presenter playback", () => {
  it("starts at the run's playback start and advances every panel together", async () => {
    render(<Console adapter={new MockAdapter()} />);
    await waitFor(() => expect(clock()).toContain("Day 6"), { timeout: 5000 });
    expect(inbox()).toContain("0 awaiting approval");
    fireEvent.click(screen.getByRole("button", { name: /Next needle/ }));
    await waitFor(() => expect(inbox()).toContain("1 awaiting approval"));
    expect(screen.getByRole("article", { name: "Proposal for Gloria Hernandez" })).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /Next needle/ }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Decision for Mei Chen" })).toBeTruthy());
    const panel = screen.getByRole("region", { name: "Decision for Mei Chen" });
    expect(panel.textContent).toContain("82 · lives alone · basement unit · no power");
    expect(panel.textContent).toContain("Son Wei was due Sep 7");
    expect(panel.textContent).toContain("Acting 12h before deadlines (was 0h)");
    expect(within(panel).getAllByRole("button", { name: /record, Sep \d+\. Show source/ })).toHaveLength(5);
    expect(screen.getByRole("region", { name: /Long-term goal/ }).textContent).toContain("Policy v2");
  });

  it("stamps a decision with the playback time and confirms it", async () => {
    const adapter = new MockAdapter();
    render(<Console adapter={adapter} />);
    await waitFor(() => expect(clock()).toContain("Day 6"), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: /Next needle/ }));
    fireEvent.click(screen.getByRole("button", { name: /Next needle/ }));
    await waitFor(() => expect(screen.getByRole("region", { name: "Decision for Mei Chen" })).toBeTruthy());
    fireEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("Approved welfare check for Mei Chen"));
    const snap = await adapter.load(mockSnapshot.run.run_id);
    expect(snap.decisions["prop-s1_h_001"]).toEqual({ status: "approved", ts: 303.12, reason: null });
  });

  it("clamps to the run head and stops there", async () => {
    render(<Console adapter={new MockAdapter()} />);
    await waitFor(() => expect(clock()).toContain("Day 6"), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "+1 week" }));
    fireEvent.click(screen.getByRole("button", { name: "+1 week" }));
    await waitFor(() => expect(clock()).toContain("Day 13"));
    expect(inbox()).toContain("3 awaiting approval");
    expect(screen.getByRole("button", { name: "+1 day" })).toHaveProperty("disabled", true);
    expect(screen.getByRole("button", { name: "Play" })).toHaveProperty("disabled", true);
  });

  it("proves it only with measured data", async () => {
    render(<Console adapter={new MockAdapter()} />);
    await waitFor(() => expect(clock()).toContain("Day 6"), { timeout: 5000 });
    fireEvent.click(screen.getByRole("tab", { name: "Prove it" }));
    expect(screen.getByRole("heading", { name: "Not yet measured" })).toBeTruthy();
    cleanup();
    const bucket = (label: string, recall: number | null) => ({ label, min_days: 0, max_days: null, open: 4, recalled: 2, recall });
    const recall = (values: (number | null)[]) => ({
      probe_times: [100],
      open: 8,
      recalled: 4,
      recall: 0.5,
      named_not_open: 0,
      by_age: ["0-3d", "3-7d", "7d+"].map((l, i) => bucket(l, values[i]!)),
    });
    render(<ProveIt comparison={{ relay: { promise_recall: recall([1, 0.9, 0.85]) }, baseline: { promise_recall: recall([0.9, 0.4, null]) } }} />);
    const rows = within(screen.getByRole("table")).getAllByRole("row").map((r) => r.textContent);
    expect(rows).toEqual(["Promise ageRelayBaseline (long context)", "0-3d100%90%", "3-7d90%40%", "7d+85%no open promises"]);
  });
});
