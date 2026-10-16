"use client";

import {
  BookOpen,
  Bot,
  Box,
  Check,
  Clock,
  Gauge,
  Loader2,
  Pause,
  Phone,
  Play,
  RotateCcw,
  ShieldAlert,
  ShieldCheck,
  SkipForward,
  Sparkles,
  TriangleAlert,
  UserCheck,
  Users,
  type LucideIcon,
} from "lucide-react";
import { useCallback, useEffect, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { DemoRunner, type RunnerState } from "@/lib/relay/demoRunner";
import {
  DEMO_DISASTER,
  DEMO_RUN,
  DEMO_SURVIVOR,
  SCRIPTS,
  initialScene,
  type DemoScript,
  type OrgPhase,
  type Scene,
  type TranscriptLine,
} from "@/lib/relay/demoScript";
import { STATUSES, STATUS_META, categoryLabel, conditionLabel, orgName } from "@/lib/relay/selectors";
import type { Board, CompareResult } from "@/lib/relay/types";
import { CategoryIcon } from "./ResponseView";
import { Card, Pill, StatusBadge } from "./ui";

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

function Sample({ children = "sample" }: { children?: string }) {
  return <span className="rounded-md border border-dashed border-line px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">{children}</span>;
}

function CardHead({ icon: Icon, title, badge }: { icon: LucideIcon; title: string; badge?: string }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
        <Icon aria-hidden className="size-4 text-agent" />
        {title}
      </h2>
      {badge ? <Sample>{badge}</Sample> : null}
    </div>
  );
}

// ---------------------------------------------------------------- stage rail

function Rail({ script, state }: { script: DemoScript; state: RunnerState }) {
  const started = state.status !== "idle";
  return (
    <ol aria-label="Demo stages" className="flex gap-1 overflow-x-auto pb-1">
      {script.steps.map((step, i) => {
        const done = started && (i < state.index || state.status === "done");
        const current = started && i === state.index && state.status !== "done";
        return (
          <li key={step.id} aria-current={current ? "step" : undefined} className="flex min-w-[4.5rem] flex-1 flex-col items-center gap-1 text-center">
            <span className="flex w-full items-center">
              <span className={cn("h-px flex-1", i === 0 ? "bg-transparent" : done || current ? "bg-agent" : "bg-line")} />
              <span
                className={cn(
                  "grid size-5 shrink-0 place-items-center rounded-full border text-[10px] font-medium tabular-nums transition-colors",
                  done ? "border-agent bg-agent text-white" : current ? "border-agent text-agent ring-4 ring-agent/15" : "border-line text-muted-foreground",
                )}
              >
                {done ? <Check aria-label="Done" className="size-3" /> : i + 1}
              </span>
              <span className={cn("h-px flex-1", i === script.steps.length - 1 ? "bg-transparent" : done ? "bg-agent" : "bg-line")} />
            </span>
            <span className={cn("text-[11px] leading-tight", current ? "font-semibold text-agent" : done ? "text-ink" : "text-muted-foreground")}>{step.stage}</span>
          </li>
        );
      })}
    </ol>
  );
}

// ---------------------------------------------------------------- incoming call

function Bubble({ line }: { line: TranscriptLine }) {
  if (line.speaker === "system") {
    return <li className="animate-arrive text-center text-[11px] text-muted-foreground">{line.text}</li>;
  }
  const caller = line.speaker === "caller";
  return (
    <li className={cn("flex animate-arrive", caller ? "justify-start" : "justify-end")}>
      <span className={cn("max-w-[88%] rounded-lg px-2.5 py-1.5 text-xs", caller ? "bg-muted text-ink" : "border border-agent/30 bg-agent/10 text-ink")}>
        {line.text}
      </span>
    </li>
  );
}

