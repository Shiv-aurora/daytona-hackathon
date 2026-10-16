"use client";

import { useEffect, useRef, useState } from "react";
import type { SystemEvent } from "@/lib/contracts";
import { fmtShort } from "@/lib/sim";
import { STAGES, TRACE_KIND, describe, stageOf, tokenSeries, traceKind, traceLabel, type TraceKind } from "@/lib/view";
import { cn } from "@/lib/utils";
import { Tag, type Tone } from "./bits";

const nf = new Intl.NumberFormat("en-US");
const KIND_TONE: Record<TraceKind, Tone> = {
  tick: "neutral",
  matched: "neutral",
  promise: "blue",
  proposal: "teal",
  silence: "amber",
  cross: "violet",
  call: "neutral",
  emergency: "red",
  policy: "teal",
  goal: "teal",
  decision: "green",
  model: "neutral",
};

const CONTEXT_MAX = 16_000;
const k = (v: number) => (v >= 1000 ? `${Math.round(v / 1000)}k` : String(v));

/** One of a matched pair of sparklines: same size, own y-axis (fixed when `max` is given). */
function Spark({ label, value, values, max, tone = "ink", note }: { label: string; value: number; values: number[]; max?: number; tone?: "ink" | "agent"; note: string }) {
  const w = 200;
  const h = 40;
  const top = max ?? Math.max(1, ...values);
  const pts = values.map((v, i) => `${values.length > 1 ? (i / (values.length - 1)) * w : 0},${h - (Math.min(v, top) / top) * h}`).join(" ");
  const stroke = tone === "agent" ? "var(--agent)" : "var(--text)";
  return (
    <figure role="group" aria-label={`${label}: ${nf.format(value)} tokens. ${note}`} className="flex w-64 flex-col justify-center" title={note}>
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="text-sm text-muted-foreground">{label}</span>
        <span className={cn("font-mono text-lg font-semibold tabular-nums", tone === "agent" && "text-agent")}>{nf.format(value)}</span>
      </figcaption>
      <div className="relative mt-1 h-10">
        {values.length < 2 ? (
          <p className="pt-2 text-sm text-muted-foreground">No model calls yet</p>
        ) : (
          <svg viewBox={`0 0 ${w} ${h}`} className="size-full overflow-visible" aria-hidden preserveAspectRatio="none">
            <line x1="0" x2={w} y1={h} y2={h} stroke="var(--border)" vectorEffect="non-scaling-stroke" />
            <polyline points={pts} fill="none" stroke={stroke} strokeWidth="2" vectorEffect="non-scaling-stroke" />
          </svg>
        )}
        {max !== undefined && (
          <span aria-hidden className="absolute -top-1 right-0 font-mono text-[10px] leading-none text-muted-foreground">
            {k(max)}
          </span>
        )}
      </div>
    </figure>
  );
}

