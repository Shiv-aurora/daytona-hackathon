"use client";

// Hand-drawn SVG/HTML charts. No chart library: each mark is specified here so the visual language stays consistent
// (hairline axes, one teal, five lifecycle colours) and so charts stay tiny, accessible and SSR-safe.
import { useId } from "react";
import { cn } from "@/lib/utils";
import { STATUSES, STATUS_META, categoryLabel } from "@/lib/relay/selectors";
import type { RequestStatus } from "@/lib/relay/types";
import { journey, type CategoryRow, type Funnel, type NodeState, type StatusCounts } from "@/lib/relay/viz";
import type { RelayRequest } from "@/lib/relay/types";

/* ------------------------------------------------------------------ proportion bar */

export interface Segment {
  key: string;
  value: number;
  color: string;
  label: string;
}

/** A single horizontal bar split into proportional segments. The workhorse micro-chart. */
export function ProportionBar({ segments, height = 6, className, label }: { segments: Segment[]; height?: number; className?: string; label?: string }) {
  const total = segments.reduce((n, s) => n + s.value, 0);
  const summary = label ?? segments.filter((s) => s.value).map((s) => `${s.value} ${s.label}`).join(", ");
  return (
    <div role="img" aria-label={summary || "No data"} className={cn("flex w-full gap-px overflow-hidden rounded-full bg-hover", className)} style={{ height }}>
      {total === 0
        ? null
        : segments
            .filter((s) => s.value > 0)
            .map((s) => (
              <span key={s.key} title={`${s.label}: ${s.value}`} className="h-full origin-left animate-grow first:rounded-l-full last:rounded-r-full" style={{ width: `${(s.value / total) * 100}%`, background: s.color }} />
            ))}
    </div>
  );
}

export function statusSegments(counts: StatusCounts): Segment[] {
  return STATUSES.map((s) => ({ key: s, value: counts[s], color: STATUS_META[s].color, label: STATUS_META[s].label }));
}

export function Legend({ items, className }: { items: { color: string; label: string; value?: number | string }[]; className?: string }) {
  return (
    <ul className={cn("flex flex-wrap gap-x-4 gap-y-1", className)}>
      {items.map((i) => (
        <li key={i.label} className="flex items-center gap-1.5 text-2xs text-muted-foreground">
          <span aria-hidden className="size-2 rounded-[2px]" style={{ background: i.color }} />
          {i.label}
          {i.value !== undefined ? <span className="num font-medium text-ink">{i.value}</span> : null}
        </li>
      ))}
    </ul>
  );
}

/* ------------------------------------------------------------------ lifecycle funnel (Sankey-lite) */

const DROP_LABEL: Record<string, string> = { reported: "unclaimed", claimed: "awaiting delivery", delivered: "unverified" };

const FW = 640;
const FH = 168;
const BAR_W = 8;
const TOP = 46;
const MAXH = 86;

/**
 * Reported → Claimed → Delivery reported → Receipt verified. Teal ribbons are requests that moved on; the amber
 * ribbon after "delivery reported" is the gap the product exists to close: delivered, but not yet confirmed received.
 */
