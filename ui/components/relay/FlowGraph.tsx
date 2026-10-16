"use client";

// The Live demo's hero: one left-to-right graph from "a 911 call comes in" to "the next disaster is triaged better".
// Relay plugs onto the existing call lines; every node and edge is driven by the same Scene/RunnerState the scripted
// demo produces, so what lights up is what actually happened in the backend. Each stage owns one hue.
import {
  AudioLines,
  Building2,
  Check,
  Headphones,
  LayoutDashboard,
  Lightbulb,
  MessageSquareText,
  Phone,
  PhoneCall,
  Plug,
  Radio,
  ShieldAlert,
  ShieldCheck,
  Sparkles,
  UserCheck,
  type LucideIcon,
} from "lucide-react";
import { useLayoutEffect, useRef, useState, useSyncExternalStore, type ComponentType, type CSSProperties, type ReactNode, type SVGProps } from "react";
import { cn } from "@/lib/utils";
import type { RunnerState } from "@/lib/relay/demoRunner";
import type { Channel, DemoScript, Scene } from "@/lib/relay/demoScript";
import { categoryLabel, conditionLabel, orgName } from "@/lib/relay/selectors";
import type { Board } from "@/lib/relay/types";
import { countByStatus, metricDelta } from "@/lib/relay/viz";
import { StatusGlyph, shortOrg } from "./ui";
import { StatusTally } from "./charts";
import { CategoryIcon } from "./ResponseView";
import { ArizeLogo, DaytonaLogo, ElevenLabsLogo, GroqLogo, SurrealDBLogo } from "./logos";

type Brand = { name: string; logo: ComponentType<SVGProps<SVGSVGElement>> };
const ELEVENLABS: Brand = { name: "ElevenLabs", logo: ElevenLabsLogo };
const GROQ: Brand = { name: "Groq", logo: GroqLogo };
const DAYTONA: Brand = { name: "Daytona", logo: DaytonaLogo };
const SURREAL: Brand = { name: "SurrealDB", logo: SurrealDBLogo };
const ARIZE: Brand = { name: "Arize", logo: ArizeLogo };

/* ------------------------------------------------------------------ stages */

type Stage = "line" | "ai" | "safety" | "hub" | "respond" | "verify" | "learn";
const HUE: Record<Stage, string> = {
  line: "var(--text)",
  ai: "var(--st-ai)",
  safety: "var(--st-safety)",
  hub: "var(--st-hub)",
  respond: "var(--st-respond)",
  verify: "var(--st-verify)",
  learn: "var(--st-learn)",
};

/** Which hue a demo step belongs to, so the progress rail matches the graph. */
export const STEP_HUE: Record<string, string> = {
  call: HUE.ai,
  emergency: HUE.safety,
  triage: HUE.ai,
  dashboard: HUE.hub,
  claim: HUE.respond,
  delivery: HUE.respond,
  "helper-call": HUE.verify,
  reopen: HUE.safety,
  alert: HUE.safety,
  resolve: HUE.learn,
  lesson: HUE.learn,
  measure: HUE.learn,
};

const hue = (c: string) => ({ "--c": c }) as CSSProperties;

/* ------------------------------------------------------------------ geometry */

const W = 1280;
const H = 664;
const CY = 231; // every box on the main axis shares this centre line, so the primary edges are dead straight

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
type NodeId = "stt" | "gate" | "triage" | "hub" | "orgs" | "voice" | "human" | "lesson" | `src-${Channel}`;

const SOURCES: { channel: Channel; name: string; sub: string; icon: LucideIcon }[] = [
  { channel: "phone", name: "911 calls", sub: "Voice", icon: Phone },
  { channel: "radio", name: "Radio dispatch", sub: "Voice", icon: Radio },
  { channel: "helpline", name: "211 helpline", sub: "Voice", icon: Headphones },
  { channel: "sms", name: "Text to 911", sub: "SMS · web", icon: MessageSquareText },
];

const BOX: Record<NodeId, Box> = {
  "src-phone": { x: 12, y: 56, w: 148, h: 80 },
  "src-radio": { x: 12, y: 146, w: 148, h: 80 },
  "src-helpline": { x: 12, y: 236, w: 148, h: 80 },
  "src-sms": { x: 12, y: 326, w: 148, h: 80 },
  stt: { x: 216, y: CY - 160, w: 172, h: 320 },
  gate: { x: 430, y: CY - 78, w: 140, h: 156 },
  triage: { x: 612, y: CY - 170, w: 184, h: 340 },
  hub: { x: 840, y: CY - 170, w: 196, h: 340 },
  orgs: { x: 1080, y: 58, w: 188, h: 214 },
  voice: { x: 1080, y: 284, w: 188, h: 316 },
  human: { x: 430, y: 496, w: 210, h: 102 },
  lesson: { x: 664, y: 496, w: 288, h: 116 },
};

const PLUG = { x: 190, y: CY, r: 13 };