export function TraceStrip({ trace, day0, now, names = {}, policyVersion = 1 }: {
  trace: SystemEvent[];
  day0: string;
  now: number;
  names?: Record<string, string>;
  /** Latest policy version; when it rises the "policy adjusted" chip pulses once. */
  policyVersion?: number;
}) {
  const seen = useRef(policyVersion);
  const [flash, setFlash] = useState(0);
  useEffect(() => {
    if (policyVersion > seen.current) setFlash((f) => f + 1);
    seen.current = policyVersion;
  }, [policyVersion]);
  useEffect(() => {
    if (!flash) return;
    const id = setTimeout(() => setFlash(0), 1500);
    return () => clearTimeout(id);
  }, [flash]);
  // Chronological in simulated time; ticks are hidden to keep the strip readable in a demo.
  const steps = trace.filter((s) => s.ts <= now).sort((a, b) => a.ts - b.ts);
  // Model calls are summarised by the token counters, so the list keeps to decisions and facts.
  const meaningful = steps.filter((s) => traceKind(s) !== "tick");
  const shown = meaningful.filter((s) => traceKind(s) !== "model").slice(-8);
  const last = shown.at(-1);
  const latest = meaningful.at(-1);
  const tokens = tokenSeries(steps);

  return (
    <section aria-labelledby="trace-title" className="grid shrink-0 grid-cols-1 gap-4 border-t bg-surface px-5 py-2 lg:h-32 lg:grid-cols-[1fr_auto_auto] lg:gap-8">
      <div className="flex min-h-0 flex-col">
        <div className="flex flex-wrap items-center gap-1">
          <h2 id="trace-title" className="mr-2 text-sm font-semibold">
            Relay now
          </h2>
          {STAGES.map(([key, label], i) => {
            const active = latest && stageOf(latest) === key;
            const flashing = key === "policy" && flash > 0;
            return (
              <span key={key} className="flex items-center gap-1">
                <span
                  key={flashing ? `flash-${flash}` : key}
                  className={cn(
                    "rounded-full px-2 py-0.5 text-sm",
                    active ? "bg-agent text-primary-foreground" : "bg-muted text-muted-foreground",
                    flashing && "bg-agent/15 text-agent ring-2 ring-agent motion-safe:animate-pulse-once",
                  )}
                >
                  {active && <span aria-hidden>▶ </span>}
                  {label}
                  {active && <span className="sr-only"> (latest step)</span>}
                </span>
                {i < STAGES.length - 1 && <span aria-hidden className="text-line">›</span>}
              </span>
            );
          })}
        </div>
        {last ? (
          <p className="mt-2 flex items-center gap-2 text-base" aria-live="polite">
            <Tag tone={KIND_TONE[traceKind(last)]} glyph={TRACE_KIND[traceKind(last)].glyph}>
              {TRACE_KIND[traceKind(last)].label}
            </Tag>
            <span className="font-medium">{traceLabel(last)}</span>
            {(last as { household_id?: string }).household_id && (
              <span className="text-muted-foreground">{names[(last as { household_id?: string }).household_id!] ?? ""}</span>
            )}
          </p>
        ) : (
          <p className="mt-2 text-base text-muted-foreground">Nothing yet in this run.</p>
        )}
        <details className="mt-1 min-h-0">
          <summary className="cursor-pointer text-sm text-muted-foreground">History</summary>
          <ol className="mt-1 max-h-28 overflow-y-auto text-sm leading-7" aria-label="Latest agent steps">
          {shown.map((s, i) => {
            const kind = traceKind(s);
            const k = TRACE_KIND[kind];
            const hid = (s as { household_id?: string }).household_id;
            return (
              <li key={`${s._id ?? i}`} className="flex items-center gap-2 whitespace-nowrap" data-kind={kind}>
                <span className="w-20 shrink-0 text-muted-foreground">{fmtShort(day0, s.ts)}</span>
                <Tag tone={KIND_TONE[kind]} glyph={k.glyph} className="w-28 justify-start">
                  {k.label}
                </Tag>
                <span className="font-medium">{traceLabel(s)}</span>
                {hid && <span className="text-muted-foreground">{names[hid] ?? hid}</span>}
                <span className="truncate text-muted-foreground" title={describe(s)}>
                  {kind === "policy" ? describe(s) : ""}
                </span>
              </li>
            );
          })}
          </ol>
        </details>
      </div>
      <Spark label="Total tokens processed" value={tokens.at(-1)?.total ?? 0} values={tokens.map((t) => t.total)} note="Every record read so far. Climbs with the run." />
      <Spark
        label="Context per call"
        value={tokens.at(-1)?.context ?? 0}
        values={tokens.map((t) => t.context)}
        max={CONTEXT_MAX}
        tone="agent"
        note="Prompt size per model call, on a fixed 0-16k axis. Stays flat because memory lives in recorded snapshots, not the prompt."
      />
    </section>
  );
}
