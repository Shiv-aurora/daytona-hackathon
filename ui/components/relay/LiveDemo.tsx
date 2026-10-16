"use client";

import { ArrowUpRight, Check, Loader2, Pause, Play, RotateCcw, ShieldAlert, SkipForward } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { DemoRunner, type RunnerState } from "@/lib/relay/demoRunner";
import { DEMO_DISASTER, DEMO_RUN, DEMO_SURVIVOR, SCRIPTS, initialScene, type DemoScript, type Scene } from "@/lib/relay/demoScript";
import { FlowGraph, STEP_HUE } from "./FlowGraph";
import { Segmented } from "./ui";

type ScriptId = DemoScript["id"];
const IDLE: RunnerState = { status: "idle", index: -1, error: null };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Poll until a condition holds (state lives in React, so a click handler has to wait for renders). */
async function until(cond: () => boolean, fail: () => string | null, ms = 8000) {
  const end = Date.now() + ms;
  while (!cond()) {
    const problem = fail();
    if (problem) throw new Error(problem);
    if (Date.now() > end) throw new Error("The backend did not become ready.");
    await sleep(40);
  }
}

// ---------------------------------------------------------------- progress rail

function Rail({ script, state }: { script: DemoScript; state: RunnerState }) {
  const started = state.status !== "idle";
  return (
    <ol aria-label="Demo stages" className="flex gap-1.5 overflow-x-auto">
      {script.steps.map((step, i) => {
        const done = started && (i < state.index || state.status === "done");
        const current = started && i === state.index && state.status !== "done";
        const c = STEP_HUE[step.id] ?? "var(--agent)";
        return (
          <li key={step.id} aria-current={current ? "step" : undefined} className="min-w-[4.5rem] flex-1" style={{ "--c": c } as CSSProperties}>
            <span aria-hidden className="block h-1 overflow-hidden rounded-full bg-line">
              <span
                className={cn("block h-full rounded-full bg-[var(--c)] transition-[width,opacity] duration-500", done ? "w-full opacity-60" : current ? "w-full" : "w-0")}
              />
            </span>
            <span className={cn("mt-1.5 flex items-center gap-1 text-[11px] leading-[14px]", current ? "font-semibold text-[var(--c)]" : done ? "text-ink-2" : "text-muted-foreground")}>
              {done ? <Check aria-label="Done" className="size-3 shrink-0 text-[var(--c)]" strokeWidth={2.5} /> : null}
              <span className="truncate">{step.stage}</span>
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------- page

export function LiveDemo() {
  const relay = useRelay();
  const { board } = relay;
  const latest = useRef(relay);
  useEffect(() => {
    latest.current = relay;
  });

  const [scriptId, setScriptId] = useState<ScriptId>("main");
  const [scene, setScene] = useState<Scene>(initialScene);
  const [rs, setRs] = useState<RunnerState>(IDLE);
  const [speed, setSpeed] = useState(1);
  const [starting, setStarting] = useState(false);

  const runner = useRef<DemoRunner | null>(null);
  const running = useRef<Promise<void>>(Promise.resolve());
  const seq = useRef(0);
  const busy = useRef(false);
  const speedRef = useRef(1);

  useEffect(() => {
    const token = seq;
    return () => {
      // Leaving the page cancels the run and any start still waiting on the backend.
      token.current += 1;
      runner.current?.cancel();
    };
  }, []);

  const start = useCallback(async (id: ScriptId) => {
    if (busy.current) return; // no double-runs
    busy.current = true;
    const mine = ++seq.current;
    const L = () => latest.current;
    try {
      setStarting(true);
      if (runner.current) {
        runner.current.cancel();
        await running.current;
      }
      setScriptId(id);
      setScene(initialScene());
      setRs(IDLE);
      if (L().mode !== "mock") L().setMode("mock");
      const bad = () => (L().connection === "error" ? (L().connectionError ?? "The backend failed to start.") : null);
      await until(() => L().mode === "mock" && L().connection === "ready" && L().board !== null, bad);
      await L().resetDemo();
      if (L().runId !== DEMO_RUN) L().selectRun(DEMO_RUN);
      await until(() => L().runId === DEMO_RUN && L().board?.run_id === DEMO_RUN, bad);
      if (mine !== seq.current) return;
      const next = new DemoRunner(
        SCRIPTS[id],
        {
          api: L().api,
          runId: DEMO_RUN,
          disasterId: DEMO_DISASTER,
          survivorId: DEMO_SURVIVOR,
          patch: (p) => setScene((s) => ({ ...s, ...(typeof p === "function" ? p(s) : p) })),
          refresh: () => L().refresh(),
          onEscalation: (message) => L().setEscalation({ message }),
        },
        (state) => {
          if (mine !== seq.current) return;
          setRs(state);
          if (state.status === "error") L().notify("error", state.error ?? "The demo stopped unexpectedly.");
        },
      );
      next.setSpeed(speedRef.current);
      runner.current = next;
      running.current = next.run();
    } catch (e) {
      L().notify("error", e instanceof Error ? e.message : "Could not start the demo.");
    } finally {
      busy.current = false;
      setStarting(false);
    }
  }, []);

  const script = SCRIPTS[scriptId];
  const live = rs.status === "running" || rs.status === "paused";
  const primary = rs.status === "running" ? "pause" : rs.status === "paused" ? "resume" : "start";

  function onPrimary() {
    if (primary === "pause") runner.current?.pause();
    else if (primary === "resume") runner.current?.resume();
    else void start(rs.status === "done" ? scriptId : "main");
  }
  function pickSpeed(n: number) {
    speedRef.current = n;
    setSpeed(n);
    runner.current?.setSpeed(n);
  }

  const PrimaryIcon = primary === "pause" ? Pause : Play;
  const primaryLabel = starting ? "Getting ready" : primary === "pause" ? "Pause" : primary === "resume" ? "Resume" : rs.status === "done" ? "Run again" : "Start demo";
  const step = rs.index >= 0 ? script.steps[Math.min(rs.index, script.steps.length - 1)] : null;

  return (
    <div className="flex flex-col gap-3 lg:min-h-0 lg:flex-1">
      <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2">
        <div className="flex min-w-0 items-baseline gap-3">
          <h1 className="text-xl font-semibold tracking-[-0.04em] text-ink">Live demo</h1>
          <p className="truncate text-sm text-muted-foreground" aria-live="polite">
            {step && rs.status !== "done" ? (
              <>
                <span className="num font-medium text-ink-2">
                  {rs.index + 1}/{script.steps.length}
                </span>{" "}
                <span className="font-semibold" style={{ color: STEP_HUE[step.id] }}>
                  {step.label}
                </span>
              </>
            ) : rs.status === "done" ? (
              <span className="font-medium text-promise-kept">Complete</span>
            ) : (
              "One call, from 911 line to verified help."
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          <Button variant="ghost" size="sm" disabled={starting} onClick={() => void start("safety")} className="text-ink-2">
            <ShieldAlert aria-hidden className="text-st-safety" /> Emergency path
          </Button>
          <span aria-hidden className="mx-1 h-5 w-px bg-line" />
          <Segmented
            label="Speed"
            value={String(speed)}
            onChange={(v) => pickSpeed(Number(v))}
            options={[
              { value: "1", label: "1×" },
              { value: "2", label: "2×" },
            ]}
          />
          <Button variant="outline" size="icon" title="Skip step" aria-label="Skip step" disabled={!live} onClick={() => runner.current?.skip()}>
            <SkipForward aria-hidden />
          </Button>
          <Button variant="outline" size="icon" title="Restart" aria-label="Restart" disabled={starting || rs.status === "idle"} onClick={() => void start(scriptId)}>
            <RotateCcw aria-hidden />
          </Button>
          <Button disabled={starting} onClick={onPrimary} className="min-w-[7.5rem] px-3.5">
            {starting ? <Loader2 aria-hidden className="animate-spin" /> : <PrimaryIcon aria-hidden />}
            {primaryLabel}
          </Button>
        </div>
      </div>

      <div className="relative rounded-[16px] border border-line bg-canvas p-3 [background-image:radial-gradient(var(--ds-gray-500)_1px,transparent_1px)] [background-size:20px_20px] md:p-3 lg:min-h-0 lg:flex-1">
        <FlowGraph fit script={script} scene={scene} state={rs} board={board} />
      </div>

      <div className="flex items-end gap-4">
        <div className="min-w-0 flex-1">
          <Rail script={script} state={rs} />
        </div>
        <Link href="/response" className="inline-flex shrink-0 items-center gap-1 pb-0.5 text-xs font-medium text-ink-2 underline-offset-4 hover:text-ink hover:underline">
          Dashboard <ArrowUpRight aria-hidden className="size-3.5" />
        </Link>
      </div>
    </div>
  );
}