/** Tinted lanes behind each stage, numbered so the order reads in one glance. */
const BANDS: { n: number; title: string; stage: Stage; x: number; y: number; w: number; h: number; external?: boolean; steps: string[]; titleX?: number }[] = [
  { n: 1, title: "911 lines", stage: "line", x: 0, y: 26, w: 172, h: 394, external: true, steps: ["call"] },
  { n: 2, title: "Transcribe", stage: "ai", x: 204, y: 26, w: 196, h: 394, steps: ["call"] },
  { n: 3, title: "Safety", stage: "safety", x: 418, y: 26, w: 164, h: 394, steps: ["emergency"] },
  { n: 4, title: "Triage", stage: "ai", x: 600, y: 26, w: 208, h: 394, steps: ["triage"] },
  { n: 5, title: "Dashboard", stage: "hub", x: 828, y: 26, w: 220, h: 394, steps: ["dashboard"] },
  { n: 6, title: "Respond + verify", stage: "respond", x: 1068, y: 26, w: 212, h: 586, steps: ["claim", "delivery", "helper-call"] },
  { n: 7, title: "Close the loop", stage: "learn", x: 412, y: 462, w: 556, h: 162, steps: ["alert", "reopen", "resolve", "lesson", "measure"], titleX: 160 }, // title sits clear of the edges entering from above
];

type Pt = [number, number];

/** Orthogonal path with softened corners. */
function rounded(points: Pt[], r = 10): string {
  let d = `M${points[0][0]} ${points[0][1]}`;
  for (let i = 1; i < points.length - 1; i++) {
    const [px, py] = points[i - 1];
    const [cx, cy] = points[i];
    const [nx, ny] = points[i + 1];
    const l1 = Math.hypot(cx - px, cy - py);
    const l2 = Math.hypot(nx - cx, ny - cy);
    const r1 = Math.min(r, l1 / 2);
    const r2 = Math.min(r, l2 / 2);
    const ax = cx - ((cx - px) / l1) * r1;
    const ay = cy - ((cy - py) / l1) * r1;
    const bx = cx + ((nx - cx) / l2) * r2;
    const by = cy + ((ny - cy) / l2) * r2;
    d += ` L${ax} ${ay} Q${cx} ${cy} ${bx} ${by}`;
  }
  const last = points[points.length - 1];
  return d + ` L${last[0]} ${last[1]}`;
}

const right = (id: NodeId, dy = 0.5): Pt => [BOX[id].x + BOX[id].w, BOX[id].y + BOX[id].h * dy];
const left = (id: NodeId, dy = 0.5): Pt => [BOX[id].x, BOX[id].y + BOX[id].h * dy];
const bottom = (id: NodeId, dx = 0.5): Pt => [BOX[id].x + BOX[id].w * dx, BOX[id].y + BOX[id].h];

type EdgeKind = "flow" | "alert" | "feedback";
interface Edge {
  id: string;
  points: Pt[];
  /** Demo step during which this edge carries something. */
  at: string;
  /** Hue of the stage the edge delivers into. */
  stage: Stage;
  kind?: EdgeKind;
  label?: string;
  labelAt?: Pt;
  anchor?: "start" | "middle" | "end";
  /** Only drawn for this script. */
  only?: DemoScript["id"];
  channel?: Channel;
}

const GAP_R = (BOX.hub.x + BOX.hub.w + BOX.orgs.x) / 2; // channel between the dashboard and the right-hand column
const gateX = bottom("gate")[0];
const LOOP_Y = 640; // the long return edge runs under the bottom row
const JOIN_X = 176;

const EDGES: Edge[] = [
  ...SOURCES.map((s): Edge => {
    const [x0, y0] = right(`src-${s.channel}` as NodeId);
    return { id: `e-${s.channel}`, at: "call", stage: "line", channel: s.channel, points: [[x0, y0], [JOIN_X, y0], [JOIN_X, CY], [PLUG.x - PLUG.r, CY]] };
  }),
  { id: "e-plug-stt", at: "call", stage: "ai", points: [[PLUG.x + PLUG.r, CY], left("stt")] },
  { id: "e-stt-gate", at: "emergency", stage: "safety", points: [right("stt"), left("gate")] },
  { id: "e-gate-triage", at: "triage", stage: "ai", points: [right("gate"), left("triage")], label: "clear", labelAt: [591, CY - 8] },
  { id: "e-triage-hub", at: "dashboard", stage: "hub", points: [right("triage"), left("hub")], label: "needs", labelAt: [818, CY - 8] },
  {
    id: "e-hub-orgs",
    at: "claim",
    stage: "respond",
    points: [right("hub", 0.2), [GAP_R - 10, right("hub", 0.2)[1]], [GAP_R - 10, BOX.orgs.y + 66], [BOX.orgs.x, BOX.orgs.y + 66]],
    label: "match",
    labelAt: [GAP_R, right("hub", 0.2)[1] - 10],
  },
  {
    id: "e-orgs-hub",
    at: "delivery",
    stage: "hub",
    points: [[BOX.orgs.x, BOX.orgs.y + 150], [GAP_R + 10, BOX.orgs.y + 150], [GAP_R + 10, right("hub", 0.42)[1]], [right("hub")[0], right("hub", 0.42)[1]]],
    label: "delivered",
    labelAt: [GAP_R, BOX.orgs.y + 166],
  },
  {
    id: "e-hub-voice",
    at: "helper-call",
    stage: "verify",
    points: [right("hub", 0.82), [GAP_R - 10, right("hub", 0.82)[1]], [GAP_R - 10, BOX.voice.y + 62], [BOX.voice.x, BOX.voice.y + 62]],
    label: "verify",
    labelAt: [GAP_R, BOX.voice.y + 52],
  },
  {
    id: "e-voice-human",
    at: "reopen",
    stage: "safety",
    kind: "alert",
    points: [bottom("voice"), [bottom("voice")[0], LOOP_Y], [BOX.human.x + 170, LOOP_Y], [BOX.human.x + 170, BOX.human.y + BOX.human.h]],
    label: "household: did not arrive",
    labelAt: [1010, LOOP_Y + 15],
  },
  { id: "e-gate-human", at: "emergency", stage: "safety", only: "safety", kind: "alert", points: [bottom("gate"), [gateX, BOX.human.y]], label: "emergency", labelAt: [gateX + 8, 446], anchor: "start" },
  { id: "e-gate-human-alert", at: "alert", stage: "safety", only: "safety", kind: "alert", points: [bottom("gate"), [gateX, BOX.human.y]] },
  {
    id: "e-human-hub",
    at: "resolve",
    stage: "learn",
    points: [[BOX.human.x + 124, BOX.human.y], [BOX.human.x + 124, 440], [880, 440], [880, bottom("hub")[1]]],
    label: "verified by a person",
    labelAt: [BOX.human.x + 136, 434],
    anchor: "start",
  },
  { id: "e-hub-lesson", at: "lesson", stage: "learn", points: [[996, bottom("hub")[1]], [996, 452], [920, 452], [920, BOX.lesson.y]], label: "reviewed", labelAt: [1004, 448], anchor: "start" },
  { id: "e-lesson-triage", at: "measure", stage: "ai", kind: "feedback", points: [[724, BOX.lesson.y], [724, bottom("triage")[1]]], label: "history improves triage", labelAt: [732, 482], anchor: "start" },
];

