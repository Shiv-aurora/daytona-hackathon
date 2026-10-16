"use client";

import { Check, Clock, Mic, Phone, PhoneOff, ShieldAlert, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { useState } from "react";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, fmtTime, householdOf, outcomeLabel } from "@/lib/relay/selectors";
import type { Board, RelayCall, ScriptedAnswer } from "@/lib/relay/types";
import { ActionButton, Card, EmptyState, LoadingBlock, Pill, Select, SectionTitle } from "./ui";

const ANSWERS: { value: ScriptedAnswer; label: string }[] = [
  { value: "no", label: "Did not arrive" },
  { value: "yes", label: "Arrived" },
  { value: "no_answer", label: "No answer" },
];

const OUTCOME_STYLE = {
  good: "border-promise-kept/30 bg-promise-kept/10 text-promise-kept",
  bad: "border-promise-lapsed/30 bg-promise-lapsed/10 text-promise-lapsed",
  neutral: "border-line bg-muted text-muted-foreground",
  alert: "border-promise-escalated bg-promise-escalated text-white",
} as const;

const OUTCOME_ICON = { good: Check, bad: X, neutral: Clock, alert: ShieldAlert } as const;

// Never claim a call was a rehearsal (or live) unless the record says so.
function callModeLabel(call: RelayCall): string {
  if (call.mode === "live") return "Live voice";
  if (call.mode === "scripted" || (call.summary && /scripted/i.test(call.summary))) return "Scripted rehearsal · no phone call placed";
  if (call.status === "queued") return "Not started · nothing dialed";
  return "Mode not reported";
}

