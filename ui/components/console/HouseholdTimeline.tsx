"use client";

import { useState } from "react";
import Link from "next/link";
import { Languages, NotebookPen, PhoneCall, PhoneOff } from "lucide-react";
import type { Event, Household, RegistryEntry, RelayPromise } from "@/lib/contracts";
import { SCENARIO_HOURS, fmtClock, fmtShort } from "@/lib/sim";
import { cn } from "@/lib/utils";
import type { callsOf } from "@/lib/view";
import { LANGUAGE, OUTCOME, PROMISE, PromiseBadge, SOURCE, SOURCE_ICON, Tag, type PromiseView, type Tone } from "./bits";

const x = (ts: number) => `${(Math.min(Math.max(ts, 0), SCENARIO_HOURS) / SCENARIO_HOURS) * 100}%`;
// Call outcomes on the timeline: missed calls amber, answered green, emergencies red (icon differs too).
const TONE_MARK: Partial<Record<Tone, string>> = {
  amber: "border-promise-due-soon bg-promise-due-soon/10 text-promise-due-soon",
  green: "border-promise-kept text-promise-kept",
  red: "border-promise-lapsed bg-promise-lapsed/10 text-promise-lapsed",
};
const LANES: { label: string; sources: string[] }[] = [
  { label: "Visits", sources: ["visit_note"] },
  { label: "Calls", sources: ["call", "call_result"] },
  { label: "Outage & services", sources: ["utility", "crew", "311"] },
];

/** Contract statuses are open/kept/lapsed; "due soon" is a view of an open promise within 24h of due. */
export function promiseView(p: RelayPromise, now: number): PromiseView {
  if (p.status !== "open") return p.status;
  return p.due_ts - now <= 24 ? "due_soon" : "open";
}

function Row({ label, tall = false, children }: { label: React.ReactNode; tall?: boolean; children?: React.ReactNode }) {
  return (
    <div className="grid grid-cols-[9rem_1fr] items-center gap-2">
      <div className="truncate text-sm text-muted-foreground">{label}</div>
      <div className={cn("relative border-b border-dashed", tall ? "h-11" : "h-8")}>{children}</div>
    </div>
  );
}

/** Dashed while open; solid with ✓ or ✕ once kept or lapsed. The full promise sits on the bar. */
function PromiseSegment({ p, now, day0 }: { p: RelayPromise; now: number; day0: string }) {
  const v = promiseView(p, now);
  const settled = p.status !== "open";
  const end = settled ? (p.status_ts ?? p.due_ts) : p.due_ts;
  const s = PROMISE[v];
  return (
    <>
      <span aria-hidden className={`absolute top-0 text-sm font-medium whitespace-nowrap ${s.text}`} style={{ left: x(p.made_ts) }}>
        {p.text}
      </span>
      <div
        aria-hidden
        className={`absolute bottom-1.5 border-t-2 border-current ${settled ? "border-solid" : "border-dashed"} ${s.text}`}
        style={{ left: x(p.made_ts), width: `calc(${x(end)} - ${x(p.made_ts)})` }}
      />
      <span
        role="img"
        aria-label={`${p.text}. ${s.label}, due ${fmtClock(day0, p.due_ts)}`}
        title={`${p.text} (${s.label})`}
        className={`absolute bottom-1.5 -translate-x-1/2 translate-y-1/2 rounded-full bg-surface px-0.5 text-sm font-bold leading-none ${s.text}`}
        style={{ left: x(end) }}
      >
        {s.glyph}
      </span>
    </>
  );
}