/* ------------------------------------------------------------------ run-state helpers */

type NodeState = "idle" | "active" | "done" | "alert" | "skipped";
type StepState = "off" | "idle" | "active" | "done";

const NODE_STEPS: Record<string, string[]> = {
  stt: ["call"],
  gate: ["emergency"],
  triage: ["triage"],
  hub: ["dashboard"],
  orgs: ["claim", "delivery"],
  voice: ["helper-call"],
  human: ["alert", "reopen", "resolve"],
  lesson: ["lesson", "measure"],
};

function useRunView(script: DemoScript, rs: RunnerState) {
  const stepIndex = (id: string) => script.steps.findIndex((s) => s.id === id);
  const started = rs.status !== "idle";
  const finished = rs.status === "done";
  const stateOfStep = (id: string): StepState => {
    const i = stepIndex(id);
    if (i < 0) return "off";
    if (!started) return "idle";
    if (finished || i < rs.index) return "done";
    return i === rs.index ? "active" : "idle";
  };
  const combine = (steps: string[]): NodeState => {
    const states = steps.map(stateOfStep).filter((s) => s !== "off");
    if (!states.length) return "skipped";
    if (states.includes("active")) return "active";
    if (states.every((s) => s === "done")) return "done";
    if (states.includes("done")) return "active"; // between steps of a multi-step node
    return "idle";
  };
  return { started, stateOfStep, combine, stateOfNode: (id: string) => combine(NODE_STEPS[id] ?? []) };
}

/* ------------------------------------------------------------------ node chrome */

function NodeBox({
  id,
  state,
  stage,
  icon: Icon,
  title,
  sub,
  brands,
  children,
  footer,
  dim,
  flow = true,
}: {
  id: NodeId;
  state: NodeState;
  stage: Stage;
  icon: LucideIcon;
  title: string;
  sub?: string;
  /** The real services that run this step, shown by their marks. */
  brands?: Brand[];
  children?: ReactNode;
  footer?: ReactNode;
  /** The run has started and has not reached this node yet. */
  dim?: boolean;
  flow?: boolean;
}) {
  const b = BOX[id];
  const c = state === "alert" ? HUE.safety : HUE[stage];
  const lit = state === "active" || state === "alert";
  return (
    <section
      aria-label={title}
      data-state={state}
      style={{ ...hue(c), ...(flow ? { left: b.x, top: b.y, width: b.w, height: b.h } : {}) }}
      className={cn(
        "flex flex-col overflow-hidden rounded-[12px] border bg-panel text-xs shadow-[var(--ds-shadow-small)] transition-[border-color,box-shadow,opacity] duration-300",
        flow && "absolute",
        lit ? "border-[var(--c)] shadow-[0_0_0_4px_color-mix(in_srgb,var(--c)_16%,transparent),0_8px_24px_-12px_color-mix(in_srgb,var(--c)_45%,transparent)]" : "border-line",
        state === "skipped" && "border-dashed opacity-40",
        dim && state === "idle" && "opacity-55",
      )}
    >
      <header className="flex items-center gap-2 px-2.5 pb-1.5 pt-2.5">
        <span
          className={cn(
            "relative grid size-7 shrink-0 place-items-center rounded-[7px] transition-colors duration-300",
            lit ? "bg-[var(--c)] text-white" : "bg-[color-mix(in_srgb,var(--c)_11%,transparent)] text-[var(--c)]",
          )}
        >
          <Icon aria-hidden className="size-3.5" />
          {state === "done" ? (
            <span className="absolute -right-1 -top-1 grid size-3.5 place-items-center rounded-full bg-[var(--c)] ring-2 ring-panel">
              <Check aria-label="Done" className="size-2 text-white" strokeWidth={3.5} />
            </span>
          ) : null}
        </span>
        <div className="min-w-0 flex-1 leading-tight">
          <h3 className="truncate text-[13px] font-semibold tracking-[-0.01em] text-ink">{title}</h3>
          {brands?.length ? (
            <p className="mt-0.5 flex flex-wrap items-center gap-x-1.5 text-[11px] font-medium text-ink-2">
              {brands.map(({ name, logo: Logo }) => (
                <span key={name} className="inline-flex items-center gap-1">
                  <Logo aria-hidden className="size-3 shrink-0" />
                  {name}
                </span>
              ))}
            </p>
          ) : sub ? (
            <p className="truncate text-[10.5px] text-muted-foreground">{sub}</p>
          ) : null}
        </div>
      </header>
      <div className="min-h-0 flex-1 overflow-hidden px-2.5 pb-2.5 pt-1">{children}</div>
      {footer ? <footer className="border-t border-line px-2.5 py-1.5 text-[11px] text-ink-2">{footer}</footer> : null}
    </section>
  );
}

