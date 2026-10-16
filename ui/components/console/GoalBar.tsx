import { SlidersHorizontal } from "lucide-react";
import type { Goal } from "@/lib/view";
import { fmtShort } from "@/lib/sim";
import { cn } from "@/lib/utils";
import { Ring, Tag, type Tone } from "./bits";

const GOAL_TEXT = "Every promise kept or escalated before its deadline, and no opted-in household silent more than 72 hours.";
const TARGET_PCT = 90;
const n = (v: number | null) => (v === null ? "–" : String(Math.round(v)));

/** The long-term goal from W1's own metrics, as three glanceable instruments. Nothing is invented. */
export function GoalBar({ goal, day0, onSelectHousehold, celebrate = 0 }: {
  goal: Goal;
  day0: string;
  onSelectHousehold: (id: string) => void;
  /** Bumped after an approval: the ring redraws its fill (the value itself stays W1's metric). */
  celebrate?: number;
}) {
  const scored = goal.scoredAt !== null;
  const pct = goal.onTimePct;
  // Neutral on target, amber below it. Never red: this is a team goal, not an alarm.
  const pctTone: Tone = scored && pct !== null && pct < TARGET_PCT ? "amber" : "neutral";
  const silent = goal.silent ?? 0;
  return (
    <section aria-label={`Long-term goal: ${GOAL_TEXT}`} title={GOAL_TEXT} className="flex flex-wrap items-center gap-x-10 gap-y-2 border-b bg-surface px-5 py-2">
      <p className="sr-only">{scored ? `Goal scored ${fmtShort(day0, goal.scoredAt!)}` : "Goal not scored yet"}</p>

      <div className="flex items-center gap-3" title={`${n(goal.met)} of ${n(goal.due)} due promises kept or escalated in time. Target ${TARGET_PCT}%.`}>
        <Ring value={pct === null ? 0 : pct / 100} tone={pctTone} size={52} width={6} replay={celebrate}>
          <span className="font-mono text-sm font-semibold tabular-nums" aria-label={`Promises on time: ${pct === null ? "N/A" : `${pct.toFixed(0)} percent`}`}>
            {!scored ? "–" : pct === null ? "N/A" : `${pct.toFixed(0)}%`}
          </span>
        </Ring>
        <span className="leading-tight">
          <span className="block font-medium">Promises kept or escalated on time</span>
          <span className="font-mono text-sm text-muted-foreground tabular-nums">
            {n(goal.met)} of {n(goal.due)} due
          </span>
        </span>
      </div>

      <div className="flex items-center gap-2.5" title="Opted-in households with no contact for more than 72 hours">
        <span className={cn("font-mono text-2xl font-semibold tabular-nums", silent ? "text-promise-due-soon" : "text-ink")}>{goal.silent === null ? "–" : n(goal.silent)}</span>
        <span className="flex flex-col gap-1">
          <span className="flex gap-0.5" aria-hidden>
            {Array.from({ length: Math.min(silent, 12) }, (_, i) => (
              <span key={i} className="size-2 rounded-full bg-promise-due-soon" />
            ))}
            {silent > 12 && <span className="text-xs leading-none text-promise-due-soon">+{silent - 12}</span>}
          </span>
          <span className="text-sm text-muted-foreground">silent &gt; 72h</span>
        </span>
        <span className="flex gap-1">
          {goal.silentHouseholds.slice(0, 2).map((s) => (
            <button key={s.household_id} onClick={() => onSelectHousehold(s.household_id)} className="rounded-md">
              <Tag tone="amber" className="hover:underline">
                {s.name}
              </Tag>
            </button>
          ))}
        </span>
      </div>

      <Tag tone="teal" icon={SlidersHorizontal} title={goal.policy?.whatChanged ?? "Starting policy"} className="text-sm">
        Policy v{goal.policy?.version ?? 1}
      </Tag>
    </section>
  );
}
