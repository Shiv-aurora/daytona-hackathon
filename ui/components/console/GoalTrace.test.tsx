// @vitest-environment jsdom
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { mockSnapshot } from "@/lib/mock";
import { goalOf } from "@/lib/view";
import { GoalBar } from "./GoalBar";
import { TraceStrip } from "./TraceStrip";

afterEach(cleanup);
const day0 = mockSnapshot.run.day0;

describe("goal bar (W1 metrics only)", () => {
  it("renders N/A, never 0%, when promises_on_time_pct is missing at the latest scoring", () => {
    const last = Math.max(...mockSnapshot.metrics.map((m) => m.ts));
    const snap = { ...mockSnapshot, metrics: mockSnapshot.metrics.filter((m) => !(m.ts === last && m.name === "promises_on_time_pct")) };
    render(<GoalBar goal={goalOf(snap)} day0={day0} onSelectHousehold={() => {}} />);
    expect(screen.getByLabelText("Promises on time: N/A").textContent).toBe("N/A");
    expect(document.body.textContent).not.toContain("0%");
  });

  it("shows silent_households and the policy, and invents nothing without metrics", () => {
    render(<GoalBar goal={goalOf(mockSnapshot)} day0={day0} onSelectHousehold={() => {}} />);
    expect(document.body.textContent).toContain("2silent > 72h");
    expect(document.body.textContent).toContain("40%");
    cleanup();
    render(<GoalBar goal={goalOf({ ...mockSnapshot, metrics: [], policy_changes: [] })} day0={day0} onSelectHousehold={() => {}} />);
    expect(document.body.textContent).toMatch(/not scored yet/i);
    expect(document.body.textContent).not.toMatch(/\d+%/);
  });
});

describe("agent trace", () => {
  it("shows the metric values behind a policy change", () => {
    const trace = [
      { run_id: "r", module: "runtime", action: "policy_changed", ts: 10, version: 2, what_changed: "lead_hours 0 -> 12 (on-time below target)",
        metric_values: { promises_on_time_pct: 40, promises_due: 5 } },
    ];
    render(<TraceStrip trace={trace} day0={day0} now={20} />);
    const row = screen.getByRole("list", { name: "Latest agent steps" }).querySelector('[data-kind="policy"]')!;
    expect(row.textContent).toContain("lead_hours 0 -> 12");
    expect(row.textContent).toContain("because promises_on_time_pct=40, promises_due=5");
  });

  it("distinguishes silence, cross-service, call, and model rows", () => {
    const e = (action: string, extra = {}) => ({ run_id: "r", module: "runtime", action, ts: 1, ...extra });
    const trace = [e("silence_escalated"), e("proposal_created", { kind: "cross_service_check_in" }), e("call_result_logged", { module: "calls" }),
      e("llm_call", { purpose: "extract", cached: true, prompt_tokens: 3000, completion_tokens: 100 })];
    render(<TraceStrip trace={trace} day0={day0} now={2} />);
    const kinds = [...document.querySelectorAll("[data-kind]")].map((el) => el.getAttribute("data-kind"));
    expect(kinds).toEqual(["silence", "cross", "call"]); // model calls are summarised by the token counters
    expect(screen.getByRole("group", { name: /^Total tokens processed: 3,100 tokens/ })).toBeTruthy();
  });
});