function Waveform({ live }: { live: boolean }) {
  return (
    <span aria-hidden className="flex h-8 items-center gap-[3px]">
      {[0, 2, 1, 3, 1, 2, 0, 3, 1].map((d, i) => (
        <span
          key={i}
          className={cn("h-full w-[3px] origin-center rounded-full", live ? "animate-wave bg-agent" : "scale-y-[0.2] bg-line")}
          style={live ? { animationDelay: `${d * 120 + i * 40}ms` } : undefined}
        />
      ))}
    </span>
  );
}

function CallCard({ script, scene }: { script: DemoScript; scene: Scene }) {
  const lines = script.call.slice(0, scene.callLines);
  const tripped = scene.emergency === "tripped";
  return (
    <Card className="flex min-h-80 flex-col gap-3 p-3">
      <CardHead icon={Phone} title="Incoming call" badge="911 line · sample" />
      <div className="flex items-center gap-3">
        <span
          aria-hidden
          className={cn(
            "grid size-10 shrink-0 place-items-center rounded-full",
            scene.callActive ? "animate-call-ring bg-agent text-white" : "bg-muted text-muted-foreground",
          )}
        >
          <Phone className="size-4" />
        </span>
        <Waveform live={scene.callActive} />
        <span className="ml-auto flex items-center gap-1 text-[11px] font-medium text-ink">
          ElevenLabs STT <Sample>sample</Sample>
        </span>
      </div>
      <ul aria-label="Call transcript" aria-live="polite" className="flex-1 space-y-1.5">
        {lines.length ? lines.map((l, i) => <Bubble key={i} line={l} />) : <li className="pt-6 text-center text-xs text-muted-foreground">Waiting for a call</li>}
      </ul>
      <div className="min-h-6">
        {scene.emergency === "checking" ? (
          <Pill tone="amber" icon={Loader2} className="[&_svg]:animate-spin">
            Emergency check…
          </Pill>
        ) : scene.emergency === "clear" ? (
          <Pill tone="green" icon={ShieldCheck} className="animate-arrive">
            Emergency check: clear
          </Pill>
        ) : tripped ? (
          <div role="alert" className="animate-arrive space-y-1 rounded-lg border border-promise-lapsed/40 bg-promise-lapsed/10 p-2">
            <Pill tone="red" icon={ShieldAlert}>
              Emergency check: tripped
            </Pill>
            <p className="text-xs font-medium text-ink">{scene.emergencyMessage}</p>
          </div>
        ) : null}
      </div>
    </Card>
  );
}

// ---------------------------------------------------------------- triage

function Fact({ icon: Icon, children }: { icon: LucideIcon; children: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink">
      <Icon aria-hidden className="size-3.5 text-muted-foreground" />
      {children}
    </span>
  );
}

function TriageCard({ scene }: { scene: Scene }) {
  const t = scene.triage;
  return (
    <Card className="flex min-h-80 flex-col gap-3 p-3">
      <CardHead icon={Sparkles} title="AI triage" badge="Groq · sample" />
      <div className="flex-1 space-y-3">
        {scene.triageSkipped ? (
          <p className="pt-6 text-center text-xs font-medium text-muted-foreground">Skipped: emergencies go to a person first.</p>
        ) : scene.triageLoading ? (
          <div aria-label="Triage running" role="status" className="space-y-2 pt-1">
            {[70, 45, 60].map((w) => (
              <div key={w} className="h-6 animate-shimmer rounded-md bg-muted" style={{ width: `${w}%` }} />
            ))}
          </div>
        ) : t ? (
          <>
            <div className="flex flex-wrap gap-1.5">
              {t.needs.map((n, i) => (
                <span
                  key={n}
                  style={{ animationDelay: `${i * 150}ms` }}
                  className="inline-flex animate-arrive items-center gap-1.5 rounded-md border border-agent/30 bg-agent/10 px-2.5 py-1.5 text-sm font-medium text-agent [animation-fill-mode:backwards]"
                >
                  <CategoryIcon category={n} className="size-4" />
                  {categoryLabel(n)}
                </span>
              ))}
            </div>
            {t.conditions.length ? (
              <div className="flex flex-wrap gap-1.5">
                {t.conditions.map((c) => (
                  <Pill key={c} tone="amber" icon={TriangleAlert}>
                    {conditionLabel(c)}
                  </Pill>
                ))}
              </div>
            ) : null}
            <div className="flex flex-col gap-1.5">
              <Fact icon={Clock}>{t.deadline}</Fact>
              <Fact icon={Gauge}>{t.workload}</Fact>
            </div>
          </>
        ) : (
          <p className="pt-6 text-center text-xs text-muted-foreground">Waiting for the transcript</p>
        )}
      </div>
      <p className="flex items-center gap-1.5 border-t border-line pt-2 text-xs font-medium text-ink">
        <UserCheck aria-hidden className="size-3.5 text-agent" /> A person decides
      </p>
    </Card>
  );
}