const Quiet = ({ children }: { children: ReactNode }) => <p className="pt-4 text-center text-[11px] text-muted-foreground">{children}</p>;

/* ------------------------------------------------------------------ node bodies */

function Waveform({ live }: { live: boolean }) {
  return (
    <span aria-hidden className="flex h-6 flex-1 items-center gap-[2px]">
      {[0, 2, 1, 3, 1, 2, 0, 3, 1, 2, 0, 3, 2, 1, 3, 0, 2, 1].map((d, i) => (
        <span
          key={i}
          className={cn("h-full w-[2px] origin-center rounded-full", live ? "animate-wave bg-[var(--c)]" : "scale-y-[0.18] bg-line-strong")}
          style={live ? { animationDelay: `${d * 110 + i * 35}ms` } : undefined}
        />
      ))}
    </span>
  );
}

function SourceNode({ s, scene, started }: { s: (typeof SOURCES)[number]; scene: Scene; started: boolean }) {
  const Icon = s.icon;
  const used = started && scene.channel === s.channel;
  const live = used && scene.callActive;
  const b = BOX[`src-${s.channel}` as NodeId];
  return (
    <section
      aria-label={s.name}
      data-state={live ? "active" : used ? "done" : "idle"}
      style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
      className={cn(
        "absolute flex flex-col justify-between rounded-[12px] border bg-panel p-2.5 transition-[border-color,box-shadow,opacity] duration-300",
        live ? "border-ink shadow-[0_0_0_4px_color-mix(in_srgb,var(--text)_10%,transparent)]" : used ? "border-line-strong" : "border-line",
        started && !used && "opacity-55",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("relative grid size-7 place-items-center rounded-[7px] transition-colors", live ? "bg-ink text-panel" : "bg-hover text-ink-2")}>
          <Icon aria-hidden className="size-3.5" />
          {live ? <span aria-hidden className="absolute inset-0 animate-call-ring rounded-[7px]" /> : null}
        </span>
        <span className="min-w-0 leading-tight">
          <span className="block truncate text-[12.5px] font-semibold text-ink">{s.name}</span>
          <span className="block text-[10.5px] text-muted-foreground">{s.sub}</span>
        </span>
      </div>
      {used ? (
        <p className="flex items-center gap-1.5 text-[10.5px] font-medium text-ink">
          <span aria-hidden className={cn("size-1.5 rounded-full bg-promise-kept", live && "animate-pulse")} />
          {live ? "On the line" : "Call received"}
        </p>
      ) : (
        <span aria-hidden className="h-px w-full bg-line" />
      )}
    </section>
  );
}

function SttBody({ script, scene }: { script: DemoScript; scene: Scene }) {
  const lines = script.call.slice(0, scene.callLines);
  const shown = lines.slice(-4);
  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center gap-2 rounded-md bg-surface px-2 py-1">
        <Waveform live={scene.callActive} />
      </div>
      <ul aria-label="Call transcript" aria-live="polite" className="flex-1 space-y-1.5 overflow-hidden">
        {shown.map((l, i) =>
          l.speaker === "system" ? (
            <li key={`${lines.length - shown.length + i}`} className="animate-arrive text-center text-[10px] text-muted-foreground">
              {l.text}
            </li>
          ) : (
            <li
              key={`${lines.length - shown.length + i}`}
              className={cn(
                "animate-arrive rounded-md px-2 py-1 text-[11px] leading-snug",
                l.speaker === "caller" ? "bg-[color-mix(in_srgb,var(--c)_9%,transparent)] text-ink" : "border border-line text-ink-2",
              )}
            >
              <span className="mb-0.5 block text-[9px] font-medium uppercase tracking-wider text-muted-foreground">{l.speaker === "caller" ? "Caller" : "Relay"}</span>
              {l.text}
            </li>
          ),
        )}
        {!lines.length ? <li className="pt-6 text-center text-[11px] text-muted-foreground">Waiting for a call</li> : null}
      </ul>
    </div>
  );
}