export function HouseholdTimeline({ household: h, events, promises, registry, calls, citedIds, runId, day0, now, nameShown = false }: {
  household: Household;
  events: Event[];
  promises: RelayPromise[];
  registry: RegistryEntry | undefined;
  calls: ReturnType<typeof callsOf>;
  citedIds: string[];
  runId: string;
  day0: string;
  now: number;
  /** The decision panel above already shows the name; keep it for screen readers only. */
  nameShown?: boolean;
}) {
  const [open, setOpen] = useState<string | null>(null);
  const optedIn = registry?.opt_in === true;
  const lang = h.language ?? registry?.language;
  return (
    <section aria-labelledby="hh-title" className="flex min-h-0 flex-col overflow-y-auto rounded-lg border bg-surface">
      <header className="border-b px-4 py-3">
        <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
          <h2 id="hh-title" className={nameShown ? "sr-only" : "text-xl font-semibold"}>
            {h.name ?? h.household_id}
          </h2>
          <span className="text-base text-muted-foreground">{h.address ?? "Address unknown"}</span>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          {lang && (
            <Tag icon={Languages}>
              <span lang={lang}>{LANGUAGE[lang] ?? lang}</span>
            </Tag>
          )}
          {optedIn ? (
            <Tag tone="green" icon={PhoneCall}>
              Calls OK
            </Tag>
          ) : (
            <Tag icon={PhoneOff}>No calls</Tag>
          )}
          {calls.length > 0 && (
            <ul className="contents" aria-label="Calls">
              {calls.map(({ request, result }) => {
                const o = OUTCOME[result?.outcome ?? "queued"];
                return (
                  <li key={request._id}>
                    <Link href={`/call/${encodeURIComponent(request._id)}?run=${encodeURIComponent(runId)}`} className="rounded-md focus-visible:outline-2">
                      <Tag tone={o.tone} icon={o.icon} className="underline-offset-2 hover:underline">
                        {fmtShort(day0, result?.ts ?? request.requested_ts).split(" ").slice(0, 2).join(" ")} {o.label.toLowerCase()}
                      </Tag>
                    </Link>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      </header>

      <div className="space-y-1 px-4 py-3">
        <div className="grid grid-cols-[9rem_1fr] gap-2 text-sm text-muted-foreground" aria-hidden>
          <span>Six weeks</span>
          <div className="relative h-4">
            {[0, 7, 14, 21, 28, 35].map((d) => (
              <span key={d} className="absolute" style={{ left: x(d * 24) }}>
                Week {d / 7 + 1}
              </span>
            ))}
          </div>
        </div>
        <div className="relative">
          <div aria-hidden className="pointer-events-none absolute inset-y-0 left-[9.5rem] right-0">
            {/* Future weeks are empty on purpose: nothing has happened there yet. */}
            <div className="absolute inset-y-0 right-0 bg-[repeating-linear-gradient(135deg,transparent_0_7px,var(--border)_7px_8px)] bg-bg/70" style={{ left: x(now) }} />
            <div className="absolute inset-y-0 w-0.5 bg-agent" style={{ left: x(now) }}>
              <span className="absolute -bottom-5 -translate-x-1/2 text-sm font-semibold text-agent">now</span>
            </div>
          </div>
          {LANES.map((lane) => (
            <Row key={lane.label} label={lane.label}>
              {events
                .filter((e) => lane.sources.includes(e.source))
                .map((e) => {
                  const outcome = (e as { outcome?: string }).outcome;
                  const o = outcome ? OUTCOME[outcome] : undefined;
                  const Icon = o?.icon || SOURCE_ICON[e.source] || NotebookPen;
                  const label = `${SOURCE[e.source]?.label ?? e.source}, ${fmtClock(day0, e.ts)}: ${e.text}`;
                  return (
                    <button
                      key={e._id}
                      aria-label={label}
                      title={label}
                      onClick={() => setOpen(e._id)}
                      style={{ left: x(e.ts) }}
                      className={cn(
                        "absolute top-1/2 -translate-x-1/2 -translate-y-1/2 rounded-full border bg-surface p-1 hover:border-agent",
                        o && o.tone !== "neutral" && TONE_MARK[o.tone],
                      )}
                    >
                      <Icon aria-hidden className="size-4" />
                    </button>
                  );
                })}
            </Row>
          ))}
          {promises.map((p) => (
            <Row key={p._id} tall label={<PromiseBadge status={promiseView(p, now)} />}>
              <PromiseSegment p={p} now={now} day0={day0} />
            </Row>
          ))}
        </div>
      </div>

      <details className="border-t px-4 py-2">
        <summary className="cursor-pointer text-base font-semibold">Records ({events.length})</summary>
        <ol className="mt-1 divide-y">
          {[...events].reverse().map((e) => {
            const cited = citedIds.includes(e._id);
            const text = e.text || OUTCOME[(e as { outcome?: string }).outcome ?? ""]?.label || "No text";
            const s = SOURCE[e.source];
            return (
              <li key={e._id}>
                <button onClick={() => setOpen(open === e._id ? null : e._id)} aria-expanded={open === e._id} className="flex w-full items-start gap-2 py-1.5 text-left">
                  <span className="w-16 shrink-0 pt-0.5 text-sm text-muted-foreground">{fmtShort(day0, e.ts).split(" ").slice(0, 2).join(" ")}</span>
                  <Tag icon={s?.icon}>{s?.label ?? e.source}</Tag>
                  <span className={cn("min-w-0 flex-1 text-base", open === e._id ? "" : "line-clamp-1")}>{text}</span>
                  {cited && (
                    <Tag tone="teal" className="ml-1">
                      Cited
                    </Tag>
                  )}
                  {(e as { origin?: string }).origin === "real" && (
                    <Tag tone="blue" className="ml-1" title="Real NYC Open Data 311 request from Ida (2021)">
                      Real 311
                    </Tag>
                  )}
                </button>
              </li>
            );
          })}
        </ol>
      </details>
    </section>
  );
}
