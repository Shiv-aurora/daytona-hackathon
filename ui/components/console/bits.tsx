// Shared visual vocabulary. One meaning per colour, everywhere:
//   red = act now · amber = soon / gone quiet · blue = open / info · green = done / ok
//   violet = escalated / several services · teal = Relay · neutral = context
// Every tag pairs its colour with an icon or glyph and a word, so no state depends on colour alone.
import {
  Briefcase,
  CircleCheck,
  Clock,
  HardHat,
  Hourglass,
  House,
  Layers,
  Megaphone,
  NotebookPen,
  Package,
  Phone,
  PhoneCall,
  PhoneOff,
  Siren,
  TriangleAlert,
  UserRound,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { fmtHours } from "@/lib/sim";
import { cn } from "@/lib/utils";

export type Tone = "red" | "amber" | "blue" | "green" | "violet" | "teal" | "neutral";

const TONE: Record<Tone, string> = {
  red: "bg-promise-lapsed/10 text-promise-lapsed",
  amber: "bg-promise-due-soon/10 text-promise-due-soon",
  blue: "bg-promise-open/10 text-promise-open",
  green: "bg-promise-kept/10 text-promise-kept",
  violet: "bg-promise-escalated/10 text-promise-escalated",
  teal: "bg-agent/10 text-agent",
  neutral: "bg-muted text-muted-foreground",
};
export const TONE_BORDER: Record<Tone, string> = {
  red: "border-l-promise-lapsed",
  amber: "border-l-promise-due-soon",
  blue: "border-l-promise-open",
  green: "border-l-promise-kept",
  violet: "border-l-promise-escalated",
  teal: "border-l-agent",
  neutral: "border-l-line",
};

export function Tag({ tone = "neutral", icon: Icon, glyph, children, title, className }: {
  tone?: Tone;
  icon?: LucideIcon;
  glyph?: string;
  children: React.ReactNode;
  title?: string;
  className?: string;
}) {
  return (
    <span title={title} className={cn("inline-flex shrink-0 items-center gap-1 rounded-md px-1.5 py-0.5 text-sm font-medium whitespace-nowrap", TONE[tone], className)}>
      {Icon && <Icon aria-hidden className="size-3.5" />}
      {glyph && <span aria-hidden>{glyph}</span>}
      {children}
    </span>
  );
}

// ---- promises ----------------------------------------------------------------------------------
export type PromiseView = "open" | "due_soon" | "kept" | "lapsed";
export const PROMISE: Record<PromiseView, { glyph: string; label: string; tone: Tone; text: string }> = {
  open: { glyph: "◯", label: "Open", tone: "blue", text: "text-promise-open" },
  due_soon: { glyph: "◔", label: "Due soon", tone: "amber", text: "text-promise-due-soon" },
  kept: { glyph: "✓", label: "Kept", tone: "green", text: "text-promise-kept" },
  lapsed: { glyph: "✕", label: "Lapsed", tone: "red", text: "text-promise-lapsed" },
};

export function PromiseBadge({ status }: { status: PromiseView }) {
  const p = PROMISE[status];
  return (
    <Tag tone={p.tone} glyph={p.glyph}>
      {p.label}
    </Tag>
  );
}

// ---- deadlines ---------------------------------------------------------------------------------
export type Band = "overdue" | "soon" | "later" | "none";
export function bandOf(due: number | undefined, now: number): Band {
  if (due === undefined) return "none";
  const left = due - now;
  return left < 0 ? "overdue" : left < 24 ? "soon" : "later";
}
export const BAND: Record<Band, { title: string; tone: Tone }> = {
  overdue: { title: "Overdue", tone: "red" },
  soon: { title: "Next 24 hours", tone: "amber" },
  later: { title: "Later", tone: "neutral" },
  none: { title: "No deadline", tone: "neutral" },
};

/** Deadline as a tag. `short` is for dense rows: "45m", "9h", "18h late". */
export function DeadlineTag({ due, now, short = false }: { due: number | undefined; now: number; short?: boolean }) {
  const w = short ? "w-[4.5rem] justify-start" : "";
  if (due === undefined) return <Tag icon={Clock} className={w}>{short ? "–" : "No deadline"}</Tag>;
  const left = due - now;
  if (left < 0) return <Tag tone="red" icon={TriangleAlert} className={w}>{short ? `${fmtHours(-left)} late` : `Overdue ${fmtHours(-left)}`}</Tag>;
  if (left < 1) return <Tag tone="red" icon={TriangleAlert} className={w}>{short ? fmtHours(left) : `${fmtHours(left)} left`}</Tag>;
  if (left < 24) return <Tag tone="amber" icon={Clock} className={w}>{short ? fmtHours(left) : `${fmtHours(left)} left`}</Tag>;
  return <Tag icon={Clock} className={w}>{short ? fmtHours(left) : `${fmtHours(left)} left`}</Tag>;
}

// ---- proposal kinds ----------------------------------------------------------------------------
const KIND: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  check_in: { label: "Check-in", tone: "teal", icon: House },
  welfare_check: { label: "Welfare check", tone: "teal", icon: House },
  silence_check_in: { label: "Gone quiet", tone: "amber", icon: Hourglass },
  cross_service_check_in: { label: "Several services", tone: "violet", icon: Layers },
  emergency: { label: "Emergency", tone: "red", icon: Siren },
  human_escalation: { label: "Person follow-up", tone: "violet", icon: UserRound },
  caseworker_followup: { label: "Caseworker", tone: "blue", icon: Briefcase },
  priority_power: { label: "Power", tone: "blue", icon: Zap },
  supplies: { label: "Supplies", tone: "neutral", icon: Package },
};