function GateBody({ scene }: { scene: Scene }) {
  const e = scene.emergency;
  const Icon = e === "tripped" ? ShieldAlert : ShieldCheck;
  return (
    <div className="flex h-full flex-col items-center justify-center gap-1.5 text-center">
      <span
        className={cn(
          "grid size-10 place-items-center rounded-full",
          e === "tripped" ? "bg-promise-lapsed text-white" : e === "clear" ? "bg-promise-kept/12 text-promise-kept" : e === "checking" ? "animate-pulse bg-[color-mix(in_srgb,var(--c)_14%,transparent)] text-[var(--c)]" : "bg-hover text-muted-foreground",
        )}
      >
        <Icon aria-hidden className="size-[18px]" />
      </span>
      <p className={cn("text-[12px] font-semibold", e === "tripped" ? "text-promise-lapsed" : e === "clear" ? "text-promise-kept" : "text-ink-2")} role="status">
        {e === "idle" ? "Waiting" : e === "checking" ? "Checking" : e === "clear" ? "Clear" : "Emergency"}
      </p>
    </div>
  );
}

function TriageBody({ scene }: { scene: Scene }) {
  const t = scene.triage;
  if (scene.triageSkipped) return <Quiet>Skipped. Emergencies go to a person first.</Quiet>;
  if (scene.triageLoading)
    return (
      <div role="status" aria-label="Triage running" className="space-y-2 pt-1">
        {[80, 52, 66, 40].map((w) => (
          <div key={w} className="h-5 animate-shimmer rounded-[5px] bg-[color-mix(in_srgb,var(--c)_10%,transparent)]" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  if (!t) return <Quiet>Waiting for the transcript</Quiet>;
  return (
    <div className="space-y-3">
      <div>
        <p className="label !text-[9.5px]">Needs</p>
        <ul className="mt-1.5 space-y-1">
          {t.needs.map((n, i) => (
            <li
              key={n}
              style={{ animationDelay: `${i * 140}ms` }}
              className="flex animate-arrive items-center gap-2 rounded-md bg-[color-mix(in_srgb,var(--c)_10%,transparent)] px-2 py-1.5 text-[12px] font-semibold text-[var(--c)] [animation-fill-mode:backwards]"
            >
              <CategoryIcon category={n} className="size-3.5" />
              {categoryLabel(n)}
            </li>
          ))}
        </ul>
      </div>
      {t.conditions.length ? (
        <div>
          <p className="label !text-[9.5px]">Conditions</p>
          <p className="mt-1 text-[11.5px] text-ink">{t.conditions.map(conditionLabel).join(" · ")}</p>
        </div>
      ) : null}
      <dl className="grid grid-cols-2 gap-2 text-[11px]">
        <div>
          <dt className="label !text-[9.5px]">Deadline</dt>
          <dd className="text-ink">{t.deadline}</dd>
        </div>
        <div>
          <dt className="label !text-[9.5px]">Workload</dt>
          <dd className="text-ink">{t.workload}</dd>
        </div>
      </dl>
    </div>
  );
}

function HubBody({ board, scene }: { board: Board | null; scene: Scene }) {
  const requests = board?.requests ?? [];
  const mine = scene.requestIds.flatMap((id) => requests.find((r) => r.id === id) ?? []);
  return (
    <div className="flex h-full flex-col gap-3">
      <StatusTally counts={countByStatus(requests)} variant="list" />
      {scene.alert ? (
        <p role="alert" className="animate-arrive rounded-md bg-promise-lapsed/10 px-2 py-1.5 text-[11px] font-medium text-ink">
          <ShieldAlert aria-hidden className="mr-1 inline size-3 -translate-y-px text-promise-lapsed" />
          {scene.alert}
        </p>
      ) : null}
      <ul className="flex-1 space-y-1 overflow-hidden" aria-label="Requests from this call">
        {mine.map((r) => (
          <li key={r.id} className="flex animate-arrive items-center gap-2 rounded-md border border-line px-2 py-1.5">
            <StatusGlyph status={r.status} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[11.5px] font-medium text-ink">{categoryLabel(r.category)}</span>
              <span className="block truncate text-[10px] text-muted-foreground">{r.organization_id && board ? shortOrg(orgName(board, r.organization_id)) : "Unclaimed"}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

const PHASE: Record<string, string> = { idle: "", tagging: "Suggested", claimed: "Claimed", delivered: "Delivered" };

function OrgsBody({ board, scene }: { board: Board | null; scene: Scene }) {
  return (
    <ul className="space-y-1.5" aria-label="Volunteer organizations">
      {(board?.organizations ?? []).map((o) => {
        const st = scene.orgs[o.id];
        const active = st && st.phase !== "idle";
        return (
          <li key={o.id} className={cn("rounded-md border px-2 py-1.5 transition-colors", active ? "border-transparent bg-[color-mix(in_srgb,var(--c)_10%,transparent)]" : "border-line")}>
            <div className="flex items-center gap-2">
              <span
                aria-hidden
                className={cn("grid size-[18px] shrink-0 place-items-center rounded-[5px] font-mono text-[10px] font-semibold", active ? "bg-[var(--c)] text-white" : "bg-hover text-ink-2")}
              >
                {shortOrg(o.name).charAt(0)}
              </span>
              <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-ink">{shortOrg(o.name)}</span>
              <span className="flex shrink-0 gap-1 text-muted-foreground">
                {o.capabilities.map((c) => (
                  <CategoryIcon key={c} category={c} className={cn("size-3", active && "text-[var(--c)]")} />
                ))}
              </span>
            </div>
            {active ? (
              <p key={st.phase} className="mt-0.5 flex animate-arrive items-center gap-1 pl-[26px] text-[10.5px] font-semibold text-[var(--c)]">
                {st.phase !== "tagging" ? <Check aria-hidden className="size-3" strokeWidth={2.5} /> : null}
                {PHASE[st.phase]}
              </p>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}

function VoiceBody({ script, scene }: { script: DemoScript; scene: Scene }) {
  const lines = script.followUp.slice(0, scene.followLines).filter((l) => l.speaker !== "system");
  return (
    <div className="flex h-full flex-col gap-2">
      <ul aria-label="AI Help Force" className="grid grid-cols-1 gap-1">
        {scene.helpers.map((h) => (
          <li key={h.id} className="flex flex-wrap items-baseline gap-x-1.5">
            <span aria-hidden className={cn("size-1.5 shrink-0 -translate-y-px rounded-full", h.status === "working" ? "animate-pulse bg-[var(--c)]" : "bg-line-strong")} />
            <span className={cn("shrink-0 text-[11px]", h.status === "working" ? "font-semibold text-ink" : "text-ink-2")}>
              {h.role}
              <span className="sr-only"> {h.status}</span>
            </span>
            {h.status === "working" ? <span className="w-full truncate pl-3 text-[10px] text-[var(--c)]">{h.lastAction}</span> : null}
          </li>
        ))}
      </ul>
      <div className="mt-auto space-y-1 border-t border-line pt-2">
        <ul aria-label="Follow-up call transcript" aria-live="polite" className="space-y-1">
          {lines.slice(scene.followOutcome ? -2 : -3).map((l, i) => (
            <li
              key={`${lines.length}-${i}`}
              className={cn(
                "animate-arrive line-clamp-2 rounded-md px-2 py-1 text-[10.5px] leading-snug",
                l.speaker === "caller" ? "bg-[color-mix(in_srgb,var(--c)_11%,transparent)] text-ink" : "border border-line text-ink-2",
              )}
            >
              {l.text}
            </li>
          ))}
          {!lines.length ? <li className="text-[10.5px] text-muted-foreground">Calls the household after delivery</li> : null}
        </ul>
        {scene.followOutcome ? <p className="animate-arrive text-[11px] font-semibold text-promise-lapsed">Household: did not arrive</p> : null}
      </div>
    </div>
  );
}

function HumanBody({ scene }: { scene: Scene }) {
  const hot = Boolean(scene.alert || scene.humanReview);
  const text = scene.humanReview ? "Reviewing the re-delivery" : scene.alert ? scene.alert : "Standing by. A person decides, never the model.";
  return <p className={cn("text-[11.5px] leading-snug", hot ? "font-medium text-ink" : "text-muted-foreground")}>{text}</p>;
}

const METRIC_SHORT: Record<string, { label: string; lower?: boolean }> = {
  category_extraction: { label: "Needs found" },
  organization_compatibility: { label: "Right organization" },
  false_closure: { label: "False closures", lower: true },
  groundedness: { label: "Grounded" },
  relevant_lesson_use: { label: "Lesson used" },
};

function LessonBody({ scene }: { scene: Scene }) {
  const l = scene.lesson;
  const without = scene.compare?.evaluations.find((e) => e.variant === "without_history");
  const withH = scene.compare?.evaluations.find((e) => e.variant === "with_history");
  const deltas =
    without && withH
      ? Object.keys(METRIC_SHORT)
          .map((m) => metricDelta(m, without.metrics[m], withH.metrics[m], METRIC_SHORT[m].lower))
          .filter((d) => d.direction !== "same")
          .slice(0, 2)
      : [];
  return (
    <div className="space-y-1.5">
      {l ? (
        <p className="line-clamp-2 animate-arrive text-[11px] leading-snug text-ink" title={l.recommendation}>
          {l.recommendation}
        </p>
      ) : (
        <p className="text-[11px] text-muted-foreground">Learned from verified outcomes, approved by a person.</p>
      )}
      {without && withH ? (
        <ul className="animate-arrive space-y-0.5 border-t border-line pt-1.5 text-[10.5px]" aria-label="Measured with versus without history">
          {deltas.length ? (
            deltas.map((d) => (
              <li key={d.metric} className="flex justify-between gap-2">
                <span className="text-ink-2">{METRIC_SHORT[d.metric].label}</span>
                <span className="num font-semibold text-[var(--c)]">
                  {d.without === null ? "–" : `${Math.round(d.without * 100)}%`} → {d.withHistory === null ? "–" : `${Math.round(d.withHistory * 100)}%`}
                </span>
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">No metric changed</li>
          )}
        </ul>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ lanes, plug, edges */

function Bands({ view }: { view: ReturnType<typeof useRunView> }) {
  return (
    <>
      {BANDS.map((b) => {
        const st = view.combine(b.steps);
        const lit = st === "active";
        return (
          <div
            key={b.n}
            aria-hidden
            style={{ ...hue(HUE[b.stage]), left: b.x, top: b.y, width: b.w, height: b.h }}
            className={cn(
              "absolute rounded-[14px] border transition-[background-color,border-color] duration-500",
              b.external
                ? "border-dashed border-line-strong bg-[color-mix(in_srgb,var(--text)_3%,var(--canvas))]"
                : lit
                  ? "border-[color-mix(in_srgb,var(--c)_32%,transparent)] bg-[color-mix(in_srgb,var(--c)_9%,var(--canvas))]"
                  : "border-[color-mix(in_srgb,var(--c)_16%,transparent)] bg-[color-mix(in_srgb,var(--c)_4%,var(--canvas))]",
            )}
          >
            <p className="flex items-center gap-1.5 px-2.5 pt-2 text-[11px] font-semibold tracking-[-0.005em]" style={b.titleX ? { paddingLeft: b.titleX } : undefined}>
              <span
                className={cn(
                  "grid size-[17px] place-items-center rounded-full text-[9.5px] font-bold tabular-nums transition-colors",
                  lit || st === "done" ? "bg-[var(--c)] text-panel" : "bg-[color-mix(in_srgb,var(--c)_14%,transparent)] text-[var(--c)]",
                )}
              >
                {b.n}
              </span>
              <span className={cn(b.external ? "text-ink-2" : "text-[var(--c)]")}>{b.title}</span>
            </p>
          </div>
        );
      })}
    </>
  );
}

function PlugBadge({ state }: { state: StepState }) {
  const lit = state === "active" || state === "done";
  return (
    <div className="absolute flex flex-col items-center" style={{ left: PLUG.x - PLUG.r, top: PLUG.y - PLUG.r, width: PLUG.r * 2 }} title="Relay plugs into the existing call lines">
      <span className={cn("grid size-[26px] place-items-center rounded-full border-2 bg-panel transition-colors", lit ? "border-st-ai text-st-ai" : "border-line-strong text-muted-foreground")}>
        <Plug aria-hidden className="size-3" />
      </span>
      <span className="mt-1 whitespace-nowrap rounded-full bg-panel px-1.5 text-[9.5px] font-semibold text-ink-2 shadow-[0_0_0_1px_var(--border)]">plug-in</span>
    </div>
  );
}

function Edges({ script, scene, view }: { script: DemoScript; scene: Scene; view: ReturnType<typeof useRunView> }) {
  return (
    <svg aria-hidden width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="pointer-events-none absolute inset-0 overflow-visible">
      <defs>
        {(["idle", ...Object.keys(HUE)] as const).map((k) => (
          <marker key={k} id={`arrow-${k}`} viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M1 1l5.5 3L1 7" fill="none" stroke={k === "idle" ? "var(--line-strong)" : HUE[k as Stage]} strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" />
          </marker>
        ))}
      </defs>
      {EDGES.map((e) => {
        if (e.only && e.only !== script.id) return null;
        let state = view.stateOfStep(e.at);
        if (e.channel) {
          if (scene.channel !== e.channel) state = state === "off" ? "off" : "idle";
          else if (state === "idle" && scene.callActive) state = "active";
        }
        if (state === "off") return null;
        const kind = e.kind ?? "flow";
        const lit = state !== "idle";
        const color = lit ? HUE[e.stage] : "var(--line-strong)";
        const d = rounded(e.points);
        return (
          <g key={e.id} data-edge={e.id} data-state={state}>
            <path
              d={d}
              fill="none"
              stroke={color}
              strokeWidth={lit ? 2 : 1.25}
              strokeOpacity={state === "done" ? 0.55 : 1}
              strokeDasharray={kind === "feedback" ? "5 4" : undefined}
              markerEnd={e.channel ? undefined : `url(#arrow-${lit ? e.stage : "idle"})`}
              className="transition-[stroke] duration-300"
            />
            {state === "active" ? <path d={d} fill="none" stroke={color} strokeWidth="4" strokeLinecap="round" strokeDasharray="0.1 14" className="flow-dots" /> : null}
            {e.label && e.labelAt && lit ? (
              <text
                x={e.labelAt[0]}
                y={e.labelAt[1]}
                fontSize="10.5"
                fontWeight="600"
                textAnchor={e.anchor ?? "middle"}
                fill={color}
                className="animate-fade"
                stroke="var(--bg)"
                strokeWidth="4"
                paintOrder="stroke"
                strokeLinejoin="round"
              >
                {e.label}
              </text>
            ) : null}
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------------ layout */

const media = (q: string) => ({
  subscribe: (cb: () => void) => {
    const mq = window.matchMedia(q);
    mq.addEventListener("change", cb);
    return () => mq.removeEventListener("change", cb);
  },
  get: () => window.matchMedia(q).matches,
});
const NARROW = media("(max-width: 767px)");
const TALL = media("(min-width: 1024px)");
const useMedia = (m: typeof NARROW) => useSyncExternalStore(m.subscribe, m.get, () => false);

/**
 * `fit`: on large screens the graph scales to fill its parent in both directions (the Live page is one fixed screen).
 * Below that it scales to the width and takes the height it needs.
 */
export function FlowGraph({ script, scene, state, board, fit = false }: { script: DemoScript; scene: Scene; state: RunnerState; board: Board | null; fit?: boolean }) {
  const view = useRunView(script, state);
  const narrow = useMedia(NARROW);
  const tall = useMedia(TALL) && fit;
  const wrap = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const measure = () => {
      const byWidth = el.clientWidth / W;
      setScale(tall ? Math.min(byWidth, el.clientHeight / H, 1.5) : Math.min(1, byWidth));
    };
    measure();
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, [narrow, tall]);

  const tripped = scene.emergency === "tripped";
  const humanState: NodeState = scene.humanReview || scene.alert || tripped ? "alert" : view.stateOfNode("human");
  const dim = view.started && state.status !== "done";
  const nodes = {
    stt: (flow = true) => (
      <NodeBox key="stt" flow={flow} dim={dim} id="stt" stage="ai" icon={AudioLines} title="Speech to text" brands={[ELEVENLABS]} state={view.stateOfNode("stt")}>
        <SttBody script={script} scene={scene} />
      </NodeBox>
    ),
    gate: (flow = true) => (
      <NodeBox key="gate" flow={flow} dim={dim} id="gate" stage="safety" icon={ShieldCheck} title="Emergency" sub="Rules before AI" state={tripped ? "alert" : view.stateOfNode("gate")}>
        <GateBody scene={scene} />
      </NodeBox>
    ),
    triage: (flow = true) => (
      <NodeBox
        key="triage"
        flow={flow}
        dim={dim}
        id="triage"
        stage="ai"
        icon={Sparkles}
        title="AI triage"
        brands={[GROQ]}
        state={scene.triageSkipped ? "skipped" : view.stateOfNode("triage")}
        footer={
          <span className="flex items-center gap-1.5">
            <UserCheck aria-hidden className="size-3 text-[var(--c)]" /> A person decides
          </span>
        }
      >
        <TriageBody scene={scene} />
      </NodeBox>
    ),
    hub: (flow = true) => (
      <NodeBox key="hub" flow={flow} dim={dim} id="hub" stage="hub" icon={LayoutDashboard} title="Triage board" brands={[SURREAL]} state={view.stateOfNode("hub")}>
        <HubBody board={board} scene={scene} />
      </NodeBox>
    ),
    orgs: (flow = true) => (
      <NodeBox key="orgs" flow={flow} dim={dim} id="orgs" stage="respond" icon={Building2} title="Volunteer orgs" sub="Claim and deliver" state={view.stateOfNode("orgs")}>
        <OrgsBody board={board} scene={scene} />
      </NodeBox>
    ),
    voice: (flow = true) => (
      <NodeBox key="voice" flow={flow} dim={dim} id="voice" stage="verify" icon={PhoneCall} title="AI Help Force" brands={[ELEVENLABS, DAYTONA]} state={view.stateOfNode("voice")}>
        <VoiceBody script={script} scene={scene} />
      </NodeBox>
    ),
    human: (flow = true) => (
      <NodeBox key="human" flow={flow} dim={dim} id="human" stage="safety" icon={UserCheck} title="Coordinator" sub="Human in the loop" state={humanState}>
        <HumanBody scene={scene} />
      </NodeBox>
    ),
    lesson: (flow = true) => (
      <NodeBox key="lesson" flow={flow} dim={dim} id="lesson" stage="learn" icon={Lightbulb} title="Reviewed lesson" brands={[ARIZE, SURREAL]} state={view.stateOfNode("lesson")}>
        <LessonBody scene={scene} />
      </NodeBox>
    ),
  };

  if (narrow) {
    // Small screens: the same nodes as a vertical sequence. The geometry above is for the wide canvas only.
    const src = SOURCES.find((s) => s.channel === scene.channel) ?? SOURCES[0];
    return (
      <ol aria-label="Relay flow" className="space-y-2">
        <li className="flex items-center gap-2 rounded-[10px] border border-dashed border-line-strong px-3 py-2 text-xs text-ink">
          <src.icon aria-hidden className="size-3.5 text-ink-2" />
          <span className="font-semibold">{src.name}</span>
          <span className="ml-auto flex items-center gap-1 text-[10.5px] font-semibold text-st-ai">
            <Plug aria-hidden className="size-3" /> plug-in
          </span>
        </li>
        {(["stt", "gate", "triage", "hub", "orgs", "voice", "human", "lesson"] as const).map((k) => (
          <li key={k} className="h-auto [&_section]:!h-auto">
            {nodes[k](false)}
          </li>
        ))}
      </ol>
    );
  }

  return (
    <div ref={wrap} className={cn("relative w-full overflow-hidden", tall && "h-full")} style={tall ? undefined : { height: H * scale }}>
      <div
        role="group"
        aria-label="Relay flow: 911 calls, transcription, emergency check, AI triage, dashboard, volunteer organizations and the AI Help Force"
        className="absolute left-1/2 top-1/2"
        style={{ width: W, height: H, transform: `translate(-50%, -50%) scale(${scale})` }}
      >
        <Bands view={view} />
        <Edges script={script} scene={scene} view={view} />
        <PlugBadge state={view.stateOfStep("call")} />
        {SOURCES.map((s) => (
          <SourceNode key={s.channel} s={s} scene={scene} started={view.started} />
        ))}
        {(Object.keys(nodes) as (keyof typeof nodes)[]).map((k) => nodes[k]())}
      </div>
    </div>
  );
}