export function FunnelChart({ funnel, className }: { funnel: Funnel; className?: string }) {
  const { stages, total } = funnel;
  const colX = (i: number) => 24 + i * ((FW - 48 - BAR_W) / (stages.length - 1));
  const h = (n: number) => (total ? (n / total) * MAXH : 0);
  const id = useId();
  const summary = stages.map((s) => `${s.count} ${s.label.toLowerCase()}`).join(", ");
  return (
    <svg role="img" aria-label={`Request funnel: ${summary}`} viewBox={`0 0 ${FW} ${FH}`} className={cn("block h-auto w-full", className)}>
      <defs>
        <pattern id={`${id}-hatch`} width="5" height="5" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">
          <rect width="5" height="5" fill="var(--promise-due-soon)" fillOpacity="0.12" />
          <line x1="0" y1="0" x2="0" y2="5" stroke="var(--promise-due-soon)" strokeOpacity="0.45" strokeWidth="1.2" />
        </pattern>
      </defs>
      {stages.slice(0, -1).map((s, i) => {
        const next = stages[i + 1];
        const x0 = colX(i) + BAR_W;
        const x1 = colX(i + 1);
        const mx = (x0 + x1) / 2;
        const keep = h(next.count);
        const drop = h(s.count) - keep;
        const ribbon = (y0: number, hh: number) =>
          `M${x0} ${y0} C${mx} ${y0} ${mx} ${y0} ${x1} ${y0} L${x1} ${y0 + hh} C${mx} ${y0 + hh} ${mx} ${y0 + hh} ${x0} ${y0 + hh} Z`;
        const keepY1 = TOP;
        const dropGap = i === stages.length - 2; // the delivery → verification gap is the interesting one
        return (
          <g key={s.id}>
            {keep > 0 ? <path d={ribbon(keepY1, keep)} fill="var(--agent)" fillOpacity="0.16" className="animate-fade" /> : null}
            {drop > 0 ? (
              <text x={(x0 + x1) / 2} y={TOP + keep + drop + 24} textAnchor="middle" fontSize="9.5" className="fill-muted-foreground">
                {s.count - next.count} {DROP_LABEL[s.id] ?? "not yet"}
              </text>
            ) : null}
            {drop > 0 ? (
              <path
                d={`M${x0} ${TOP + keep} C${mx} ${TOP + keep} ${mx} ${TOP + keep + 6} ${x1} ${TOP + keep + 6} L${x1} ${TOP + keep + 6 + drop} C${mx} ${TOP + keep + 6 + drop} ${mx} ${TOP + keep + drop} ${x0} ${TOP + keep + drop} Z`}
                fill={dropGap ? `url(#${id}-hatch)` : "var(--series-base)"}
                fillOpacity={dropGap ? 1 : 0.22}
                className="animate-fade"
              />
            ) : null}
          </g>
        );
      })}
      {stages.map((s, i) => {
        const x = colX(i);
        const last = i === stages.length - 1;
        const fill = last ? "var(--promise-kept)" : "var(--ink-2, var(--text))";
        return (
          <g key={s.id}>
            <rect x={x} y={TOP} width={BAR_W} height={Math.max(h(s.count), s.count ? 2 : 0)} rx="1.5" fill={fill} />
            {s.count === 0 ? <line x1={x} x2={x + BAR_W} y1={TOP} y2={TOP} stroke="var(--line-strong)" strokeWidth="1.5" /> : null}
            <text x={last ? x + BAR_W : x} textAnchor={last ? "end" : "start"} y={TOP - 26} className="fill-muted-foreground" fontSize="9.5" letterSpacing="0.06em" style={{ textTransform: "uppercase" }}>
              {s.label}
            </text>
            <text x={last ? x + BAR_W : x} textAnchor={last ? "end" : "start"} y={TOP - 8} className="num fill-ink" fontSize="19" fontWeight="500">
              {s.count}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------------ needs by category */

export function CategoryBars({ rows, className }: { rows: CategoryRow[]; className?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.total));
  if (!rows.length) return <p className="text-xs text-muted-foreground">No requests yet.</p>;
  return (
    <ul className={cn("space-y-2", className)}>
      {rows.map((r) => (
        <li key={r.category} className="grid grid-cols-[5.5rem_1fr_1.5rem] items-center gap-3 text-xs">
          <span className="truncate text-ink-2">{categoryLabel(r.category)}</span>
          <ProportionBar segments={statusSegments(r.counts)} height={8} className="rounded-[3px] [&>span]:rounded-none" label={`${categoryLabel(r.category)}: ${statusSummary(r.counts)}`} />
          <span className="num text-right text-ink" style={{ opacity: 0.5 + 0.5 * (r.total / max) }}>
            {r.total}
          </span>
        </li>
      ))}
    </ul>
  );
}

export function statusSummary(c: StatusCounts) {
  return STATUSES.filter((s) => c[s]).map((s) => `${c[s]} ${STATUS_META[s].label.toLowerCase()}`).join(", ") || "none";
}

/* ------------------------------------------------------------------ journey lane */

const NODE_COLOR: Record<NodeState, string> = {
  done: "var(--text)",
  current: "var(--promise-due-soon)",
  todo: "var(--line-strong)",
  bad: "var(--promise-lapsed)",
};

/**
 * Four nodes per request: requested → claimed → delivered → verified. Cheap enough to repeat on every row, so a
 * glance down the list shows where every request is stuck. The last node is the independent check.
 */
export function JourneyLane({ request, className, width = 92 }: { request: RelayRequest; className?: string; width?: number }) {
  const nodes = journey(request);
  const step = (width - 12) / 3;
  const label = nodes.map((n) => `${n.label}: ${n.state === "done" ? "done" : n.state === "bad" ? "failed" : n.state === "current" ? "in progress" : "pending"}`).join(", ");
  return (
    <svg role="img" aria-label={label} width={width} height={14} viewBox={`0 0 ${width} 14`} className={cn("shrink-0", className)}>
      {nodes.slice(0, -1).map((n, i) => (
        <line
          key={n.id}
          x1={6 + i * step}
          x2={6 + (i + 1) * step}
          y1={7}
          y2={7}
          stroke={nodes[i + 1].state === "todo" ? "var(--line-strong)" : "var(--text)"}
          strokeOpacity={nodes[i + 1].state === "todo" ? 1 : 0.55}
          strokeWidth="1.25"
          strokeDasharray={nodes[i + 1].state === "todo" ? "2 2" : undefined}
        />
      ))}
      {nodes.map((n, i) => {
        const cx = 6 + i * step;
        const c = n.state === "current" ? STATUS_META[request.status].color : NODE_COLOR[n.state];
        return n.state === "done" ? (
          <circle key={n.id} cx={cx} cy={7} r={4} fill={i === 3 ? "var(--promise-kept)" : c} />
        ) : n.state === "todo" ? (
          <circle key={n.id} cx={cx} cy={7} r={3.5} fill="var(--panel)" stroke={c} strokeWidth="1.25" />
        ) : (
          <g key={n.id}>
            <circle cx={cx} cy={7} r={5.5} fill="none" stroke={c} strokeOpacity="0.35" strokeWidth="1" />
            <circle cx={cx} cy={7} r={3.5} fill={c} />
          </g>
        );
      })}
    </svg>
  );
}

/* ------------------------------------------------------------------ status mini-counter */

/** The five lifecycle counts with a share bar. `row` is a compact strip; `list` is a labelled column for narrow panels. */
export function StatusTally({ counts, className, variant = "row" }: { counts: StatusCounts; className?: string; variant?: "row" | "list" }) {
  if (variant === "list") {
    return (
      <div className={cn("space-y-2", className)} aria-label="Request counts">
        <ProportionBar segments={statusSegments(counts)} height={6} />
        <ul className="space-y-0.5">
          {STATUSES.map((s: RequestStatus) => (
            <li key={s} title={STATUS_META[s].hint} className="flex items-center gap-2 text-[11px]">
              <span aria-hidden className="size-1.5 shrink-0 rounded-full" style={{ background: STATUS_META[s].color }} />
              <span className="flex-1 truncate text-ink-2">{STATUS_META[s].label}</span>
              <span key={counts[s]} className="num animate-arrive font-medium text-ink">
                {counts[s]}
              </span>
            </li>
          ))}
        </ul>
      </div>
    );
  }
  return (
    <div className={cn("space-y-2", className)} aria-label="Request counts">
      <ProportionBar segments={statusSegments(counts)} height={6} />
      <ul className="grid grid-cols-5 gap-1">
        {STATUSES.map((s: RequestStatus) => (
          <li key={s} title={STATUS_META[s].label} className="min-w-0">
            <span key={counts[s]} className="num block animate-arrive text-base font-medium leading-5 text-ink">
              {counts[s]}
            </span>
            <span className="flex items-center gap-1 text-[10px] text-muted-foreground">
              <span aria-hidden className="size-1.5 shrink-0 rounded-full" style={{ background: STATUS_META[s].color }} />
              <span className="truncate">{STATUS_META[s].short}</span>
            </span>
          </li>
        ))}
      </ul>
    </div>
  );
}

/* ------------------------------------------------------------------ dumbbell (before → after) */

/**
 * One metric, two measurements on the same 0–100% track: hollow grey = without history, solid teal = with history.
 * The connecting bar is the change. Colour of the bar says whether the change is good for that metric's polarity.
 */
export function Dumbbell({
  label,
  note,
  without,
  withHistory,
  lowerIsBetter = false,
}: {
  label: string;
  note?: string;
  without: number | null;
  withHistory: number | null;
  lowerIsBetter?: boolean;
}) {
  const measured = without !== null && withHistory !== null;
  const pct = (v: number) => `${Math.max(0, Math.min(1, v)) * 100}%`;
  const delta = measured ? Math.round((withHistory - without) * 100) : null;
  const better = measured && withHistory !== without ? (lowerIsBetter ? withHistory < without : withHistory > without) : null;
  const barColor = better === null ? "var(--line-strong)" : better ? "var(--agent)" : "var(--promise-lapsed)";
  const fmt = (v: number | null) => (v === null ? "n/a" : `${Math.round(v * 100)}%`);
  return (
    <li className="grid grid-cols-[minmax(7.5rem,11rem)_1fr_4.5rem] items-center gap-x-4 py-2" title={note}>
      <span className="text-xs text-ink">
        {label}
        {lowerIsBetter ? <span className="block text-2xs text-muted-foreground">lower is better</span> : null}
      </span>
      <span
        role="img"
        aria-label={`${label}: ${fmt(without)} without history, ${fmt(withHistory)} with history`}
        className="relative block h-5"
      >
        <span aria-hidden className="absolute inset-x-0 top-1/2 h-px bg-line" />
        {[0, 0.5, 1].map((t) => (
          <span aria-hidden key={t} className="absolute top-[5px] h-2.5 w-px bg-line" style={{ left: pct(t) }} />
        ))}
        {measured ? (
          <>
            <span aria-hidden className="absolute top-1/2 h-[3px] -translate-y-1/2 rounded-full" style={{ left: pct(Math.min(without, withHistory)), width: `${Math.abs(withHistory - without) * 100}%`, background: barColor }} />
            <span aria-hidden className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-series-base bg-panel" style={{ left: pct(without) }} />
            <span aria-hidden className="absolute top-1/2 size-3 -translate-x-1/2 -translate-y-1/2 rounded-full bg-agent ring-2 ring-panel" style={{ left: pct(withHistory) }} />
          </>
        ) : (
          <span className="absolute inset-0 grid place-items-center text-2xs text-muted-foreground">
            {without === null && withHistory === null ? "not measured" : `only measured ${without === null ? "with" : "without"} history`}
          </span>
        )}
      </span>
      <span className={cn("num text-right text-xs", better === null ? "text-muted-foreground" : better ? "font-medium text-agent" : "font-medium text-promise-lapsed")}>
        {delta === null ? "" : delta === 0 ? "no change" : `${delta > 0 ? "+" : "−"}${Math.abs(delta)} pts`}
      </span>
    </li>
  );
}
