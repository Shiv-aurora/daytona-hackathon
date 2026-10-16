import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { DemoRunner, type RunnerState } from "./demoRunner";
import { MAIN_SCRIPT, SAFETY_SCRIPT, callerText, initialScene, runScriptHeadless, type DemoCtx } from "./demoScript";
import { categoriesOf, conditionsOf, MockApi } from "./mock";
import type { Board } from "./types";

const RUN = "demo-current";

// Same trick as mock.test.ts: the mock simulates latency with setTimeout; run it instantly.
beforeEach(() => {
  vi.stubGlobal("setTimeout", ((fn: () => void) => {
    queueMicrotask(fn);
    return 0;
  }) as unknown as typeof setTimeout);
});
afterEach(() => vi.unstubAllGlobals());

describe("main demo script", () => {
  it("uses a report the mock classifies as food + supplies with access blocked", () => {
    const text = callerText(MAIN_SCRIPT.call);
    expect(text).toBe("We need food and blankets for the family. The road is blocked so we can't get out.");
    expect(categoriesOf(text)).toEqual(["food", "supplies"]);
    expect(conditionsOf(text)).toEqual(["access_blocked"]);
  });

  it("ends with a human-reviewed resolution, escalation, approved lesson and a 3-case comparison", async () => {
    const api = new MockApi();
    const before = await api.board(RUN);
    const scene = await runScriptHeadless(MAIN_SCRIPT, { api });
    const board = await api.board(RUN);

    const created = board.requests.filter((r) => scene.requestIds.includes(r.id));
    expect(created.map((r) => r.category).sort()).toEqual(["food", "supplies"]);
    expect(created.every((r) => r.status === "resolved")).toBe(true);
    expect(board.requests.length).toBe(before.requests.length + 2);

    const food = created.find((r) => r.category === "food")!;
    const verifications = board.verifications.filter((v) => v.request_id === food.id);
    expect(verifications.map((v) => [v.source, v.received])).toEqual([
      ["survivor_call", false],
      ["human_review", true],
    ]);
    expect(board.calls.find((c) => c.request_id === food.id)?.outcome).toBe("not_received");
    expect(board.system_events.some((e) => e.action === "human_escalation" && e.subject_id === food.id)).toBe(true);

    const lesson = board.lessons.find((l) => l.source_run_id === RUN);
    expect(lesson?.approved).toBe(true);
    expect(scene.lesson?.id).toBe(lesson?.id);

    expect(scene.compare?.case_count).toBe(3);
    expect(board.evaluations).toHaveLength(2);
    expect(scene.helpers).toHaveLength(5);
    expect(scene.triage?.conditions).toEqual(["access_blocked"]);

    for (const s of board.survivors) expect(Object.keys(s)).not.toContain("phone");
    expect(JSON.stringify(board)).not.toMatch(/phone/i);
  });
});

describe("safety demo script", () => {
  it("escalates before any triage and creates no request", async () => {
    const api = new MockApi();
    const before: Board = await api.board(RUN);
    const seen: string[] = [];
    const scene = await runScriptHeadless(SAFETY_SCRIPT, { api });
    const after = await api.board(RUN);
    after.system_events.slice(before.system_events.length).forEach((e) => seen.push(`${e.module}/${e.action}`));

    expect(after.requests).toHaveLength(before.requests.length);
    expect(seen[0]).toBe("intake/human_escalation");
    expect(seen).not.toContain("intake/report_received");
    expect(scene.emergency).toBe("tripped");
    expect(scene.triage).toBeNull();
    expect(scene.triageSkipped).toBe(true);
    expect(scene.emergencyMessage).toMatch(/911/);
  });
});

describe("DemoRunner", () => {
  async function build(onChange: (s: RunnerState) => void) {
    const api = new MockApi();
    const patches: unknown[] = [];
    const runner = new DemoRunner(
      MAIN_SCRIPT,
      {
        api,
        runId: RUN,
        disasterId: "demo-storm-2026",
        survivorId: "current-survivor-1",
        patch: (p) => void patches.push(p),
        refresh: async () => undefined,
      } satisfies Omit<DemoCtx, "wait" | "mem">,
      onChange,
    );
    return { api, runner, patches };
  }

  it("runs every stage once and refuses a second run", async () => {
    const states: RunnerState[] = [];
    const { api, runner } = await build((s) => states.push(s));
    runner.setSpeed(1000);
    await Promise.all([runner.run(), runner.run()]);
    expect(runner.snapshot.status).toBe("done");
    expect(new Set(states.map((s) => s.index)).size).toBe(MAIN_SCRIPT.steps.length + 1);
    expect((await api.board(RUN)).lessons.some((l) => l.source_run_id === RUN && l.approved)).toBe(true);
  });

  it("cancels cleanly and reports errors instead of swallowing them", async () => {
    const a = await build(() => undefined);
    const run = a.runner.run();
    a.runner.cancel();
    await run;
    expect(a.runner.snapshot.status).toBe("idle");

    const states: RunnerState[] = [];
    const b = await build((s) => states.push(s));
    b.api.board = async () => {
      throw new Error("backend down");
    };
    b.runner.setSpeed(1000);
    await b.runner.run();
    expect(b.runner.snapshot).toMatchObject({ status: "error", error: "backend down" });
  });

  it("pauses and resumes", async () => {
    const { runner } = await build(() => undefined);
    runner.setSpeed(1000);
    const run = runner.run();
    runner.pause();
    expect(runner.snapshot.status).toBe("paused");
    runner.resume();
    runner.skip();
    runner.cancel();
    await run;
    expect(initialScene().helpers).toHaveLength(5);
  });
});