function CallCard({ call, board }: { call: RelayCall; board: Board }) {
  const { api, runId, act, busy, selectRequest } = useRelay();
  const [answer, setAnswer] = useState<ScriptedAnswer>("no");
  const request = board.requests.find((r) => r.id === call.request_id);
  const household = householdOf(board, call.survivor_id);
  const outcome = outcomeLabel(call.outcome);
  const tone = call.outcome === "emergency_escalated" ? "alert" : outcome.tone;
  const OutcomeIcon = OUTCOME_ICON[tone];
  const dot = call.status === "completed" ? "bg-promise-kept" : call.status === "queued" ? "bg-promise-due-soon" : "bg-agent";
  const key = `start:${call.id}`;
  return (
    <Card className="space-y-3 rounded-lg p-4">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <span role="img" aria-label={`${call.status}: ${callModeLabel(call)}`} title={callModeLabel(call)} className={`size-2 shrink-0 rounded-full ${dot}`} />
        <h3 className="font-semibold text-ink">{request ? categoryLabel(request.category) : "Request"}</h3>
        <span className="text-muted-foreground">· {household?.display_name ?? "Household"}</span>
        <span className="ml-auto text-xs tabular-nums text-muted-foreground">{fmtTime(call.created_at)}</span>
      </div>

      {call.disclosure ? (
        <figure className="rounded-md border border-line bg-muted/60 px-3 py-2">
          <figcaption className="mb-0.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <ShieldCheck aria-hidden className="size-3.5 text-agent" /> Fixed disclosure (code-owned)
          </figcaption>
          <blockquote className="text-sm text-ink">{call.disclosure}</blockquote>
        </figure>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <span className={`inline-flex items-center gap-2 rounded-full border px-3 py-1.5 text-sm font-medium ${OUTCOME_STYLE[tone]}`}>
          <OutcomeIcon aria-hidden className="size-4" />
          {outcome.label}
        </span>
      </div>
      {call.summary ? <p className="line-clamp-2 text-sm text-ink">{call.summary}</p> : null}
      {call.evidence_ids.length ? (
        <p title={call.evidence_ids.join(", ")} className="truncate font-mono text-[11px] text-muted-foreground">
          evidence: {call.evidence_ids.join(", ")}
        </p>
      ) : null}
      {call.status === "completed" && call.outcome !== "verified_received" && call.outcome !== "not_received" ? (
        <p className="text-xs text-muted-foreground">A completed call is not proof of receipt.</p>
      ) : null}

      {call.status === "queued" ? (
        <div className="flex flex-wrap items-center gap-2 rounded-md border border-line bg-muted/40 p-2">
          <Select
            id={`ans-${call.id}`}
            aria-label="Scripted reply"
            value={answer}
            onChange={(e) => setAnswer(e.target.value as ScriptedAnswer)}
            className="min-w-44 flex-1"
          >
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
            <Phone aria-hidden /> Run scripted call
          </ActionButton>
        </div>
      ) : null}
      {request ? (
        <Link href="/response" onClick={() => selectRequest(request.id)} className="inline-block text-xs font-medium text-agent underline underline-offset-2">
          Open on board
        </Link>
      ) : null}
    </Card>
  );
}

export function CallsView() {
  const { board, health, mode, connection, api, runId, act, busy, selectRequest } = useRelay();
  if (!board) return connection === "error" ? null : <LoadingBlock label="Loading calls…" />;

  const calls = [...board.calls].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at));
  const followUps = board.requests.filter((r) => r.status === "awaiting_verification" || r.status === "reopened");
  const voiceLive = mode === "live" && Boolean(health?.live.elevenlabs);

  return (
    <div className="@container space-y-4">
      <div className="space-y-2">
        <div>
          <h1 className="text-xl font-semibold text-ink">Calls</h1>
          <p className="text-sm text-muted-foreground">Confirm by phone that help arrived.</p>
        </div>
        <Pill tone={voiceLive ? "teal" : "neutral"} icon={Mic}>
          {voiceLive ? "ElevenLabs connected" : "Scripted rehearsal · no phone call placed"}
        </Pill>
      </div>

      <Card className="space-y-2 rounded-lg p-4">
        <SectionTitle icon={ShieldCheck}>Household consent</SectionTitle>
        <ul className="flex flex-wrap gap-2">
          {board.survivors.map((s) => (
            <li
              key={s.id}
              title={s.call_opt_in ? "Opted in to calls" : "No opt-in: Relay will not call"}
              className="inline-flex items-center gap-1.5 rounded-md border border-line px-2 py-1 text-sm"
            >
              {s.call_opt_in ? (
                <ShieldCheck aria-hidden className="size-3.5 text-agent" />
              ) : (
                <PhoneOff aria-hidden className="size-3.5 text-muted-foreground" />
              )}
              <span className="font-medium text-ink">{s.display_name}</span>
              {s.call_opt_in ? null : <span className="text-xs text-muted-foreground">will not call</span>}
            </li>
          ))}
        </ul>
      </Card>

      {followUps.length ? (
        <Card className="space-y-2 rounded-lg p-4">
          <SectionTitle icon={Phone}>Needs verification</SectionTitle>
          <ul className="divide-y divide-line">
            {followUps.map((r) => {
              const s = householdOf(board, r.survivor_id);
              const queued = board.calls.some((c) => c.request_id === r.id && c.status === "queued");
              const key = `follow:${r.id}`;
              return (
                <li key={r.id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                  <button className="font-medium text-ink underline-offset-2 hover:underline" onClick={() => selectRequest(r.id)}>
                    {categoryLabel(r.category)}
                  </button>
                  <span className="text-muted-foreground">{s?.display_name}</span>
                  <Pill tone={r.status === "reopened" ? "red" : "amber"}>{r.status === "reopened" ? "Reopened" : "Awaiting"}</Pill>
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
        </Card>
      ) : null}

      <div className="space-y-3">
        <h2 className="text-sm font-semibold text-ink">Call log</h2>
        {calls.length ? (
          calls.map((c) => <CallCard key={c.id} call={c} board={board} />)
        ) : (
          <EmptyState icon={Phone} title="No calls yet">
            Queue a follow-up after a delivery.
          </EmptyState>
        )}
      </div>
    </div>
  );
}
