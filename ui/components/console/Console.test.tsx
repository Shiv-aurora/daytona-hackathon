// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { MockAdapter } from "@/lib/adapter";
import { mockSnapshot } from "@/lib/mock";
import { Console } from "./Console";

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: vi.fn() }), usePathname: () => "/console" }));

afterEach(cleanup);

// Opens at the run head instead of the presenter's playback start.
const atHead = () => new MockAdapter({ ...mockSnapshot, start_ts: undefined });
const inboxTitle = () => screen.getByRole("heading", { name: /awaiting approval/i });
const cards = () => screen.getAllByRole("article");

describe("Console on the mock adapter (no backend)", () => {
  it("renders the inbox sorted by deadline and the selected household's timeline", async () => {
    render(<Console adapter={atHead()} />);
    await waitFor(() => expect(inboxTitle()?.textContent).toContain("3 awaiting approval"));
    expect(cards().map((c) => c.getAttribute("aria-label"))).toEqual([
      "Proposal for Mei Chen",
      "Proposal for Gloria Hernandez",
      "Proposal for Soon-ja Kim",
    ]);
    expect(screen.getByRole("heading", { level: 2, name: "Mei Chen" })).toBeTruthy();
    expect(screen.getByText("Mock data")).toBeTruthy();
  });

  it("approves a proposal", async () => {
    render(<Console adapter={atHead()} />);
    await waitFor(() => expect(cards()).toHaveLength(3), { timeout: 5000 });
    fireEvent.click(screen.getByRole("button", { name: "Approve" })); // decision panel follows the selected (first) proposal
    await waitFor(() => expect(inboxTitle()?.textContent).toContain("2 awaiting approval"), { timeout: 5000 });
    const decided = screen.getByRole("list", { name: "Decided proposals" });
    const rows = within(decided).getAllByText("Mei Chen").map((el) => el.closest("li")?.textContent ?? "");
    expect(rows.filter((t) => t.includes("Approved")).length).toBeGreaterThan(1); // the check-ins plus the one decided now
  });

  it("dismisses only after a reason is chosen", async () => {
    render(<Console adapter={atHead()} />);
    await waitFor(() => expect(cards()).toHaveLength(3), { timeout: 5000 });
    fireEvent.click(within(cards()[1]).getByRole("button"));
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    const confirm = await screen.findByRole("button", { name: "Dismiss with this reason" });
    expect(confirm).toHaveProperty("disabled", true);
    fireEvent.click(screen.getByRole("radio", { name: "Wrong household match" }));
    await waitFor(() => expect(confirm).toHaveProperty("disabled", false));
    fireEvent.click(confirm);
    await waitFor(() => expect(inboxTitle()?.textContent).toContain("2 awaiting approval"), { timeout: 5000 });
    const decided = screen.getByRole("list", { name: "Decided proposals" });
    expect(within(decided).getByText("Gloria Hernandez").closest("button")?.getAttribute("title")).toBe("Wrong household match");
  });

  it("shows the goal bar and agent trace for the run", async () => {
    render(<Console adapter={atHead()} />);
    await waitFor(() => expect(cards()).toHaveLength(3), { timeout: 5000 });
    expect(screen.getByRole("region", { name: /Long-term goal/ }).textContent).toMatch(/silent > 72h/);
    const trace = screen.getByRole("list", { name: "Latest agent steps" });
    expect(trace.querySelectorAll("li").length).toBeGreaterThan(0);
    expect(screen.getByRole("group", { name: /Total tokens processed/ }).getAttribute("aria-label")).toMatch(/[1-9][\d,]* tokens/);
  });

  it("supports keyboard approve (A) and next (J)", async () => {
    render(<Console adapter={atHead()} />);
    await waitFor(() => expect(cards()).toHaveLength(3), { timeout: 5000 });
    fireEvent.keyDown(window, { key: "j" });
    fireEvent.keyDown(window, { key: "a" });
    await waitFor(() => expect(inboxTitle()?.textContent).toContain("2 awaiting approval"), { timeout: 5000 });
    expect(within(screen.getByRole("list", { name: "Decided proposals" })).getByText("Gloria Hernandez")).toBeTruthy();
  }, 10000);
});