const TEXT: Record<Tone, string> = {
  red: "text-promise-lapsed",
  amber: "text-promise-due-soon",
  blue: "text-promise-open",
  green: "text-promise-kept",
  violet: "text-promise-escalated",
  teal: "text-agent",
  neutral: "text-muted-foreground",
};
export function KIND_OF(kind?: string, queue?: string) {
  const k = (kind && KIND[kind]) || (queue && KIND[queue]) || { label: "Proposal", tone: "teal" as Tone, icon: House };
  return { ...k, text: TEXT[k.tone] };
}

export function KindTag({ kind, queue }: { kind?: string; queue?: string }) {
  const k = KIND_OF(kind, queue);
  return (
    <Tag tone={k.tone} icon={k.icon}>
      {k.label}
    </Tag>
  );
}
/** Kept for callers that only know the queue. */
export const QueueBadge = ({ queue }: { queue?: string }) => <KindTag queue={queue} />;

// ---- sources -----------------------------------------------------------------------------------
export const SOURCE: Record<string, { label: string; icon: LucideIcon }> = {
  "311": { label: "311", icon: Megaphone },
  visit_note: { label: "Visit", icon: NotebookPen },
  utility: { label: "Utility", icon: Zap },
  crew: { label: "Crew", icon: HardHat },
  call: { label: "Call", icon: Phone },
  call_result: { label: "Call", icon: PhoneCall },
};
export const SOURCE_ICON: Record<string, LucideIcon> = Object.fromEntries(Object.entries(SOURCE).map(([k, v]) => [k, v.icon]));

export function SourceTag({ source, children }: { source: string; children?: React.ReactNode }) {
  const s = SOURCE[source] ?? { label: source, icon: NotebookPen };
  return (
    <Tag icon={s.icon}>
      {s.label}
      {children}
    </Tag>
  );
}

// ---- calls & people ----------------------------------------------------------------------------
export const OUTCOME: Record<string, { label: string; tone: Tone; icon: LucideIcon }> = {
  queued: { label: "Queued", tone: "neutral", icon: Clock },
  completed: { label: "Answered", tone: "green", icon: CircleCheck },
  no_answer: { label: "No answer", tone: "amber", icon: PhoneOff },
  failed: { label: "Failed", tone: "red", icon: PhoneOff },
  refused_no_opt_in: { label: "Blocked: no opt-in", tone: "neutral", icon: PhoneOff },
  emergency_escalated: { label: "Emergency: person paged", tone: "red", icon: Siren },
};

export function OutcomeTag({ outcome }: { outcome: string }) {
  const o = OUTCOME[outcome] ?? OUTCOME.queued;
  return (
    <Tag tone={o.tone} icon={o.icon}>
      {o.label}
    </Tag>
  );
}

export const LANGUAGE: Record<string, string> = { en: "English", es: "Spanish", zh: "Mandarin", ko: "Korean", bn: "Bengali" };

// ---- visual primitives ---------------------------------------------------------------------------
const STROKE: Record<Tone, string> = {
  red: "var(--promise-lapsed)",
  amber: "var(--promise-due-soon)",
  blue: "var(--promise-open)",
  green: "var(--promise-kept)",
  violet: "var(--promise-escalated)",
  teal: "var(--agent)",
  neutral: "var(--muted)",
};

/** Progress ring; `value` is 0..1. Children sit in the middle. Changing `replay` redraws the fill. */
export function Ring({ value, tone, size = 40, width = 4, children, label, replay = 0 }: {
  value: number;
  tone: Tone;
  size?: number;
  width?: number;
  children?: React.ReactNode;
  label?: string;
  replay?: number;
}) {
  const r = (size - width) / 2;
  const c = 2 * Math.PI * r;
  const v = Math.max(0, Math.min(1, value));
  return (
    <span className="relative inline-grid shrink-0 place-items-center" style={{ width: size, height: size }} role={label ? "img" : undefined} aria-label={label}>
      <svg width={size} height={size} className="absolute inset-0 -rotate-90" aria-hidden>
        <circle cx={size / 2} cy={size / 2} r={r} fill="none" stroke="var(--border)" strokeWidth={width} />
        <circle
          key={replay}
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={STROKE[tone]}
          strokeWidth={width}
          strokeLinecap="round"
          strokeDasharray={`${v * c} ${c}`}
          style={{ "--c": c } as React.CSSProperties}
          className="transition-[stroke-dasharray] duration-250 motion-safe:animate-ring-fill"
        />
      </svg>
      <span className="relative">{children}</span>
    </span>
  );
}

const initials = (name: string) =>
  name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]!.toUpperCase())
    .join("");

/** Initials in a plain circle. Deadline state is carried by the deadline tag, not the avatar. */
export function Avatar({ name, size = 36 }: { name: string; size?: number }) {
  return (
    <span aria-hidden className="grid shrink-0 place-items-center rounded-full border bg-bg font-semibold text-ink" style={{ width: size, height: size, fontSize: size * 0.36 }}>
      {initials(name)}
    </span>
  );
}
