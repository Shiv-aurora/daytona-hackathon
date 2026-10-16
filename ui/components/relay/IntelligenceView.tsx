"use client";

import { BookOpen, Check, ChevronDown, FlaskConical, HeartPulse, House, Package, Play, ShieldCheck, Tag, TrafficCone, Truck, Utensils, Wrench, X, type LucideIcon } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, conditionLabel, fmtTime, lessonStatus } from "@/lib/relay/selectors";
import type { Board, CompareResult, Evaluation, Lesson } from "@/lib/relay/types";
import { ActionButton, Card, EmptyState, Field, Input, LoadingBlock, Pill, SectionTitle, Textarea } from "./ui";

// ---------- Lessons ----------

const CONDITION_ICON: [RegExp, LucideIcon][] = [
  [/food/, Utensils],
  [/suppl/, Package],
  [/transport|ride/, Truck],
  [/shelter/, House],
  [/repair/, Wrench],
  [/medic/, HeartPulse],
  [/access|road|block/, TrafficCone],
];
const conditionIcon = (c: string): LucideIcon => CONDITION_ICON.find(([re]) => re.test(c))?.[1] ?? Tag;

function LessonCard({ lesson, board }: { lesson: Lesson; board: Board }) {
  const { api, runId, act, busy, runs, selectRun, disasters } = useRelay();
  const status = lessonStatus(lesson, board);
  const outcomes = lesson.source_outcome_ids.map((id) => board.verifications.find((v) => v.id === id) ?? null);
  const sourceRun = runs.find((r) => r.run_id === lesson.source_run_id);
  const sourceName = disasters.find((d) => d.id === lesson.source_disaster_id)?.name ?? lesson.source_disaster_id;
  const key = `approve:${lesson.id}`;
  return (
    <Card className="space-y-2 rounded-lg p-3">
      <div className="flex items-start justify-between gap-2">
        <p className="min-w-0 text-sm font-medium text-ink" title={lesson.summary}>
          {lesson.recommendation}
        </p>
        <span className="shrink-0">
          {status === "historical" ? (
            <Pill tone="teal" className="rounded-md" >Historical</Pill>
          ) : status === "approved" ? (
            <Pill tone="teal" icon={ShieldCheck} className="rounded-md">Approved</Pill>
          ) : (
            <Pill tone="neutral" className="rounded-md">Draft</Pill>
          )}
        </span>
      </div>
      <div className="flex flex-wrap items-center gap-1.5">
        {lesson.conditions.map((c) => {
          const Icon = conditionIcon(c);
          return (
            <Pill key={c} icon={Icon} className="rounded-md">
              {conditionLabel(c)}
            </Pill>
          );
        })}
        {lesson.approved_at ? <span className="ml-auto text-[11px] tabular-nums text-muted-foreground">{fmtTime(lesson.approved_at)}</span> : null}
      </div>
      <details className="group text-xs">
        <summary className="flex cursor-pointer list-none items-center gap-1 text-muted-foreground outline-none hover:text-ink focus-visible:ring-3 focus-visible:ring-ring/50">
          <span className="tabular-nums">
            {lesson.source_outcome_ids.length} verified outcome{lesson.source_outcome_ids.length === 1 ? "" : "s"} · from {sourceName}
          </span>
          <ChevronDown aria-hidden className="size-3 transition-transform group-open:rotate-180" />
        </summary>
        <ul className="mt-1.5 space-y-0.5 rounded-md bg-muted/60 p-2 text-muted-foreground">
          {lesson.source_outcome_ids.map((id, i) => {
            const v = outcomes[i];
            return (
              <li key={id}>
                <span className="font-mono">{id}</span>
                {v ? `: ${v.received === true ? "received" : v.received === false ? "did not arrive" : "unconfirmed"} (${v.source === "survivor_call" ? "survivor call" : "human review"})${v.notes ? ` — ${v.notes}` : ""}` : ""}
              </li>
            );
          })}
        </ul>
      </details>
      {status === "historical" && sourceRun ? (
        <Button variant="link" size="sm" className="h-auto p-0 text-xs" onClick={() => selectRun(sourceRun.run_id)}>
          Inspect the source outcomes in that disaster
        </Button>
      ) : null}
      {status === "draft" ? (
        <ActionButton
          size="sm"
          title="A coordinator reviews the wording first. Approval is never automatic."
          busy={busy(key)}
          onClick={() => void act(key, "Lesson approved. It can now inform requests in other disasters.", () => api.approveLesson(runId, lesson.id))}
        >
          <ShieldCheck aria-hidden /> Approve for other disasters
        </ActionButton>
      ) : null}
    </Card>
  );
}

