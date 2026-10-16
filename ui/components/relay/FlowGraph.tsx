"use client";

// The Live demo's hero: one left-to-right graph from "a call arrives" to "the next disaster is triaged better".
// Nodes and edges are driven by the same Scene/RunnerState the scripted demo already produces, so what lights up is
// what actually happened in the (simulated) backend. Phone lines, radio, STT, the triage model and the voice agents
// are sample adapters and say so on the node.
import { Check, Headphones, MessageSquareText, Phone, Radio, ShieldAlert, ShieldCheck, UserCheck, type LucideIcon } from "lucide-react";
import { useLayoutEffect, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { cn } from "@/lib/utils";
import type { RunnerState } from "@/lib/relay/demoRunner";
import type { Channel, DemoScript, Scene } from "@/lib/relay/demoScript";
import { categoryLabel, conditionLabel, orgName } from "@/lib/relay/selectors";
import type { Board } from "@/lib/relay/types";
import { countByStatus, metricDelta } from "@/lib/relay/viz";
import { StatusGlyph, shortOrg, Monogram } from "./ui";
import { StatusTally } from "./charts";
import { CategoryIcon } from "./ResponseView";

/* ------------------------------------------------------------------ geometry */

const W = 1260;
const H = 644;

interface Box {
  x: number;
  y: number;
  w: number;
  h: number;
}
type NodeId = "stt" | "gate" | "triage" | "hub" | "orgs" | "voice" | "human" | "lesson" | `src-${Channel}`;

const SOURCES: { channel: Channel; name: string; sub: string; icon: LucideIcon }[] = [
  { channel: "phone", name: "911 phone line", sub: "voice", icon: Phone },
  { channel: "radio", name: "Radio dispatch", sub: "voice", icon: Radio },
  { channel: "helpline", name: "211 helpline", sub: "voice", icon: Headphones },
  { channel: "sms", name: "SMS · web form", sub: "text", icon: MessageSquareText },
];

// Every box on the main axis shares the centre line y = 247, so the primary edges are dead straight.
const BOX: Record<NodeId, Box> = {
  "src-phone": { x: 0, y: 40, w: 140, h: 78 },
  "src-radio": { x: 0, y: 132, w: 140, h: 78 },
  "src-helpline": { x: 0, y: 224, w: 140, h: 78 },
  "src-sms": { x: 0, y: 316, w: 140, h: 78 },
  stt: { x: 196, y: 90, w: 180, h: 314 },
  gate: { x: 416, y: 172, w: 100, h: 150 },
  triage: { x: 572, y: 74, w: 190, h: 346 },
  hub: { x: 818, y: 72, w: 190, h: 350 },
  orgs: { x: 1072, y: 16, w: 188, h: 214 },
  voice: { x: 1072, y: 252, w: 188, h: 350 },
  human: { x: 410, y: 486, w: 200, h: 108 },
  lesson: { x: 650, y: 486, w: 260, h: 128 },
};

type Pt = [number, number];

/** Orthogonal path with softened corners. */
function rounded(points: Pt[], r = 9): string {
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
  kind?: EdgeKind;
  label?: string;
  labelAt?: Pt;
  anchor?: "start" | "middle" | "end";
  /** Only drawn for this script. */
  only?: DemoScript["id"];
  channel?: Channel;
}

const sttIn = left("stt");
const GAP_R = (BOX.hub.x + BOX.hub.w + BOX.orgs.x) / 2; // channel between the dashboard and the right-hand column
const gateX = bottom("gate")[0];
const LOOP_Y = 622; // the long return edge runs under the bottom row

const EDGES: Edge[] = [
  ...SOURCES.map((s): Edge => {
    const [x0, y0] = right(`src-${s.channel}` as NodeId);
    return { id: `e-${s.channel}`, at: "call", channel: s.channel, points: [[x0, y0], [x0 + 28, y0], [x0 + 28, sttIn[1]], sttIn] };
  }),
  { id: "e-stt-gate", at: "emergency", points: [right("stt"), left("gate")] },
  { id: "e-gate-triage", at: "triage", points: [right("gate"), left("triage")], label: "clear", labelAt: [544, 239], anchor: "middle" },
  { id: "e-triage-hub", at: "dashboard", points: [right("triage"), left("hub")], label: "needs", labelAt: [790, 239], anchor: "middle" },
  { id: "e-hub-orgs", at: "claim", points: [right("hub", 0.2), [GAP_R - 12, right("hub", 0.2)[1]], [GAP_R - 12, BOX.orgs.y + 62], [BOX.orgs.x, BOX.orgs.y + 62]], label: "match", labelAt: [GAP_R - 12, 100], anchor: "middle" },
  { id: "e-orgs-hub", at: "delivery", points: [[BOX.orgs.x, BOX.orgs.y + 150], [GAP_R + 12, BOX.orgs.y + 150], [GAP_R + 12, right("hub", 0.4)[1]], [right("hub")[0], right("hub", 0.4)[1]]], label: "delivered", labelAt: [GAP_R + 12, 212], anchor: "middle" },
  { id: "e-hub-voice", at: "helper-call", points: [right("hub", 0.82), [GAP_R - 12, right("hub", 0.82)[1]], [GAP_R - 12, BOX.voice.y + 60], [BOX.voice.x, BOX.voice.y + 60]], label: "call", labelAt: [GAP_R - 12, 332], anchor: "middle" },
  { id: "e-voice-human", at: "reopen", kind: "alert", points: [bottom("voice", 0.5), [bottom("voice", 0.5)[0], LOOP_Y], [BOX.human.x + 160, LOOP_Y], [BOX.human.x + 160, BOX.human.y + BOX.human.h]], label: "household: did not arrive", labelAt: [1000, LOOP_Y + 16], anchor: "middle" },
  { id: "e-gate-human", at: "emergency", only: "safety", kind: "alert", points: [bottom("gate"), [gateX, BOX.human.y]], label: "emergency", labelAt: [gateX + 8, 420], anchor: "start" },
  { id: "e-gate-human-alert", at: "alert", only: "safety", kind: "alert", points: [bottom("gate"), [gateX, BOX.human.y]] },
  { id: "e-human-hub", at: "resolve", points: [[BOX.human.x + 120, BOX.human.y], [BOX.human.x + 120, 452], [860, 452], [860, bottom("hub")[1]]], label: "verified by a person", labelAt: [BOX.human.x + 132, 446], anchor: "start" },
  { id: "e-hub-lesson", at: "lesson", points: [[950, bottom("hub")[1]], [950, 466], [880, 466], [880, BOX.lesson.y]], label: "reviewed", labelAt: [958, 458], anchor: "start" },
  { id: "e-lesson-triage", at: "measure", kind: "feedback", points: [[720, BOX.lesson.y], [720, bottom("triage")[1]]], label: "history informs the next triage", labelAt: [730, 478], anchor: "start" },
];

/* ------------------------------------------------------------------ run-state helpers */

type NodeState = "idle" | "active" | "done" | "alert" | "skipped";

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
  const stateOfStep = (id: string): "off" | "idle" | "active" | "done" => {
    const i = stepIndex(id);
    if (i < 0) return "off";
    if (!started) return "idle";
    if (finished || i < rs.index) return "done";
    return i === rs.index ? "active" : "idle";
  };
  const stateOfNode = (id: string): NodeState => {
    const steps = NODE_STEPS[id] ?? [];
    const states = steps.map(stateOfStep).filter((s) => s !== "off");
    if (!states.length) return "skipped";
    if (states.includes("active")) return "active";
    if (states.every((s) => s === "done")) return "done";
    if (states.includes("done")) return "active"; // between steps of a multi-step node
    return "idle";
  };
  return { stateOfStep, stateOfNode };
}

