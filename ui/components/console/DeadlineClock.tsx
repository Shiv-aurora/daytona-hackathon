import { Clock, TriangleAlert } from "lucide-react";
import { fmtHours } from "@/lib/sim";
import { cn } from "@/lib/utils";

/** Ring + text. Neutral over 24h, amber under 24h, red under 1h; announcements turn assertive under 1h. */
export function DeadlineClock({ created, due, now }: { created: number; due: number; now: number }) {
  const left = due - now;
  const urgent = left < 1;
  const color = urgent ? "text-safety-tripped" : left < 24 ? "text-promise-due-soon" : "text-ink";
  const frac = Math.min(1, Math.max(0, left / Math.max(due - created, 1e-9)));
  const C = 2 * Math.PI * 10;
  return (
    <span className={cn("inline-flex items-center gap-1.5 font-mono text-xs font-semibold", color)}>
      <svg viewBox="0 0 24 24" className="size-6 -rotate-90" aria-hidden>
        <circle cx="12" cy="12" r="10" fill="none" stroke="var(--border)" strokeWidth="3" />
        <circle cx="12" cy="12" r="10" fill="none" stroke="currentColor" strokeWidth="3" strokeDasharray={`${frac * C} ${C}`} />
      </svg>
      {urgent ? <TriangleAlert aria-hidden className="size-3.5" /> : <Clock aria-hidden className="size-3.5" />}
      <span aria-live={urgent ? "assertive" : "polite"} aria-atomic>
        <span className="sr-only">Deadline: </span>
        {left < 0 ? `overdue by ${fmtHours(-left)}` : `${fmtHours(left)} left`}
      </span>
    </span>
  );
}
