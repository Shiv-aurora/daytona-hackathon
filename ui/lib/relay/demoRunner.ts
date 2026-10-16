// Timer-driven controller for a DemoScript: pause / resume / skip / speed / cancel. No React in here.
import type { DemoCtx, DemoScript } from "./demoScript";

export type RunnerStatus = "idle" | "running" | "paused" | "done" | "error";
export interface RunnerState {
  status: RunnerStatus;
  /** Index of the current (or last) step; -1 before the first step. */
  index: number;
  error: string | null;
}

class Cancelled extends Error {}

export class DemoRunner {
  private state: RunnerState = { status: "idle", index: -1, error: null };
  private speed = 1;
  private paused = false;
  private cancelled = false;
  private skipping = false;
  private started = false;
  private waiters: Array<() => void> = [];

  constructor(
    private readonly script: DemoScript,
    private readonly base: Omit<DemoCtx, "wait" | "mem">,
    private readonly onChange: (s: RunnerState) => void,
  ) {}

  get snapshot() {
    return this.state;
  }

  private set(next: Partial<RunnerState>) {
    this.state = { ...this.state, ...next };
    this.onChange(this.state);
  }

  private release() {
    const w = this.waiters;
    this.waiters = [];
    w.forEach((f) => f());
  }

  pause() {
    if (this.state.status !== "running") return;
    this.paused = true;
    this.set({ status: "paused" });
  }
  resume() {
    if (this.state.status !== "paused") return;
    this.paused = false;
    this.set({ status: "running" });
    this.release();
  }
  /** Finish the current step's waiting right away and move on. */
  skip() {
    if (this.state.status !== "running" && this.state.status !== "paused") return;
    this.skipping = true;
    this.release();
  }
  setSpeed(n: number) {
    this.speed = n > 0 ? n : 1;
  }
  cancel() {
    this.cancelled = true;
    this.release();
  }

  private async wait(ms: number) {
    let left = ms;
    while (left > 0) {
      if (this.cancelled) throw new Cancelled();
      if (this.skipping) return;
      if (this.paused) {
        await new Promise<void>((r) => this.waiters.push(r));
        continue;
      }
      const slice = Math.min(left, 50);
      const t0 = Date.now();
      await new Promise((r) => setTimeout(r, slice / this.speed));
      // Real elapsed time counts too, so a throttled background tab does not stretch the story.
      left -= Math.max(slice, (Date.now() - t0) * this.speed);
    }
    if (this.cancelled) throw new Cancelled();
  }

  /** Runs once; a second call returns the same refusal instead of starting a parallel run. */
  async run(): Promise<void> {
    if (this.started) return;
    this.started = true;
    const ctx: DemoCtx = { ...this.base, wait: (ms) => this.wait(ms), mem: { requests: [], orgFor: {} } };
    this.set({ status: "running", index: 0, error: null });
    try {
      for (let i = 0; i < this.script.steps.length; i++) {
        const step = this.script.steps[i];
        this.skipping = false;
        this.set({ index: i });
        await step.run(ctx);
        await ctx.wait(step.delayMs);
        if (this.cancelled) throw new Cancelled();
      }
      this.set({ status: "done", index: this.script.steps.length });
    } catch (e) {
      if (e instanceof Cancelled) {
        this.state = { ...this.state, status: "idle" };
        return;
      }
      this.set({ status: "error", error: e instanceof Error ? e.message : "The demo stopped unexpectedly." });
    }
  }
}
