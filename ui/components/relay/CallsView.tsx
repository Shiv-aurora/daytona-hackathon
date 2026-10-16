"use client";

import { Check, Clock, Phone, PhoneOff, ShieldAlert, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, fmtTime, householdOf, outcomeLabel } from "@/lib/relay/selectors";
import type { Board, RelayCall, ScriptedAnswer } from "@/lib/relay/types";
import { OUTCOME_GROUP_LABEL, consentSplit, outcomeMix, verificationMix, type OutcomeGroup } from "@/lib/relay/viz";
import { Legend, ProportionBar, type Segment } from "./charts";
import { ActionButton, EmptyState, LoadingBlock, PageHeader, Panel, Select, StatusBadge } from "./ui";

const ANSWERS: { value: ScriptedAnswer; label: string }[] = [
  { value: "no", label: "Did not arrive" },
  { value: "yes", label: "Arrived" },
  { value: "no_answer", label: "No answer" },
];

const OUTCOME_ICON = { good: Check, bad: X, neutral: Clock, alert: ShieldAlert } as const;
const OUTCOME_COLOR = { good: "text-promise-kept", bad: "text-promise-lapsed", neutral: "text-muted-foreground", alert: "text-promise-lapsed" } as const;

const GROUP_COLOR: Record<OutcomeGroup, string> = {
  confirmed: "var(--promise-kept)",
  not_received: "var(--promise-lapsed)",
  unverified: "var(--series-base)",
  queued: "var(--promise-claimed)",
  blocked: "var(--text)",
};

// Never claim a call was a rehearsal (or live) unless the record says so.
function callModeLabel(call: RelayCall): string {
  if (call.mode === "live") return "Live voice";
  if (call.mode === "scripted" || (call.summary && /scripted/i.test(call.summary))) return "Scripted rehearsal · no phone call placed";
  if (call.status === "queued") return "Not started · nothing dialed";
  return "Mode not reported";
}

/* ------------------------------------------------------------------ call log entry */

function CallEntry({ call, board, last }: { call: RelayCall; board: Board; last: boolean }) {
  const { api, runId, act, busy, selectRequest } = useRelay();
  const [answer, setAnswer] = useState<ScriptedAnswer>("no");
  const request = board.requests.find((r) => r.id === call.request_id);
  const household = householdOf(board, call.survivor_id);
  const outcome = outcomeLabel(call.outcome);
  const tone = call.outcome === "emergency_escalated" ? "alert" : outcome.tone;
  const OutcomeIcon = OUTCOME_ICON[tone];
  const key = `start:${call.id}`;
  return (
    <li className="relative grid grid-cols-[1.25rem_1fr] gap-x-3 px-3.5">
      <div className="relative flex justify-center">
        {!last ? <span aria-hidden className="absolute top-6 bottom-[-0.5rem] w-px bg-line" /> : null}
        <span
          role="img"
          aria-label={`${call.status}: ${callModeLabel(call)}`}
          title={callModeLabel(call)}
          className={cn("relative z-10 mt-[11px] grid size-5 place-items-center rounded-full border bg-panel", call.status === "completed" ? "border-line-strong text-ink-2" : call.status === "queued" ? "border-promise-due-soon text-promise-due-soon" : "border-agent text-agent")}
        >
          <Phone aria-hidden className="size-2.5" />
        </span>
      </div>
      <div className="min-w-0 space-y-2 pb-4 pt-2.5">
        <div className="flex flex-wrap items-baseline gap-x-2 text-sm">
          <h3 className="font-medium text-ink">{request ? categoryLabel(request.category) : "Request"}</h3>
          <span className="text-muted-foreground">{household?.display_name ?? "Household"}</span>
          <span className="ml-auto text-xs tabular-nums text-muted-foreground">{fmtTime(call.created_at)}</span>
        </div>
        <p className={cn("flex items-center gap-1.5 text-sm font-medium", OUTCOME_COLOR[tone])}>
          <OutcomeIcon aria-hidden className="size-3.5" />
          {outcome.label}
        </p>
        {call.disclosure ? (
          <figure className="border-l-2 border-line-strong pl-3">
            <figcaption className="mb-0.5 flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wider text-muted-foreground">
              <ShieldCheck aria-hidden className="size-3 text-agent" /> Fixed disclosure · code-owned
            </figcaption>
            <blockquote className="text-sm text-ink-2">{call.disclosure}</blockquote>
          </figure>
        ) : null}
        {call.summary ? <p className="line-clamp-2 text-sm text-ink-2">{call.summary}</p> : null}
        {call.evidence_ids.length ? (
          <p title={call.evidence_ids.join(", ")} className="truncate font-mono text-[10.5px] text-muted-foreground">
            evidence: {call.evidence_ids.join(", ")}
          </p>
        ) : null}
        {call.status === "completed" && call.outcome !== "verified_received" && call.outcome !== "not_received" ? (
          <p className="text-xs text-muted-foreground">A completed call is not proof of receipt.</p>
        ) : null}

        {call.status === "queued" ? (
          <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-surface p-2">
            <Select id={`ans-${call.id}`} aria-label="Household reply" value={answer} onChange={(e) => setAnswer(e.target.value as ScriptedAnswer)} className="min-w-44 flex-1">
              {ANSWERS.map((a) => (
                <option key={a.value} value={a.value}>
                  {a.label}
                </option>
              ))}
            </Select>
            <ActionButton
              size="sm"
              busy={busy(key)}
              onClick={() =>
                void act(
                  key,
                  (r) =>
                    r.call.outcome === "not_received"
                      ? "Household reported non-receipt: request reopened and escalated to a person."
                      : r.call.outcome === "verified_received"
                        ? "Household confirmed receipt: request resolved."
                        : "No answer recorded. The request stays unverified.",
                  () => api.startCall(runId, call.id, answer),
                )
              }
            >
              <Phone aria-hidden /> Run call
            </ActionButton>
          </div>
        ) : null}
        {request ? (
          <Link href="/response" onClick={() => selectRequest(request.id)} className="inline-block text-xs font-medium text-agent underline-offset-4 hover:underline">
            Open on board
          </Link>
        ) : null}
      </div>
    </li>
  );
}