/* ------------------------------------------------------------------ node chrome */

function NodeBox({
  id,
  state,
  title,
  kicker,
  tag,
  children,
  footer,
  className,
  flow = true,
}: {
  id: NodeId;
  state: NodeState;
  title: string;
  kicker?: string;
  tag?: string;
  children?: ReactNode;
  footer?: ReactNode;
  className?: string;
  flow?: boolean;
}) {
  const b = BOX[id];
  return (
    <section
      aria-label={title}
      data-state={state}
      style={flow ? { left: b.x, top: b.y, width: b.w, height: b.h } : undefined}
      className={cn(
        "flex flex-col overflow-hidden rounded-md border bg-panel text-xs transition-[border-color,box-shadow,opacity] duration-300",
        flow && "absolute",
        state === "active" && "border-agent shadow-[0_0_0_3px_color-mix(in_srgb,var(--agent)_16%,transparent)]",
        state === "done" && "border-line-strong",
        state === "idle" && "border-line",
        state === "alert" && "border-promise-lapsed shadow-[0_0_0_3px_color-mix(in_srgb,var(--promise-lapsed)_14%,transparent)]",
        state === "skipped" && "border-dashed border-line opacity-55",
        className,
      )}
    >
      <header className="flex items-start gap-2 border-b border-line px-2.5 py-2">
        <span
          aria-hidden
          className={cn(
            "mt-[3px] grid size-2 shrink-0 place-items-center rounded-full transition-colors",
            state === "active" ? "animate-pulse bg-agent" : state === "done" ? "bg-agent/60" : state === "alert" ? "bg-promise-lapsed" : "bg-line-strong",
          )}
        />
        <div className="min-w-0 flex-1 leading-tight">
          {kicker ? <p className="label !text-[9.5px]">{kicker}</p> : null}
          <h3 className="text-[12.5px] font-medium text-ink">{title}</h3>
          {tag ? <span className="mt-1 inline-block rounded-[4px] border border-dashed border-line-strong px-1 py-px text-[9px] leading-3.5 text-muted-foreground">{tag}</span> : null}
        </div>
        {state === "done" ? <Check aria-label="Done" className="mt-0.5 size-3 shrink-0 text-agent" /> : null}
      </header>
      <div className="min-h-0 flex-1 overflow-hidden px-2.5 py-2">{children}</div>
      {footer ? <footer className="border-t border-line px-2.5 py-1.5 text-[11px] text-ink-2">{footer}</footer> : null}
    </section>
  );
}