function DraftLesson({ board }: { board: Board }) {
  const { api, runId, act, busy } = useRelay();
  const confirmed = board.verifications.filter((v) => v.received === true);
  const [picked, setPicked] = useState<string[]>([]);
  const [summary, setSummary] = useState("");
  const [recommendation, setRecommendation] = useState("");
  const [conditions, setConditions] = useState("");
  if (!confirmed.length) {
    return (
      <div
        className="flex items-center gap-2 rounded-lg border border-dashed border-line px-3 py-2 text-xs text-muted-foreground"
        title="A lesson must cite at least one verified outcome where help was confirmed. Resolve a request on the Response board first."
      >
        <BookOpen aria-hidden className="size-3.5" />
        Draft a lesson · needs a confirmed receipt
      </div>
    );
  }
  const requestOf = (id: string) => board.requests.find((r) => r.id === id);
  return (
    <Card className="space-y-3 rounded-lg p-3">
      <SectionTitle icon={BookOpen}>Draft a lesson</SectionTitle>
      <fieldset className="space-y-1">
        <legend className="text-xs font-medium text-ink">Cite verified outcomes</legend>
        {board.verifications.map((v) => (
          <label key={v.id} className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              className="accent-[var(--agent)]"
              checked={picked.includes(v.id)}
              onChange={(e) => setPicked((p) => (e.target.checked ? [...p, v.id] : p.filter((x) => x !== v.id)))}
            />
            <span className="font-mono text-xs">{v.id}</span>
            <span className="text-muted-foreground">
              {categoryLabel(requestOf(v.request_id)?.category ?? "other")}: {v.received === true ? "received" : v.received === false ? "did not arrive" : "unconfirmed"}
            </span>
          </label>
        ))}
      </fieldset>
      <Field label="What happened (de-identified)" htmlFor="lesson-summary">
        <Textarea id="lesson-summary" value={summary} onChange={(e) => setSummary(e.target.value)} rows={2} />
      </Field>
      <Field label="Recommendation" htmlFor="lesson-rec">
        <Textarea id="lesson-rec" value={recommendation} onChange={(e) => setRecommendation(e.target.value)} rows={2} />
      </Field>
      <Field label="Applies when" htmlFor="lesson-cond" hint="food, access_blocked">
        <Input id="lesson-cond" value={conditions} onChange={(e) => setConditions(e.target.value)} />
      </Field>
      <ActionButton
        busy={busy("draft-lesson")}
        disabled={!picked.length || !summary.trim() || !recommendation.trim()}
        onClick={async () => {
          const r = await act("draft-lesson", "Draft saved. A coordinator must approve it before it is shared.", () =>
            api.draftLesson(runId, {
              source_outcome_ids: picked,
              summary,
              recommendation,
              conditions: conditions.split(",").map((c) => c.trim().replace(/\s+/g, "_")).filter(Boolean),
            }),
          );
          if (r) {
            setPicked([]);
            setSummary("");
            setRecommendation("");
            setConditions("");
          }
        }}
      >
        Save draft
      </ActionButton>
    </Card>
  );
}

// ---------- Measured comparison ----------

const METRIC_LABEL: Record<string, { label: string; lowerIsBetter?: boolean; note?: string }> = {
  category_extraction: { label: "Need category correct" },
  organization_compatibility: { label: "Organization can supply the need" },
  false_closure: { label: "Wrongly closed a request", lowerIsBetter: true },
  groundedness: { label: "Cites only provided evidence" },
  relevant_lesson_use: { label: "Relevant lesson used", note: "Only measurable where a relevant lesson exists" },
};

// Per-case rows come only from the compare call itself; keep them so navigating away doesn't lose them
// (re-running would save duplicate evaluation records).
const COMPARE_CACHE = new Map<string, CompareResult>();

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "not measured" : `${Math.round(v * 100)}%`);

