"use client";

import { Check, Loader2, Pause, Play, RotateCcw, ShieldAlert, SkipForward } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { DemoRunner, type RunnerState } from "@/lib/relay/demoRunner";
import { DEMO_DISASTER, DEMO_RUN, DEMO_SURVIVOR, SCRIPTS, initialScene, type DemoScript, type Scene } from "@/lib/relay/demoScript";
import { categoryLabel, conditionLabel, householdOf, orgName } from "@/lib/relay/selectors";
import { categoryBreakdown, funnel, statusCountsOf } from "@/lib/relay/viz";
import { CategoryBars, FunnelChart, JourneyLane, Legend, statusSegments } from "./charts";
import { FlowGraph } from "./FlowGraph";
import { Panel, PageHeader, Segmented, StatusBadge, shortOrg } from "./ui";

type ScriptId = DemoScript["id"];
const IDLE: RunnerState = { status: "idle", index: -1, error: null };

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Poll until a condition holds (state lives in React, so a click handler has to wait for renders). */
async function until(cond: () => boolean, fail: () => string | null, ms = 8000) {
  const end = Date.now() + ms;
  while (!cond()) {
    const problem = fail();
    if (problem) throw new Error(problem);
    if (Date.now() > end) throw new Error("The simulated backend did not become ready.");
    await sleep(40);
  }
}

// ---------------------------------------------------------------- stage rail

function Rail({ script, state }: { script: DemoScript; state: RunnerState }) {
  const started = state.status !== "idle";
  return (
    <div className="space-y-2">
      <ol aria-label="Demo stages" className="flex gap-1 overflow-x-auto">
        {script.steps.map((step, i) => {
          const done = started && (i < state.index || state.status === "done");
          const current = started && i === state.index && state.status !== "done";
          return (
            <li key={step.id} aria-current={current ? "step" : undefined} className="flex min-w-[4.25rem] flex-1 items-start gap-1.5">
              <span
                className={cn(
                  "grid size-4 shrink-0 place-items-center rounded-full border text-[9px] font-medium tabular-nums transition-colors",
                  done ? "border-agent bg-agent text-panel" : current ? "border-agent text-agent ring-4 ring-agent/15" : "border-line-strong text-muted-foreground",
                )}
              >
                {done ? <Check aria-label="Done" className="size-2.5" /> : i + 1}
              </span>
              <span className={cn("text-[11px] leading-[14px]", current ? "font-medium text-agent" : done ? "text-ink" : "text-muted-foreground")}>{step.stage}</span>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

// ---------------------------------------------------------------- dashboard, in graph form

function GraphDashboard({ scene }: { scene: Scene }) {
  const { board, selectRequest } = useRelay();
  if (!board) return null;
  const f = funnel(board.requests);
  const rows = categoryBreakdown(board.requests);
  const counts = statusCountsOf(board.requests);
  const mine = new Set(scene.requestIds);
  const list = [...board.requests].sort((a, b) => Number(mine.has(b.id)) - Number(mine.has(a.id)) || a.id.localeCompare(b.id));
  return (
    <section aria-label="Dashboard" className="space-y-3">
      <div className="flex items-end justify-between gap-3">
        <div>
          <h2 className="text-base font-semibold tracking-[-0.01em] text-ink">Dashboard</h2>
          <p className="text-xs text-muted-foreground">The same board a coordinator sees, drawn as it fills in.</p>
        </div>
        <Link href="/response" className="text-xs font-medium text-agent underline-offset-4 hover:underline">
          Open the full dashboard
        </Link>
      </div>
      <div className="grid gap-3 lg:grid-cols-[3fr_2fr]">
        <Panel title="Request funnel" aside={<span>Delivery is not receipt</span>}>
          <FunnelChart funnel={f} />
        </Panel>
        <Panel title="Needs by category" aside={<span className="num">{board.requests.length} total</span>}>
          <CategoryBars rows={rows} />
          <Legend className="mt-3" items={statusSegments(counts).map((s) => ({ color: s.color, label: s.label }))} />
        </Panel>
      </div>
      <Panel title="Where every request stands" bodyClassName="p-0" aside={<span>Sorted by deadline, never by person</span>}>
        {list.length ? (
          <ul className="divide-y divide-line">
            {list.map((r) => (
              <li key={r.id}>
                <button
                  type="button"
                  onClick={() => selectRequest(r.id)}
                  className={cn("grid w-full grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)_auto_9rem] items-center gap-3 px-3.5 py-2 text-left text-xs outline-none transition-colors hover:bg-hover focus-visible:bg-hover", mine.has(r.id) && "animate-arrive")}
                >
                  <span className="min-w-0">
                    <span className="block truncate font-medium text-ink">{categoryLabel(r.category)}</span>
                    <span className="block truncate text-2xs text-muted-foreground">
                      {householdOf(board, r.survivor_id)?.display_name ?? "Household"}
                      {r.conditions?.length ? ` · ${r.conditions.map(conditionLabel).join(", ")}` : ""}
                    </span>
                  </span>
                  <span className="truncate text-ink-2">{r.organization_id ? shortOrg(orgName(board, r.organization_id)) : "Unclaimed"}</span>
                  <JourneyLane request={r} />
                  <StatusBadge status={r.status} className="justify-self-end" />
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="p-4 text-xs text-muted-foreground">No requests yet.</p>
        )}
      </Panel>
    </section>
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
      const bad = () => (L().connection === "error" ? (L().connectionError ?? "The simulated backend failed to start.") : null);
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
    <div className="space-y-5">
      <PageHeader
        title="Live demo"
        subtitle={
          <>
            From a call to a verified outcome.{" "}
            <span className="whitespace-nowrap">
              {step && rs.status !== "done" ? <span className="font-medium text-agent">Now: {step.label}</span> : rs.status === "done" ? "Complete" : "Press start to follow one call through Relay."}
            </span>
          </>
        }
        actions={
          <>
            <Segmented
              label="Speed"
              value={String(speed)}
              onChange={(v) => pickSpeed(Number(v))}
              options={[
                { value: "1", label: "1×" },
                { value: "2", label: "2×" },
              ]}
            />
            <Button variant="outline" disabled={!live} onClick={() => runner.current?.skip()}>
              <SkipForward aria-hidden /> Skip step
            </Button>
            <Button variant="outline" disabled={starting || rs.status === "idle"} onClick={() => void start(scriptId)}>
              <RotateCcw aria-hidden /> Restart
            </Button>
            <Button variant="outline" disabled={starting} onClick={() => void start("safety")}>
              <ShieldAlert aria-hidden className="text-promise-lapsed" /> Safety demo
            </Button>
            <Button disabled={starting} onClick={onPrimary} className="px-3.5">
              {starting ? <Loader2 aria-hidden className="animate-spin" /> : <PrimaryIcon aria-hidden />}
              {primaryLabel}
            </Button>
          </>
        }
      />

      <Rail script={script} state={rs} />

      <div className="rounded-md border border-line bg-surface p-3 [background-image:radial-gradient(var(--line)_1px,transparent_1px)] [background-size:18px_18px] md:p-4">
        <FlowGraph script={script} scene={scene} state={rs} board={board} />
      </div>
      <p className="text-2xs text-muted-foreground">
        Dashed <span className="rounded-[4px] border border-dashed border-line-strong px-1">sample</span> tags mark simulated adapters: phone and radio inputs, speech-to-text, the triage model and the voice agents. Requests, claims, calls, verification and lessons are real
        state in the simulated backend, so the other pages agree with this one.
      </p>

      <GraphDashboard scene={scene} />
    </div>
  );
}