const Quiet = ({ children }: { children: ReactNode }) => <p className="pt-4 text-center text-[11px] text-muted-foreground">{children}</p>;

/* ------------------------------------------------------------------ node bodies */

function Waveform({ live }: { live: boolean }) {
  return (
    <span aria-hidden className="flex h-5 items-center gap-[2px]">
      {[0, 2, 1, 3, 1, 2, 0, 3, 1, 2, 0, 3].map((d, i) => (
        <span key={i} className={cn("h-full w-[2px] origin-center rounded-full", live ? "animate-wave bg-agent" : "scale-y-[0.2] bg-line-strong")} style={live ? { animationDelay: `${d * 110 + i * 35}ms` } : undefined} />
      ))}
    </span>
  );
}

function SourceNode({ s, scene, state }: { s: (typeof SOURCES)[number]; scene: Scene; state: NodeState }) {
  const Icon = s.icon;
  const used = scene.channel === s.channel;
  const st: NodeState = used ? (scene.callActive ? "active" : state === "idle" ? "idle" : "done") : "idle";
  const b = BOX[`src-${s.channel}` as NodeId];
  return (
    <section
      aria-label={s.name}
      data-state={st}
      style={{ left: b.x, top: b.y, width: b.w, height: b.h }}
      className={cn(
        "absolute flex flex-col justify-between rounded-md border bg-panel p-2.5 transition-[border-color,box-shadow,opacity] duration-300",
        st === "active" ? "border-agent shadow-[0_0_0_3px_color-mix(in_srgb,var(--agent)_16%,transparent)]" : used ? "border-line-strong" : "border-line opacity-80",
      )}
    >
      <div className="flex items-center gap-2">
        <span className={cn("grid size-6 place-items-center rounded-[5px] border", used ? "border-agent text-agent" : "border-line text-muted-foreground")}>
          <Icon aria-hidden className="size-3.5" />
        </span>
        <span className="min-w-0">
          <span className="block truncate text-[12px] font-medium text-ink">{s.name}</span>
          <span className="block text-[10px] text-muted-foreground">{s.sub}</span>
        </span>
      </div>
      <p className="flex items-center gap-1.5 text-[10px] text-muted-foreground">
        <span aria-hidden className={cn("size-1.5 rounded-full", used && st !== "idle" ? "bg-agent" : "border border-line-strong")} />
        {used && st !== "idle" ? (scene.callActive ? "Call in progress" : "Call received") : "Not connected"}
      </p>
    </section>
  );
}