// ---------------------------------------------------------------- dashboard

const PHASE_TEXT: Record<OrgPhase, string> = { idle: "", tagging: "Tagged", claimed: "Signed up", delivered: "Delivered" };

function MiniBoard({ board, scene }: { board: Board | null; scene: Scene }) {
  const requests = board?.requests ?? [];
  const mine = scene.requestIds.flatMap((id) => requests.find((r) => r.id === id) ?? []);
  return (
    <Card className="flex min-h-80 flex-col gap-3 p-3">
      <CardHead icon={Users} title="Dashboard" />
      <div className="grid grid-cols-5 gap-1" aria-label="Request counts">
        {STATUSES.map((s) => {
          const n = requests.filter((r) => r.status === s).length;
          return (
            <div key={s} title={STATUS_META[s].label} className="rounded-md bg-muted/60 px-1 py-1.5 text-center">
              <span key={n} className="block animate-arrive text-xl font-semibold leading-none tabular-nums text-ink">
                {n}
              </span>
              <span className="mt-1 flex items-center justify-center gap-1 text-[10px] text-muted-foreground">
                <span aria-hidden className={cn("size-1.5 rounded-full", STATUS_META[s].dot)} />
                <span className="truncate">{STATUS_META[s].label.split(" ")[0]}</span>
              </span>
            </div>
          );
        })}
      </div>
      {scene.alert ? (
        <div role="alert" className="flex animate-arrive items-center gap-2 rounded-lg border border-promise-lapsed/40 bg-promise-lapsed/10 px-2.5 py-1.5 text-xs font-medium text-ink">
          <ShieldAlert aria-hidden className="size-4 shrink-0 text-promise-lapsed" /> {scene.alert}
        </div>
      ) : null}
      {scene.humanReview ? (
        <div role="status" className="flex animate-arrive items-center gap-2 rounded-lg border border-agent/30 bg-agent/10 px-2.5 py-1.5 text-xs font-medium text-ink">
          <UserCheck aria-hidden className="size-4 shrink-0 text-agent" /> A person reviews
        </div>
      ) : null}
      <ul className="space-y-1.5">
        {mine.map((r) => (
          <li key={r.id} className="flex animate-arrive items-center gap-2 rounded-lg border border-line px-2 py-1.5">
            <span aria-hidden className="grid size-7 shrink-0 place-items-center rounded-md bg-agent/10 text-agent">
              <CategoryIcon category={r.category} className="size-4" />
            </span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-xs font-medium text-ink">{categoryLabel(r.category)}</span>
              <span className="block truncate text-[11px] text-muted-foreground">{board ? orgName(board, r.organization_id) : ""}</span>
            </span>
            <StatusBadge status={r.status} />
          </li>
        ))}
        {!mine.length ? <li className="py-2 text-center text-xs text-muted-foreground">Requests appear here</li> : null}
      </ul>
      <ul className="mt-auto space-y-1.5 border-t border-line pt-2" aria-label="Volunteer organizations">
        {(board?.organizations ?? []).map((o) => {
          const st = scene.orgs[o.id];
          const active = st && st.phase !== "idle";
          return (
            <li key={o.id} className={cn("flex items-center gap-2 rounded-md px-1.5 py-1 text-xs transition-colors", active && "bg-agent/5")}>
              <span className={cn("grid size-5 shrink-0 place-items-center rounded-full text-[10px] font-semibold", active ? "bg-agent text-white" : "bg-muted text-muted-foreground")}>
                {o.name.replace("Demo ", "").charAt(0)}
              </span>
              <span className="min-w-0 flex-1 truncate text-ink">{o.name}</span>
              <span className="flex shrink-0 items-center gap-1 text-muted-foreground">
                {o.capabilities.map((c) => (
                  <CategoryIcon key={c} category={c} className={cn("size-3.5", st?.phase === "tagging" && st.category === c && "text-agent")} />
                ))}
              </span>
              {active ? (
                <span key={st.phase} className="flex animate-arrive items-center gap-1 font-medium text-agent">
                  {st.phase !== "tagging" ? <Check aria-hidden className="size-3" /> : null}
                  {PHASE_TEXT[st.phase]}
                </span>
              ) : null}
            </li>
          );
        })}
      </ul>
    </Card>
  );
}

