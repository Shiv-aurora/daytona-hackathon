"use client";

import { Loader2, type LucideIcon } from "lucide-react";
import type { ComponentProps, ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { STATUS_META } from "@/lib/relay/selectors";
import type { RequestStatus } from "@/lib/relay/types";

export function StatusBadge({ status, className }: { status: RequestStatus; className?: string }) {
  const meta = STATUS_META[status];
  return (
    <span className={cn("inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium", meta.tone, className)}>
      <span aria-hidden className={cn("size-1.5 rounded-full", meta.dot)} />
      {meta.label}
    </span>
  );
}

const PILL: Record<string, string> = {
  neutral: "border-line bg-muted text-muted-foreground",
  teal: "border-agent/30 bg-agent/10 text-agent",
  amber: "border-promise-due-soon/40 bg-promise-due-soon/10 text-promise-due-soon",
  red: "border-promise-lapsed/30 bg-promise-lapsed/10 text-promise-lapsed",
  green: "border-promise-kept/30 bg-promise-kept/10 text-promise-kept",
  blue: "border-promise-open/30 bg-promise-open/10 text-promise-open",
  purple: "border-agent/30 bg-agent/10 text-agent",
};

export function Pill({ tone = "neutral", icon: Icon, children, className }: { tone?: keyof typeof PILL; icon?: LucideIcon; children: ReactNode; className?: string }) {
  return (
    <span className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-xs font-medium", PILL[tone], className)}>
      {Icon ? <Icon aria-hidden className="size-3" /> : null}
      {children}
    </span>
  );
}

export function Card({ className, ...props }: ComponentProps<"section">) {
  return <section className={cn("rounded-lg border border-line bg-surface", className)} {...props} />;
}

export function SectionTitle({ icon: Icon, children, aside }: { icon?: LucideIcon; children: ReactNode; aside?: ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-2">
      <h3 className="flex items-center gap-2 text-sm font-semibold text-ink">
        {Icon ? <Icon aria-hidden className="size-4 text-agent" /> : null}
        {children}
      </h3>
      {aside}
    </div>
  );
}

const CALLOUT: Record<string, string> = {
  info: "border-promise-open/30 bg-promise-open/5",
  warn: "border-promise-due-soon/40 bg-promise-due-soon/10",
  danger: "border-promise-lapsed/40 bg-promise-lapsed/10",
  good: "border-promise-kept/30 bg-promise-kept/5",
  neutral: "border-line bg-muted/60",
};

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
    <div role={role} className={cn("flex gap-2.5 rounded-lg border p-3 text-sm", CALLOUT[tone], className)}>
      {Icon ? <Icon aria-hidden className="mt-0.5 size-4 shrink-0" /> : null}
      <div className="min-w-0 space-y-0.5">
        {title ? <p className="font-semibold text-ink">{title}</p> : null}
        {children ? <div className="text-muted-foreground">{children}</div> : null}
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
      <label htmlFor={htmlFor} className="block text-xs font-medium text-ink">
        {label}
      </label>
      {children}
      {hint ? <p className="text-xs text-muted-foreground">{hint}</p> : null}
    </div>
  );
}

const CONTROL =
  "w-full rounded-lg border border-line bg-surface px-2.5 py-1.5 text-sm text-ink outline-none transition focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/40 disabled:opacity-50";

export function Select({ className, ...props }: ComponentProps<"select">) {
  return <select className={cn(CONTROL, "h-8 py-0", className)} {...props} />;
}
export function Input({ className, ...props }: ComponentProps<"input">) {
  return <input className={cn(CONTROL, className)} {...props} />;
}
export function Textarea({ className, ...props }: ComponentProps<"textarea">) {
  return <textarea className={cn(CONTROL, "min-h-16 resize-y", className)} {...props} />;
}

export function EmptyState({ icon: Icon, title, children }: { icon?: LucideIcon; title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center gap-1 rounded-lg border border-dashed border-line px-4 py-8 text-center">
      {Icon ? <Icon aria-hidden className="size-5 text-muted-foreground" /> : null}
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
