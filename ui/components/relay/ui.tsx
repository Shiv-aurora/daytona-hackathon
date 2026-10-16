"use client";

import { Loader2, type LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { STATUS_META } from "@/lib/relay/selectors";
import type { RequestStatus } from "@/lib/relay/types";

/* ------------------------------------------------------------------ status glyph
   One mark per lifecycle state, readable without colour (shape carries the meaning):
   open = dashed ring · claimed = quarter · awaiting = three-quarters · reopened = ring with a bar · resolved = check. */

const FRACTION: Partial<Record<RequestStatus, number>> = { claimed: 0.25, awaiting_verification: 0.75 };

function slice(f: number, r = 3.2, c = 8) {
  const a = f * Math.PI * 2 - Math.PI / 2;
  const x = c + r * Math.cos(a);
  const y = c + r * Math.sin(a);
  return `M${c} ${c} L${c} ${c - r} A${r} ${r} 0 ${f > 0.5 ? 1 : 0} 1 ${x.toFixed(2)} ${y.toFixed(2)} Z`;
}

export function StatusGlyph({ status, size = 14, className }: { status: RequestStatus; size?: number; className?: string }) {
  const color = STATUS_META[status].color;
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 16 16" className={cn("shrink-0", className)} fill="none">
      {status === "open" ? (
        <circle cx="8" cy="8" r="6" stroke={color} strokeWidth="1.5" strokeDasharray="2.4 2.4" />
      ) : status === "resolved" ? (
        <>
          <circle cx="8" cy="8" r="7" fill={color} />
          <path d="M5 8.2l2.1 2.1L11 6.1" stroke="var(--panel)" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : status === "reopened" ? (
        <>
          <circle cx="8" cy="8" r="6.25" stroke={color} strokeWidth="1.5" />
          <path d="M8 4.8v4" stroke={color} strokeWidth="1.6" strokeLinecap="round" />
          <circle cx="8" cy="11.2" r="0.95" fill={color} />
        </>
      ) : (
        <>
          <circle cx="8" cy="8" r="6.25" stroke={color} strokeWidth="1.5" />
          <path d={slice(FRACTION[status] ?? 0)} fill={color} />
        </>
      )}
    </svg>
  );
}

/** Glyph + plain label. No box, no border: the glyph is the badge. */
export function StatusBadge({ status, className, short = false }: { status: RequestStatus; className?: string; short?: boolean }) {
  const meta = STATUS_META[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 whitespace-nowrap text-xs font-medium text-ink", className)}>
      <StatusGlyph status={status} />
      {short ? meta.short : meta.label}
    </span>
  );
}

/* ------------------------------------------------------------------ small marks */

const TONE_TEXT: Record<string, string> = {
  neutral: "text-ink-2",
  teal: "text-agent",
  amber: "text-promise-due-soon",
  red: "text-promise-lapsed",
  green: "text-promise-kept",
  blue: "text-promise-claimed",
  purple: "text-agent",
};

/** Quiet inline tag: hairline outline, tone only on the text. Use sparingly; most metadata should be plain text. */
export function Pill({
  tone = "neutral",
  icon: Icon,
  children,
  className,
}: {
  tone?: keyof typeof TONE_TEXT;
  icon?: LucideIcon;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-[5px] border border-line px-1.5 py-px text-2xs font-medium leading-4 whitespace-nowrap", TONE_TEXT[tone], className)}>
      {Icon ? <Icon aria-hidden className="size-3" /> : null}
      {children}
    </span>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="rounded-[4px] border border-line bg-surface px-1 font-mono text-[10px] leading-4 text-muted-foreground">{children}</kbd>;
}

/** Two-letter-or-less monogram for organizations. Square, not a person-style avatar. */
export function Monogram({ name, active = false, className }: { name: string; active?: boolean; className?: string }) {
  const letter = name.replace(/^demo\s+/i, "").trim().charAt(0).toUpperCase() || "?";
  return (
    <span
      aria-hidden
      className={cn(
        "grid size-[18px] shrink-0 place-items-center rounded-[5px] border font-mono text-[10px] font-medium",
        active ? "border-agent bg-agent text-panel" : "border-line-strong text-ink-2",
        className,
      )}
    >
      {letter}
    </span>
  );
}

export const shortOrg = (name: string) => name.replace(/^demo\s+/i, "");

/* ------------------------------------------------------------------ structure */

export function Card({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("rounded-[12px] border border-line bg-panel shadow-[var(--ds-shadow-small)]", className)} {...props} />;
}

/** A bordered region with a hairline-separated header. The only container in the system besides a table. */
export function Panel({
  title,
  aside,
  children,
  className,
  bodyClassName,
  id,
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section aria-labelledby={id} className={cn("rounded-[12px] border border-line bg-panel shadow-[var(--ds-shadow-small)]", className)}>
      <header className="flex min-h-11 items-center justify-between gap-3 border-b border-line px-4">
        <h2 id={id} className="text-sm font-semibold tracking-[-0.01em] text-ink">
          {title}
        </h2>
        {aside ? <div className="flex items-center gap-2 text-xs text-muted-foreground">{aside}</div> : null}
      </header>
      <div className={cn("p-4", bodyClassName)}>{children}</div>
    </section>
  );
}

export function PageHeader({ title, subtitle, actions }: { title: string; subtitle?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2">
      <div className="min-w-0">
        <h1 className="text-xl font-semibold tracking-[-0.04em] text-ink">{title}</h1>
        {subtitle ? <p className="mt-0.5 text-sm text-muted-foreground">{subtitle}</p> : null}
      </div>
      {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
    </div>
  );
}

/** Backwards-compatible heading used inside drawers/forms. */
export function SectionTitle({ icon: Icon, children, aside }: { icon?: LucideIcon; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h3 className="flex items-center gap-1.5 text-xs font-semibold text-ink">
        {Icon ? <Icon aria-hidden className="size-3.5 text-muted-foreground" /> : null}
        {children}
      </h3>
      {aside}
    </div>
  );
}

/** Big-number readout used in KPI rows: label on top, numeral, then a free slot for a micro-chart or caption. */
export function Stat({ label, value, unit, hint, children, accent, className }: { label: ReactNode; value: ReactNode; unit?: string; hint?: ReactNode; children?: ReactNode; accent?: string; className?: string }) {
  return (
    <div className={cn("flex min-w-0 flex-col gap-1.5 px-4 py-3", className)}>
      <span className="label flex items-center gap-1.5">
        {accent ? <span aria-hidden className="size-1.5 rounded-full" style={{ background: accent }} /> : null}
        {label}
      </span>
      <span className="flex items-baseline gap-1">
        <span className="num text-2xl font-medium leading-none tracking-[-0.02em] text-ink">{value}</span>
        {unit ? <span className="text-xs text-muted-foreground">{unit}</span> : null}
      </span>
      {children}
      {hint ? <span className="text-2xs text-muted-foreground">{hint}</span> : null}
    </div>
  );
}

/** Segmented control: a single-choice group of buttons. */
export function Segmented<T extends string>({
  value,
  onChange,
  options,
  label,
  className,
}: {
  value: T;
  onChange: (v: T) => void;
  options: { value: T; label: ReactNode; title?: string }[];
  label: string;
  className?: string;
}) {
  return (
    <div role="group" aria-label={label} className={cn("inline-flex rounded-md border border-line bg-surface p-0.5", className)}>
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          title={o.title}
          aria-pressed={value === o.value}
          onClick={() => onChange(o.value)}
          className={cn(
            "inline-flex h-6 items-center gap-1.5 rounded-[4px] px-2 text-xs font-medium outline-none transition-colors",
            value === o.value ? "bg-panel text-ink shadow-[0_0_0_1px_var(--border)]" : "text-muted-foreground hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

const CALLOUT: Record<string, string> = {
  info: "border-l-promise-claimed",
  warn: "border-l-promise-due-soon",
  danger: "border-l-promise-lapsed",
  good: "border-l-promise-kept",
  neutral: "border-l-line-strong",
};
const CALLOUT_ICON: Record<string, string> = {
  info: "text-promise-claimed",
  warn: "text-promise-due-soon",
  danger: "text-promise-lapsed",
  good: "text-promise-kept",
  neutral: "text-muted-foreground",
};

/** A note with a coloured left rule. No tinted fill: the page stays calm and the rule carries severity. */
export function Callout({
  tone = "neutral",
  icon: Icon,
  title,
  children,
  role = "note",
  className,
}: {
  tone?: keyof typeof CALLOUT;
  icon?: LucideIcon;
  title?: string;
  children?: ReactNode;
  role?: "note" | "alert" | "status";
  className?: string;
}) {
  return (
    <div role={role} className={cn("flex gap-2.5 rounded-md border border-l-2 border-line bg-panel px-3 py-2.5 text-sm", CALLOUT[tone], className)}>
      {Icon ? <Icon aria-hidden className={cn("mt-0.5 size-4 shrink-0", CALLOUT_ICON[tone])} /> : null}
      <div className="min-w-0 space-y-0.5">
        {title ? <p className="font-medium text-ink">{title}</p> : null}
        {children ? <div className="text-ink-2">{children}</div> : null}
      </div>
    </div>
  );
}

export function ActionButton({ busy, children, ...props }: ComponentProps<typeof Button> & { busy?: boolean }) {
  return (
    <Button {...props} disabled={props.disabled || busy} aria-busy={busy || undefined}>
      {busy ? <Loader2 aria-hidden className="animate-spin" /> : null}
      {children}
    </Button>
  );
}

export function Field({ label, hint, children, htmlFor }: { label: string; hint?: string; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="space-y-1">
      <label htmlFor={htmlFor} className="block text-xs font-medium text-ink-2">
        {label}
      </label>
      {children}
      {hint ? <p className="text-2xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

const CONTROL =
  "w-full rounded-md border border-line-strong bg-panel px-2.5 py-1.5 text-sm text-ink outline-none transition placeholder:text-muted-foreground/80 focus-visible:border-agent focus-visible:ring-2 focus-visible:ring-agent/25 disabled:opacity-50";

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(CONTROL, "h-8 py-0", className)} {...props} />;
}
export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(CONTROL, "h-8 py-0", className)} {...props} />;
}
export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(CONTROL, "min-h-16 resize-y", className)} {...props} />;
}

export function EmptyState({ icon: Icon, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-md border border-dashed border-line-strong px-4 py-8 text-center">
      {Icon ? <Icon aria-hidden className="size-4 text-muted-foreground" /> : null}
      <p className="text-sm font-medium text-ink">{title}</p>
      {children ? <p className="max-w-prose text-xs text-muted-foreground">{children}</p> : null}
    </div>
  );
}

export function LoadingBlock({ label = "Loading…" }: { label?: string }) {
  return (
    <div role="status" className="flex items-center gap-2 p-6 text-sm text-muted-foreground">
      <Loader2 aria-hidden className="size-4 animate-spin" /> {label}
    </div>
  );
}