function verdict(metric: string, a: number | null, b: number | null): { text: string; tone: "green" | "red" | "neutral" | "blue" } {
  if (a === b) return { text: "No change", tone: "neutral" };
  if (a === null || a === undefined) return { text: "Newly measured", tone: "blue" };
  if (b === null || b === undefined) return { text: "No longer measured", tone: "neutral" };
  const better = METRIC_LABEL[metric]?.lowerIsBetter ? b < a : b > a;
  return better ? { text: "Better", tone: "green" } : { text: "Worse", tone: "red" };
}

function Bar({ value, tone }: { value: number | null; tone: "gray" | "blue" }) {
  return (
    <div className="flex items-center gap-2">
      <div className="h-2 flex-1 overflow-hidden rounded-sm bg-muted">
        {value === null ? null : <div className={cn("h-full rounded-sm", tone === "blue" ? "bg-agent" : "bg-muted-foreground/40")} style={{ width: `${Math.max(0, Math.min(1, value)) * 100}%` }} />}
      </div>
      <span className={cn("w-12 text-right text-xs tabular-nums", tone === "blue" ? "font-semibold text-ink" : "text-muted-foreground")}>{value === null ? "n/a" : pct(value)}</span>
    </div>
  );
}

function Comparison({ board }: { board: Board }) {
  const { api, runId, act, busy, health } = useRelay();
  const [result, setResult] = useState<CompareResult | null>(() => COMPARE_CACHE.get(runId) ?? null);
  const evaluations = board.evaluations;
  const without = evaluations.find((e: Evaluation) => e.variant === "without_history");
  const withH = evaluations.find((e: Evaluation) => e.variant === "with_history");
  const metrics = useMemo(() => [...new Set([...Object.keys(without?.metrics ?? {}), ...Object.keys(withH?.metrics ?? {})])], [without, withH]);
  const changes = useMemo(
    () =>
      metrics
        .map((metric) => {
          const a = without?.metrics[metric] ?? null;
          const b = withH?.metrics[metric] ?? null;
          return { metric, a, b, verdict: verdict(metric, a, b) };
        })
        .filter((c) => c.verdict.text !== "No change"),
    [metrics, without, withH],
  );
  const cases = result?.cases;
  const run = async () => {
    const r = await act("compare", "Comparison complete. Results below are exactly what was measured.", () => api.compare(runId));
    if (r) {
      COMPARE_CACHE.set(runId, r);
      setResult(r);
    }
  };

  return (
    <Card className="space-y-3 rounded-lg p-4">
      <SectionTitle icon={FlaskConical}>With vs without history</SectionTitle>
      {!without || !withH ? (
        <div className="space-y-3 py-2 text-center">
          <p className="text-sm text-muted-foreground" title="Compares the same decisions, inputs and time cutoff on held-out cases from this disaster, once with approved historical lessons and once without.">
            Not measured yet
          </p>
          <ActionButton size="lg" className="w-full" busy={busy("compare")} onClick={() => void run()}>
            <Play aria-hidden /> Run comparison
          </ActionButton>
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center gap-1.5">
            <Pill tone="amber" className="rounded-md" >
              <span title="Too small to claim a real-world effect; every result is reported, including ties and regressions.">
                Synthetic · n={without.case_count}
              </span>
            </Pill>
            <Pill className="rounded-md">
              {withH.trace_url ? (
                <a href={withH.trace_url} className="text-agent underline underline-offset-2" target="_blank" rel="noreferrer">
                  Arize trace
                </a>
              ) : health?.live.arize ? (
                <span title="Arize export is on, but this run returned no trace link.">Arize · no trace link</span>
              ) : (
                <span title="Arize export is off in this environment: results are local only.">Local scoring · no Arize export</span>
              )}
            </Pill>
            <span className="ml-auto font-mono text-[11px] text-muted-foreground" title={`Measured ${fmtTime(without.measured_at)}`}>
              {without.experiment_id}
            </span>
          </div>

          <div className="grid grid-cols-[1fr_1fr] gap-3 text-xs font-medium">
            <span className="text-muted-foreground">Without history</span>
            <span className="text-agent">With history</span>
          </div>
          <ul className="space-y-2.5" aria-label="Metrics without and with historical lessons">
            {metrics.map((m) => {
              const a = without.metrics[m] ?? null;
              const b = withH.metrics[m] ?? null;
              const v = verdict(m, a, b);
              const same = v.text === "No change";
              const info = [METRIC_LABEL[m]?.lowerIsBetter ? "Lower is better." : "", METRIC_LABEL[m]?.note ?? ""].filter(Boolean).join(" ");
              return (
                <li key={m} className={cn("space-y-1 rounded-md border p-2", same ? "border-transparent" : "border-agent/30 bg-agent/5")}>
                  <div className="flex items-center justify-between gap-2">
                    <span className={cn("text-xs", same ? "text-muted-foreground" : "font-medium text-ink")} title={info || undefined}>
                      {METRIC_LABEL[m]?.label ?? m.replace(/_/g, " ")}
                    </span>
                    {same ? (
                      <span className="text-[11px] text-muted-foreground">no change</span>
                    ) : (
                      <Pill tone={v.tone === "red" ? "red" : "teal"} className="rounded-md tabular-nums">
                        {v.text} · {pct(a)} → {pct(b)}
                      </Pill>
                    )}
                  </div>
                  <div className="grid grid-cols-2 gap-3">
                    <Bar value={a} tone="gray" />
                    <Bar value={b} tone="blue" />
                  </div>
                </li>
              );
            })}
          </ul>

          <div
            className={cn("rounded-md border px-3 py-2 text-sm font-semibold", changes.length ? "border-agent bg-agent/10 text-agent" : "border-line bg-muted text-muted-foreground")}
            role="status"
          >
            {changes.length
              ? changes.map((c) => `${METRIC_LABEL[c.metric]?.label ?? c.metric}: ${c.verdict.text.toLowerCase()} (${pct(c.a)} → ${pct(c.b)})`).join(" · ")
              : "No metric changed"}
          </div>

          {cases?.length ? (
            <details className="rounded-md border border-line">
              <summary className="cursor-pointer list-none px-3 py-1.5 text-xs font-medium text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring/50">Per-case ({cases.length})</summary>
              <table className="w-full border-t border-line text-xs">
                <caption className="sr-only">Per-case decisions</caption>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id} className="border-b border-line/60 last:border-0">
                      <td className="px-3 py-1.5 text-ink">“{c.report}”</td>
                      <td className="w-10 px-2 py-1.5 text-center" title={c.differs ? `With history, lesson ${c.with_history.lesson_ids?.join(", ") ?? ""} was surfaced.` : "History made no difference to this case."}>
                        {c.differs ? <Check aria-label="History changed this case" className="mx-auto size-4 text-agent" /> : <X aria-label="History made no difference" className="mx-auto size-4 text-muted-foreground" />}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </details>
          ) : null}
        </>
      )}
    </Card>
  );
}

// ---------- View ----------

export function IntelligenceView() {
  const { board, connection } = useRelay();
  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading lessons…" />;

  const lessons = [...board.lessons].sort((a, b) => Number(b.approved) - Number(a.approved) || Date.parse(b.created_at) - Date.parse(a.created_at));
  return (
    <div className="@container space-y-4">
      <div>
        <h1 className="text-xl font-semibold text-ink">Intelligence</h1>
        <p className="text-sm text-muted-foreground" title="Only a lesson that is de-identified and approved by a person can inform a different disaster. Survivor records never cross over.">
          Reviewed lessons from past recoveries.
        </p>
      </div>
      <div className="grid gap-4 @4xl:grid-cols-2">
        <div className="order-2 space-y-2 @4xl:order-1">
          <h2 className="text-sm font-semibold text-ink">Lessons · {board.disaster.name}</h2>
          {lessons.length ? (
            lessons.map((l) => <LessonCard key={l.id} lesson={l} board={board} />)
          ) : (
            <EmptyState icon={BookOpen} title="No lessons yet" />
          )}
          <DraftLesson board={board} />
        </div>
        <div className="order-1 space-y-3 @4xl:order-2">
          <Comparison board={board} />
        </div>
      </div>
    </div>
  );
}