function SttBody({ script, scene }: { script: DemoScript; scene: Scene }) {
  const lines = script.call.slice(0, scene.callLines);
  const shown = lines.slice(-4);
  return (
    <div className="flex h-full flex-col gap-2">
      <div className="flex items-center gap-2">
        <Waveform live={scene.callActive} />
        <span className="text-[10px] text-muted-foreground">{scene.callActive ? "Transcribing" : lines.length ? "Transcript ready" : "Waiting for a call"}</span>
      </div>
      <ul aria-label="Call transcript" aria-live="polite" className="flex-1 space-y-1.5 overflow-hidden">
        {shown.map((l, i) =>
          l.speaker === "system" ? (
            <li key={`${lines.length - shown.length + i}`} className="animate-arrive text-center text-[10px] text-muted-foreground">
              {l.text}
            </li>
          ) : (
            <li key={`${lines.length - shown.length + i}`} className={cn("animate-arrive rounded-[5px] px-1.5 py-1 text-[11px] leading-snug", l.speaker === "caller" ? "bg-hover text-ink" : "border border-line text-ink-2")}>
              <span className="mb-0.5 block text-[9px] uppercase tracking-wider text-muted-foreground">{l.speaker === "caller" ? "Caller" : "Relay"}</span>
              {l.text}
            </li>
          ),
        )}
      </ul>
    </div>
  );
}

function GateBody({ scene }: { scene: Scene }) {
  const e = scene.emergency;
  const Icon = e === "tripped" ? ShieldAlert : ShieldCheck;
  return (
    <div className="flex h-full flex-col items-center gap-2 pt-1 text-center">
      <span
        className={cn(
          "grid size-9 place-items-center rounded-full border",
          e === "tripped" ? "border-promise-lapsed bg-promise-lapsed/10 text-promise-lapsed" : e === "clear" ? "border-promise-kept bg-promise-kept/10 text-promise-kept" : e === "checking" ? "animate-pulse border-agent text-agent" : "border-line-strong text-muted-foreground",
        )}
      >
        <Icon aria-hidden className="size-4" />
      </span>
      <p className={cn("text-[11px] font-medium", e === "tripped" ? "text-promise-lapsed" : e === "clear" ? "text-promise-kept" : "text-ink")} role="status">
        {e === "idle" ? "Waiting" : e === "checking" ? "Checking…" : e === "clear" ? "Clear" : "Tripped"}
      </p>
      <p className="text-[10px] leading-tight text-muted-foreground">Code-owned. Runs before any model.</p>
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
          <div key={w} className="h-5 animate-shimmer rounded-[4px] bg-hover" style={{ width: `${w}%` }} />
        ))}
      </div>
    );
  if (!t) return <Quiet>Waiting for the transcript</Quiet>;
  return (
    <div className="space-y-3">
      <div>
        <p className="label !text-[9.5px]">Needs found</p>
        <ul className="mt-1.5 space-y-1">
          {t.needs.map((n, i) => (
            <li key={n} style={{ animationDelay: `${i * 140}ms` }} className="flex animate-arrive items-center gap-2 rounded-[5px] border border-agent/40 bg-agent-soft px-2 py-1 text-[12px] font-medium text-agent [animation-fill-mode:backwards]">
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
      <dl className="space-y-1.5 text-[11px]">
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
        <p role="alert" className="animate-arrive rounded-[5px] border border-promise-lapsed/40 bg-promise-lapsed/8 px-2 py-1.5 text-[11px] font-medium text-ink">
          <ShieldAlert aria-hidden className="mr-1 inline size-3 -translate-y-px text-promise-lapsed" />
          {scene.alert}
        </p>
      ) : null}
      <ul className="flex-1 space-y-1 overflow-hidden" aria-label="Requests from this call">
        {mine.map((r) => (
          <li key={r.id} className="flex animate-arrive items-center gap-2 rounded-[5px] border border-line px-2 py-1.5">
            <StatusGlyph status={r.status} />
            <span className="min-w-0 flex-1">
              <span className="block truncate text-[11.5px] font-medium text-ink">{categoryLabel(r.category)}</span>
              <span className="block truncate text-[10px] text-muted-foreground">{r.organization_id && board ? shortOrg(orgName(board, r.organization_id)) : "Unclaimed"}</span>
            </span>
          </li>
        ))}
        {!mine.length ? <li className="pt-3 text-center text-[11px] text-muted-foreground">Requests from the call appear here</li> : null}
      </ul>
    </div>
  );
}