// ---------------------------------------------------------------- helpers + follow-up call

function HelpersStrip({ scene }: { scene: Scene }) {
  return (
    <Card className="space-y-2 p-3">
      <CardHead icon={Bot} title="AI helpers" badge="ElevenLabs agents · Daytona sandbox · sample roles" />
      <ul className="grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-5">
        {scene.helpers.map((h) => (
          <li key={h.id} className={cn("space-y-1 rounded-lg border p-2 transition-colors", h.status === "working" ? "border-agent/50 bg-agent/5" : "border-line")}>
            <span className="flex items-center gap-1.5 text-xs font-semibold text-ink">
              <span aria-hidden className={cn("size-2 rounded-full", h.status === "working" ? "animate-pulse bg-agent" : "bg-muted-foreground/40")} />
              {h.role}
              <span className="sr-only">{h.status}</span>
            </span>
            <span className="block min-h-8 text-[11px] leading-tight text-muted-foreground">{h.lastAction}</span>
            <span className="flex items-center gap-1 font-mono text-[10px] text-muted-foreground">
              <Box aria-hidden className="size-3" /> {h.sandbox}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function FollowUpPanel({ script, scene }: { script: DemoScript; scene: Scene }) {
  const lines = script.followUp.slice(0, scene.followLines);
  return (
    <Card className="flex flex-col gap-2 p-3">
      <CardHead icon={Phone} title="Helper call" badge="sample call" />
      <ul aria-label="Follow-up call transcript" aria-live="polite" className="flex-1 space-y-1.5">
        {lines.length ? (
          lines.map((l, i) => <Bubble key={i} line={l} />)
        ) : (
          <li className="py-4 text-center text-xs text-muted-foreground">No call yet</li>
        )}
      </ul>
      {scene.followOutcome ? (
        <Pill tone="red" icon={TriangleAlert} className="animate-arrive self-start">
          Household: did not arrive
        </Pill>
      ) : null}
    </Card>
  );
}

// ---------------------------------------------------------------- result tiles

const METRICS: [string, string][] = [
  ["category_extraction", "Needs found"],
  ["organization_compatibility", "Right organization"],
  ["false_closure", "False closures"],
  ["groundedness", "Grounded"],
  ["relevant_lesson_use", "Lesson used"],
];
const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);

function LessonTile({ scene }: { scene: Scene }) {
  const l = scene.lesson;
  return (
    <Card className="space-y-2 p-3">
      <CardHead icon={BookOpen} title="Lesson" />
      {l ? (
        <div className="animate-arrive space-y-2">
          <div className="flex flex-wrap gap-1.5">
            <Pill tone="green" icon={Check}>
              Approved
            </Pill>
            <Pill>De-identified</Pill>
            {l.conditions.map((c) => (
              <Pill key={c} tone="amber">
                {conditionLabel(c)}
              </Pill>
            ))}
          </div>
          <p className="text-xs text-ink">{l.recommendation}</p>
        </div>
      ) : (
        <p className="py-3 text-center text-xs text-muted-foreground">After a person confirms</p>
      )}
    </Card>
  );
}

function MeasureTile({ compare }: { compare: CompareResult | null }) {
  const without = compare?.evaluations.find((e) => e.variant === "without_history");
  const withH = compare?.evaluations.find((e) => e.variant === "with_history");
  return (
    <Card className="space-y-2 p-3">
      <CardHead icon={Gauge} title="Measured" badge={compare ? `${compare.case_count ?? "?"} cases · recorded${compare.synthetic ? " · synthetic" : ""}` : undefined} />
      {without && withH ? (
        <div className="animate-arrive">
          <div className="grid grid-cols-[1fr_auto_auto_auto] gap-x-3 gap-y-1 text-xs tabular-nums">
            <span />
            <span className="text-right text-[10px] font-medium text-muted-foreground">Without</span>
            <span className="text-right text-[10px] font-medium text-muted-foreground">With history</span>
            <span />
            {METRICS.map(([key, label]) => {
              const a = without.metrics[key];
              const b = withH.metrics[key];
              const same = a !== null && b !== null && a === b;
              return (
                <div key={key} className="contents">
                  <span className="text-ink">{label}</span>
                  <span className="text-right text-muted-foreground">{pct(a)}</span>
                  <span className="text-right font-medium text-ink">{pct(b)}</span>
                  <span className="text-[11px] text-muted-foreground">{same ? "no change" : a === null || b === null ? "history only" : "differs"}</span>
                </div>
              );
            })}
          </div>
        </div>
      ) : (
        <p className="py-3 text-center text-xs text-muted-foreground">Last step</p>
      )}
    </Card>
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

  return (
    <div className="space-y-3">
      <Card className="space-y-3 p-3">
        <div className="flex flex-wrap items-center gap-2">
          <Button size="lg" className="h-10 gap-2 px-5 text-base" disabled={starting} onClick={onPrimary}>
            {starting ? <Loader2 aria-hidden className="animate-spin" /> : <PrimaryIcon aria-hidden />}
            {primaryLabel}
          </Button>
          <Button variant="outline" disabled={!live} onClick={() => runner.current?.skip()}>
            <SkipForward aria-hidden /> Skip step
          </Button>
          <div role="group" aria-label="Speed" className="flex overflow-hidden rounded-lg border border-line">
            {[1, 2].map((n) => (
              <button
                key={n}
                type="button"
                aria-pressed={speed === n}
                onClick={() => pickSpeed(n)}
                className={cn("h-8 px-3 text-sm font-medium tabular-nums outline-none", speed === n ? "bg-agent text-white" : "bg-surface text-muted-foreground hover:bg-muted")}
              >
                {n}x
              </button>
            ))}
          </div>
          <Button variant="outline" disabled={starting || rs.status === "idle"} onClick={() => void start(scriptId)}>
            <RotateCcw aria-hidden /> Restart
          </Button>
          <Button variant="outline" className="ml-auto" disabled={starting} onClick={() => void start("safety")}>
            <ShieldAlert aria-hidden className="text-promise-lapsed" /> Safety demo
          </Button>
        </div>
        <Rail script={script} state={rs} />
        <p className="text-[11px] text-muted-foreground">
          Phone line, speech-to-text, triage model, helpers and sandboxes: <Sample>sample · not connected</Sample> Board, claims, calls and lessons: real state in the simulated backend.
        </p>
      </Card>

      <div className="grid gap-3 lg:grid-cols-3">
        <CallCard script={script} scene={scene} />
        <TriageCard scene={scene} />
        <MiniBoard board={board} scene={scene} />
      </div>

      <div className="grid gap-3 xl:grid-cols-[3fr_2fr]">
        <HelpersStrip scene={scene} />
        <FollowUpPanel script={script} scene={scene} />
      </div>

      {scriptId === "main" ? (
        <div className="grid gap-3 md:grid-cols-2">
          <LessonTile scene={scene} />
          <MeasureTile compare={scene.compare} />
        </div>
      ) : null}
    </div>
  );
}