/* ------------------------------------------------------------------ page */

export function CallsView() {
  const { board, health, mode, connection, api, runId, act, busy, selectRequest } = useRelay();
  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading calls…" />;

  const calls = [...board.calls].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const followUps = board.requests.filter((r) => r.status === "awaiting_verification" || r.status === "reopened");
  const voiceLive = mode === "live" && Boolean(health?.live.elevenlabs);

  const mix = outcomeMix(board.calls);
  const mixSegments: Segment[] = (Object.keys(mix) as OutcomeGroup[]).map((g) => ({ key: g, value: mix[g], color: GROUP_COLOR[g], label: OUTCOME_GROUP_LABEL[g] }));
  const consent = consentSplit(board);
  const ver = verificationMix(board.verifications);
  const delivered = board.requests.filter((r) => r.status === "awaiting_verification" || r.status === "resolved" || r.status === "reopened").length;

  return (
    <div className="@container space-y-5">
      <PageHeader
        title="Calls"
        subtitle="Confirm by phone that help arrived."
        actions={
          voiceLive ? (
            <span className="inline-flex items-center gap-1.5 text-xs text-muted-foreground">
              <span aria-hidden className="size-1.5 rounded-full bg-safety-ok" />
              ElevenLabs connected
            </span>
          ) : undefined
        }
      />

      <div className="grid gap-3 @3xl:grid-cols-3">
        <Panel title="Household consent" aside={<span className="num">{board.survivors.length} {board.survivors.length === 1 ? "household" : "households"}</span>}>
          <ul className="flex flex-wrap gap-2" aria-label="Households and call consent">
            {board.survivors.map((s) => (
              <li
                key={s.id}
                title={`${s.display_name}: ${s.call_opt_in ? "opted in to calls" : "no opt-in, Relay will not call"}`}
                className={cn("grid size-7 place-items-center rounded-full border", s.call_opt_in ? "border-agent bg-agent-soft text-agent" : "border-dashed border-line-strong text-muted-foreground")}
              >
                {s.call_opt_in ? <ShieldCheck aria-hidden className="size-3.5" /> : <PhoneOff aria-hidden className="size-3.5" />}
                <span className="sr-only">
                  {s.display_name}: {s.call_opt_in ? "opted in" : "will not call"}
                </span>
              </li>
            ))}
          </ul>
          <p className="mt-3 text-xs text-muted-foreground">
            <span className="num font-medium text-ink">{consent.optedIn}</span> opted in · <span className="num font-medium text-ink">{consent.declined}</span> will never be called
          </p>
        </Panel>

        <Panel title="Call outcomes" aside={<span className="num">{board.calls.length} {board.calls.length === 1 ? "call" : "calls"}</span>}>
          <ProportionBar segments={mixSegments} height={10} />
          {board.calls.length ? (
            <Legend className="mt-3" items={mixSegments.filter((s) => s.value).map((s) => ({ color: s.color, label: s.label, value: s.value }))} />
          ) : (
            <p className="mt-3 text-xs text-muted-foreground">No calls yet.</p>
          )}
        </Panel>

        <Panel title="Two separate tracks" aside={<span>report ≠ receipt</span>}>
          <dl className="space-y-3 text-xs">
            <div>
              <dt className="mb-1 flex justify-between text-ink-2">
                <span>Organization reports delivered</span>
                <span className="num font-medium text-ink">{delivered}</span>
              </dt>
              <dd>
                <ProportionBar segments={[{ key: "d", value: delivered, color: "var(--promise-claimed)", label: "delivered" }]} height={6} />
              </dd>
            </div>
            <div>
              <dt className="mb-1 flex justify-between text-ink-2">
                <span>Verified by a household or person</span>
                <span className="num font-medium text-ink">{ver.received + ver.notReceived + ver.unconfirmed}</span>
              </dt>
              <dd>
                <ProportionBar
                  segments={[
                    { key: "r", value: ver.received, color: "var(--promise-kept)", label: "received" },
                    { key: "n", value: ver.notReceived, color: "var(--promise-lapsed)", label: "did not arrive" },
                    { key: "u", value: ver.unconfirmed, color: "var(--series-base)", label: "unconfirmed" },
                  ]}
                  height={6}
                />
                <p className="mt-1 text-2xs text-muted-foreground">
                  <span className="num">{ver.received}</span> received · <span className="num">{ver.notReceived}</span> did not arrive · <span className="num">{ver.unconfirmed}</span> unconfirmed
                  <br />
                  {ver.call} by survivor call · {ver.human} by human review
                </p>
              </dd>
            </div>
          </dl>
        </Panel>
      </div>

      {followUps.length ? (
        <Panel title="Needs verification" bodyClassName="p-0">
          <ul className="divide-y divide-line">
            {followUps.map((r) => {
              const s = householdOf(board, r.survivor_id);
              const queued = board.calls.some((c) => c.request_id === r.id && c.status === "queued");
              const key = `follow:${r.id}`;
              return (
                <li key={r.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3.5 py-2.5 text-sm">
                  <StatusBadge status={r.status} short />
                  <button className="font-medium text-ink underline-offset-2 hover:underline" onClick={() => selectRequest(r.id)}>
                    {categoryLabel(r.category)}
                  </button>
                  <span className="text-muted-foreground">{s?.display_name}</span>
                  <span className="ml-auto">
                    {!s?.call_opt_in ? (
                      <span className="text-xs text-muted-foreground" title="Not callable: use a human review">
                        Human review
                      </span>
                    ) : queued ? (
                      <span className="text-xs text-muted-foreground">Queued below</span>
                    ) : (
                      <ActionButton
                        size="sm"
                        variant="outline"
                        busy={busy(key)}
                        onClick={() => void act(key, "Follow-up call queued. Nothing is dialed until you run it.", () => api.queueFollowUp(runId, r.id))}
                      >
                        Queue follow-up
                      </ActionButton>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </Panel>
      ) : null}

      <Panel title="Call log" bodyClassName="p-0 pt-1">
        {calls.length ? (
          <ol>
            {calls.map((c, i) => (
              <CallEntry key={c.id} call={c} board={board} last={i === calls.length - 1} />
            ))}
          </ol>
        ) : (
          <div className="p-3.5">
            <EmptyState icon={Phone} title="No calls yet">
              Queue a follow-up after a delivery.
            </EmptyState>
          </div>
        )}
      </Panel>
    </div>
  );
}