const PHASE: Record<string, string> = { idle: "", tagging: "Suggested", claimed: "Claimed", delivered: "Delivered" };

function OrgsBody({ board, scene }: { board: Board | null; scene: Scene }) {
  return (
    <ul className="space-y-2" aria-label="Volunteer organizations">
      {(board?.organizations ?? []).map((o) => {
        const st = scene.orgs[o.id];
        const active = st && st.phase !== "idle";
        return (
          <li key={o.id} className={cn("rounded-[5px] border px-2 py-1.5 transition-colors", active ? "border-agent/50 bg-agent-soft" : "border-line")}>
            <div className="flex items-center gap-2">
              <Monogram name={o.name} active={Boolean(active)} />
              <span className="min-w-0 flex-1 truncate text-[11.5px] font-medium text-ink">{shortOrg(o.name)}</span>
              <span className="flex shrink-0 gap-1 text-muted-foreground">
                {o.capabilities.map((c) => (
                  <CategoryIcon key={c} category={c} className={cn("size-3", st?.phase === "tagging" && st.category === c && "text-agent")} />
                ))}
              </span>
            </div>
            {active ? (
              <p key={st.phase} className="mt-1 flex animate-arrive items-center gap-1 pl-[26px] text-[10.5px] font-medium text-agent">
                {st.phase !== "tagging" ? <Check aria-hidden className="size-3" /> : null}
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
      <ul aria-label="Voice agents" className="space-y-1">
        {scene.helpers.map((h) => (
          <li key={h.id} className="flex items-start gap-1.5">
            <span aria-hidden className={cn("mt-[5px] size-1.5 shrink-0 rounded-full", h.status === "working" ? "animate-pulse bg-agent" : "bg-line-strong")} />
            <span className="min-w-0 flex-1 leading-tight">
              <span className={cn("block text-[11.5px] font-medium", h.status === "working" ? "text-ink" : "text-ink-2")}>
                {h.role}
                <span className="sr-only"> {h.status}</span>
              </span>
              <span className="block truncate text-[10px] text-muted-foreground">{h.lastAction}</span>
            </span>
            <span className="mt-0.5 shrink-0 font-mono text-[9px] text-muted-foreground">{h.sandbox.replace("sbx-", "")}</span>
          </li>
        ))}
      </ul>
      <div className="mt-auto space-y-1 border-t border-line pt-2">
        <p className="label !text-[9.5px]">Follow-up call</p>
        <ul aria-label="Follow-up call transcript" aria-live="polite" className="max-h-[92px] space-y-1 overflow-hidden">
          {lines.slice(-3).map((l, i) => (
            <li key={`${lines.length}-${i}`} className={cn("animate-arrive line-clamp-2 rounded-[4px] px-1.5 py-1 text-[10.5px] leading-snug", l.speaker === "caller" ? "bg-hover text-ink" : "border border-line text-ink-2")}>
              {l.text}
            </li>
          ))}
          {!lines.length ? <li className="text-[10.5px] text-muted-foreground">No call yet</li> : null}
        </ul>
        {scene.followOutcome ? (
          <p className="animate-arrive text-[11px] font-medium text-promise-lapsed">Household: did not arrive</p>
        ) : null}
      </div>
    </div>
  );
}

function HumanBody({ scene }: { scene: Scene }) {
  const text = scene.humanReview ? "Reviewing the re-delivery" : scene.alert ? scene.alert : "Standing by. A person decides, never the model.";
  return (
    <div className="flex h-full items-start gap-2">
      <UserCheck aria-hidden className={cn("mt-0.5 size-4 shrink-0", scene.alert || scene.humanReview ? "text-promise-lapsed" : "text-muted-foreground")} />
      <p className={cn("text-[11.5px] leading-snug", scene.alert || scene.humanReview ? "font-medium text-ink" : "text-muted-foreground")}>{text}</p>
    </div>
  );
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
      : [];
  return (
    <div className="space-y-1.5">
      {l ? (
        <p className="animate-arrive text-[11px] leading-snug text-ink">
          <Check aria-hidden className="mr-1 inline size-3 -translate-y-px text-promise-kept" />
          {l.recommendation}
        </p>
      ) : (
        <p className="text-[11px] text-muted-foreground">Drafted from a verified outcome, then approved by a person.</p>
      )}
      {without && withH ? (
        <ul className="animate-arrive space-y-0.5 border-t border-line pt-1.5 text-[10.5px]" aria-label="Measured with versus without history">
          {deltas.length ? (
            deltas.map((d) => (
              <li key={d.metric} className="flex justify-between gap-2">
                <span className="text-ink-2">{METRIC_SHORT[d.metric].label}</span>
                <span className="num font-medium text-ink">{d.without === null ? "n/a" : `${Math.round(d.without * 100)}%`} → {d.withHistory === null ? "n/a" : `${Math.round(d.withHistory * 100)}%`}</span>
              </li>
            ))
          ) : (
            <li className="text-muted-foreground">No metric changed</li>
          )}
          <li className="pt-0.5 text-[9.5px] text-muted-foreground">Synthetic · {scene.compare?.case_count ?? "?"} cases</li>
        </ul>
      ) : null}
    </div>
  );
}

/* ------------------------------------------------------------------ edges */

function Edges({ script, scene, view }: { script: DemoScript; scene: Scene; view: ReturnType<typeof useRunView> }) {
  return (
    <svg aria-hidden width={W} height={H} viewBox={`0 0 ${W} ${H}`} className="pointer-events-none absolute inset-0">
      <defs>
        {(
          [
            ["idle", "var(--line-strong)"],
            ["flow", "var(--agent)"],
            ["alert", "var(--promise-lapsed)"],
          ] as const
        ).map(([k, c]) => (
          <marker key={k} id={`arrow-${k}`} viewBox="0 0 8 8" refX="6.5" refY="4" markerWidth="7" markerHeight="7" orient="auto">
            <path d="M1 1l5.5 3L1 7" fill="none" stroke={c} strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round" />
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
        const color = state === "idle" ? "var(--line-strong)" : kind === "alert" ? "var(--promise-lapsed)" : "var(--agent)";
        const marker = state === "idle" ? "idle" : kind === "alert" ? "alert" : "flow";
        const d = rounded(e.points);
        return (
          <g key={e.id} data-edge={e.id} data-state={state}>
            <path
              d={d}
              fill="none"
              stroke={color}
              strokeWidth={state === "idle" ? 1.25 : 1.6}
              strokeOpacity={state === "done" ? 0.75 : 1}
              strokeDasharray={kind === "feedback" ? "5 4" : undefined}
              markerEnd={`url(#arrow-${marker})`}
              className="transition-[stroke] duration-300"
            />
            {state === "active" ? <path d={d} fill="none" stroke={color} strokeWidth="3.5" strokeLinecap="round" strokeDasharray="0.1 14" className="flow-dots" /> : null}
            {e.label && e.labelAt && state !== "idle" ? (
              <text x={e.labelAt[0]} y={e.labelAt[1]} fontSize="10" textAnchor={e.anchor ?? "middle"} className="animate-fade fill-ink-2" stroke="var(--bg)" strokeWidth="4" paintOrder="stroke" strokeLinejoin="round">
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

const subscribeNarrow = (cb: () => void) => {
  const mq = window.matchMedia("(max-width: 767px)");
  mq.addEventListener("change", cb);
  return () => mq.removeEventListener("change", cb);
};
const useNarrow = () => useSyncExternalStore(subscribeNarrow, () => window.matchMedia("(max-width: 767px)").matches, () => false);

export function FlowGraph({ script, scene, state, board }: { script: DemoScript; scene: Scene; state: RunnerState; board: Board | null }) {
  const view = useRunView(script, state);
  const narrow = useNarrow();
  const wrap = useRef<HTMLDivElement>(null);
  const [scale, setScale] = useState(1);

  useLayoutEffect(() => {
    const el = wrap.current;
    if (!el) return;
    const fit = () => setScale(Math.min(1, el.clientWidth / W));
    fit();
    const ro = new ResizeObserver(fit);
    ro.observe(el);
    return () => ro.disconnect();
  }, [narrow]);

  const tripped = scene.emergency === "tripped";
  const humanState: NodeState = scene.humanReview || scene.alert || tripped ? "alert" : view.stateOfNode("human");
  const nodes = {
    stt: (flow = true) => (
      <NodeBox key="stt" flow={flow} id="stt" kicker="Transcribe" title="ElevenLabs speech-to-text" tag="sample" state={view.stateOfNode("stt")}>
        <SttBody script={script} scene={scene} />
      </NodeBox>
    ),
    gate: (flow = true) => (
      <NodeBox key="gate" flow={flow} id="gate" kicker="Safety" title="Emergency check" state={tripped ? "alert" : view.stateOfNode("gate")}>
        <GateBody scene={scene} />
      </NodeBox>
    ),
    triage: (flow = true) => (
      <NodeBox key="triage" flow={flow} id="triage" kicker="Understand" title="AI triage" tag="Groq · sample" state={scene.triageSkipped ? "skipped" : view.stateOfNode("triage")} footer={<span className="flex items-center gap-1.5"><UserCheck aria-hidden className="size-3 text-agent" /> A person decides</span>}>
        <TriageBody scene={scene} />
      </NodeBox>
    ),
    hub: (flow = true) => (
      <NodeBox key="hub" flow={flow} id="hub" kicker="Coordinate" title="Triage dashboard" state={view.stateOfNode("hub")}>
        <HubBody board={board} scene={scene} />
      </NodeBox>
    ),
    orgs: (flow = true) => (
      <NodeBox key="orgs" flow={flow} id="orgs" kicker="Volunteers" title="Organizations" state={view.stateOfNode("orgs")}>
        <OrgsBody board={board} scene={scene} />
      </NodeBox>
    ),
    voice: (flow = true) => (
      <NodeBox key="voice" flow={flow} id="voice" kicker="Verify" title="Voice agent org" tag="ElevenLabs · Daytona · sample" state={view.stateOfNode("voice")}>
        <VoiceBody script={script} scene={scene} />
      </NodeBox>
    ),
    human: (flow = true) => (
      <NodeBox key="human" flow={flow} id="human" kicker="Human in the loop" title="Coordinator" state={humanState}>
        <HumanBody scene={scene} />
      </NodeBox>
    ),
    lesson: (flow = true) => (
      <NodeBox key="lesson" flow={flow} id="lesson" kicker="Learn" title="Reviewed lesson" state={view.stateOfNode("lesson")}>
        <LessonBody scene={scene} />
      </NodeBox>
    ),
  };

  if (narrow) {
    // Small screens: the same nodes as a vertical sequence. The geometry above is for the wide canvas only.
    return (
      <ol aria-label="Relay flow" className="space-y-2">
        {SOURCES.filter((s) => s.channel === scene.channel || (!scene.channel && s.channel === "phone")).map((s) => (
          <li key={s.channel}>
            <p className="label mb-1">Input · sample adapter</p>
            <p className="rounded-md border border-line bg-panel px-3 py-2 text-xs text-ink">{s.name}</p>
          </li>
        ))}
        {(["stt", "gate", "triage", "hub", "orgs", "voice", "human", "lesson"] as const).map((k) => (
          <li key={k} className="h-auto [&_section]:!h-auto">
            {nodes[k](false)}
          </li>
        ))}
      </ol>
    );
  }

  return (
    <div ref={wrap} className="w-full overflow-hidden" style={{ height: H * scale }}>
      <div role="group" aria-label="Relay flow: calls to triage to dashboard to organizations and voice agents" className="relative origin-top-left" style={{ width: W, height: H, transform: `scale(${scale})` }}>
        <p className="label absolute left-0 top-[6px]">Inputs · plug-in adapters</p>
        <p className="absolute left-0 top-[410px] w-[150px] text-[10px] leading-snug text-muted-foreground">Sample adapters. No live emergency feed is connected.</p>
        <Edges script={script} scene={scene} view={view} />
        {SOURCES.map((s) => (
          <SourceNode key={s.channel} s={s} scene={scene} state={view.stateOfStep("call") === "off" ? "idle" : view.stateOfStep("call") === "active" ? "active" : view.stateOfStep("call") === "done" ? "done" : "idle"} />
        ))}
        {(Object.keys(nodes) as (keyof typeof nodes)[]).map((k) => nodes[k]())}
      </div>
    </div>
  );
}
