"use client";

import { BookOpen, Check, FlaskConical, Play, ShieldCheck, X } from "lucide-react";
import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, conditionLabel, fmtTime, lessonStatus } from "@/lib/relay/selectors";
import type { Board, CompareResult, Evaluation, Lesson } from "@/lib/relay/types";
import { metricDelta } from "@/lib/relay/viz";
import { Dumbbell } from "./charts";
import { ProvenanceGraph } from "./ProvenanceGraph";
import { ActionButton, EmptyState, Field, Input, LoadingBlock, PageHeader, Panel, Textarea } from "./ui";

// ---------- Lessons ----------

function LessonEntry({ lesson, board }: { lesson: Lesson; board: Board }) {
  const { api, runId, act, busy, runs, selectRun, disasters } = useRelay();
  const status = lessonStatus(lesson, board);
  const outcomes = lesson.source_outcome_ids.map((id) => board.verifications.find((v) => v.id === id) ?? null);
  const sourceRun = runs.find((r) => r.run_id === lesson.source_run_id);
  const sourceName = disasters.find((d) => d.id === lesson.source_disaster_id)?.name ?? lesson.source_disaster_id;
  const key = `approve:${lesson.id}`;
  return (
    <li className="space-y-2 px-3.5 py-3">
      <div className="flex items-start gap-3">
        <p className="min-w-0 flex-1 text-sm font-medium leading-snug text-ink" title={lesson.summary}>
          {lesson.recommendation}
        </p>
        <span
          className={cn(
            "mt-0.5 inline-flex shrink-0 items-center gap-1 text-2xs font-medium",
            status === "draft" ? "text-muted-foreground" : "text-agent",
          )}
        >
          {status !== "draft" ? <ShieldCheck aria-hidden className="size-3" /> : null}
          {status === "historical" ? "Historical · approved" : status === "approved" ? "Approved" : "Draft"}
        </span>
      </div>
      <p className="text-xs text-muted-foreground">
        {lesson.conditions.map(conditionLabel).join(" · ")}
        {lesson.approved_at ? <span className="num"> · approved {fmtTime(lesson.approved_at)}</span> : null}
      </p>
      <details className="group text-xs">
        <summary className="inline-flex cursor-pointer list-none items-center gap-1 text-muted-foreground outline-none hover:text-ink">
          <span className="num">
            {lesson.source_outcome_ids.length} verified outcome{lesson.source_outcome_ids.length === 1 ? "" : "s"}
          </span>
          · from {sourceName}
          <span aria-hidden className="transition-transform group-open:rotate-90">›</span>
        </summary>
        <ul className="mt-1.5 space-y-0.5 border-l border-line pl-3 text-muted-foreground">
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
    </li>
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
        className="flex items-center gap-2 rounded-md border border-dashed border-line-strong px-3 py-2 text-xs text-muted-foreground"
        title="A lesson must cite at least one verified outcome where help was confirmed. Resolve a request on the Response board first."
      >
        <BookOpen aria-hidden className="size-3.5" />
        Draft a lesson · needs a confirmed receipt
      </div>
    );
  }
  const requestOf = (id: string) => board.requests.find((r) => r.id === id);
  return (
    <Panel title="Draft a lesson" bodyClassName="space-y-3">
      <fieldset className="space-y-1">
        <legend className="mb-1 text-xs font-medium text-ink-2">Cite verified outcomes</legend>
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
    </Panel>
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

function Comparison({ board }: { board: Board }) {
  const { api, runId, act, busy, health } = useRelay();
  const [result, setResult] = useState<CompareResult | null>(() => COMPARE_CACHE.get(runId) ?? null);
  const evaluations = board.evaluations;
  const without = evaluations.find((e: Evaluation) => e.variant === "without_history");
  const withH = evaluations.find((e: Evaluation) => e.variant === "with_history");
  const metrics = useMemo(() => [...new Set([...Object.keys(without?.metrics ?? {}), ...Object.keys(withH?.metrics ?? {})])], [without, withH]);
  const deltas = useMemo(
    () => metrics.map((m) => metricDelta(m, without?.metrics[m], withH?.metrics[m], METRIC_LABEL[m]?.lowerIsBetter)),
    [metrics, without, withH],
  );
  const changes = deltas.filter((d) => d.direction === "better" || d.direction === "worse");
  const cases = result?.cases;
  const run = async () => {
    const r = await act("compare", "Comparison complete. Results below are exactly what was measured.", () => api.compare(runId));
    if (r) {
      COMPARE_CACHE.set(runId, r);
      setResult(r);
    }
  };

  return (
    <Panel
      title="With vs without history"
      aside={
        without && withH ? (
          <>
            <span title="Too small to claim a real-world effect; every result is reported, including ties and regressions." className="rounded-[4px] border border-dashed border-line-strong px-1 text-[10px]">
              synthetic · n={without.case_count}
            </span>
            {withH.trace_url ? (
              <a href={withH.trace_url} className="text-agent underline underline-offset-2" target="_blank" rel="noreferrer">
                Arize trace
              </a>
            ) : health?.live.arize ? (
              <span title="Arize export is on, but this run returned no trace link.">Arize · no trace link</span>
            ) : (
              <span title="Arize export is off in this environment: results are local only.">Local scoring</span>
            )}
          </>
        ) : null
      }
    >
      {!without || !withH ? (
        <div className="space-y-3 py-3 text-center">
          <FlaskConical aria-hidden className="mx-auto size-5 text-muted-foreground" />
          <p className="mx-auto max-w-xs text-sm text-muted-foreground" title="Compares the same decisions, inputs and time cutoff on held-out cases from this disaster, once with approved historical lessons and once without.">
            Not measured yet. Runs the same held-out cases twice: once with approved lessons, once without.
          </p>
          <ActionButton busy={busy("compare")} onClick={() => void run()}>
            <Play aria-hidden /> Run comparison
          </ActionButton>
        </div>
      ) : (
        <div className="space-y-4">
          <div className="flex items-center gap-4 text-2xs text-muted-foreground">
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-full border-2 border-series-base" /> Without history
            </span>
            <span className="flex items-center gap-1.5">
              <span aria-hidden className="size-2.5 rounded-full bg-agent" /> With history
            </span>
            <span className="ml-auto font-mono" title={`Measured ${fmtTime(without.measured_at)}`}>
              {without.experiment_id}
            </span>
          </div>
          <div>
            <div aria-hidden className="grid grid-cols-[minmax(7.5rem,11rem)_1fr_4.5rem] gap-x-4 text-[10px] text-muted-foreground">
              <span />
              <span className="flex justify-between">
                <span>0%</span>
                <span>50%</span>
                <span>100%</span>
              </span>
              <span />
            </div>
            <ul className="divide-y divide-line" aria-label="Metrics without and with historical lessons">
              {deltas.map((d) => (
                <Dumbbell
                  key={d.metric}
                  label={METRIC_LABEL[d.metric]?.label ?? d.metric.replace(/_/g, " ")}
                  note={METRIC_LABEL[d.metric]?.note}
                  without={d.without}
                  withHistory={d.withHistory}
                  lowerIsBetter={METRIC_LABEL[d.metric]?.lowerIsBetter}
                />
              ))}
            </ul>
          </div>

          <p className={cn("border-l-2 py-0.5 pl-3 text-sm", changes.length ? "border-agent font-medium text-ink" : "border-line-strong text-muted-foreground")} role="status">
            {changes.length
              ? changes
                  .map((c) => `${METRIC_LABEL[c.metric]?.label ?? c.metric}: ${c.direction} (${Math.round((c.without ?? 0) * 100)}% → ${Math.round((c.withHistory ?? 0) * 100)}%)`)
                  .join(" · ")
              : "No metric changed"}
          </p>

          {cases?.length ? (
            <details className="rounded-md border border-line">
              <summary className="cursor-pointer list-none px-3 py-1.5 text-xs font-medium text-ink outline-none">
                Per-case ledger ({cases.filter((c) => c.differs).length} of {cases.length} changed)
              </summary>
              <table className="w-full border-t border-line text-xs">
                <caption className="sr-only">Per-case decisions</caption>
                <tbody>
                  {cases.map((c) => (
                    <tr key={c.id} className="border-b border-line last:border-0">
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
        </div>
      )}
    </Panel>
  );
}

// ---------- View ----------

export function IntelligenceView() {
  const { board, connection } = useRelay();
  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading lessons…" />;

  const lessons = [...board.lessons].sort((a, b) => Number(b.approved) - Number(a.approved) || Date.parse(b.created_at) - Date.parse(a.created_at));
  return (
    <div className="@container space-y-5">
      <PageHeader
        title="Intelligence"
        subtitle={
          <span title="Only a lesson that is de-identified and approved by a person can inform a different disaster. Survivor records never cross over.">
            Reviewed lessons from past recoveries · {board.disaster.name}
          </span>
        }
      />

      <Panel title="Where a lesson comes from, and where it applies" aside={<span>De-identified · approved by a person</span>}>
        <ProvenanceGraph />
      </Panel>

      <div className="grid items-start gap-4 @4xl:grid-cols-[3fr_2fr]">
        <Comparison board={board} />
        <div className="space-y-4">
          <Panel title="Lessons" aside={<span className="num">{lessons.length}</span>} bodyClassName="p-0">
            {lessons.length ? (
              <ul className="divide-y divide-line">
                {lessons.map((l) => (
                  <LessonEntry key={l.id} lesson={l} board={board} />
                ))}
              </ul>
            ) : (
              <div className="p-3.5">
                <EmptyState icon={BookOpen} title="No lessons yet" />
              </div>
            )}
          </Panel>
          <DraftLesson board={board} />
        </div>
      </div>
    </div>
  );
}
