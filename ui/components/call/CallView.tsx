"use client";

import { useState } from "react";
import Link from "next/link";
import { Languages, Mic, PhoneCall, ShieldCheck, Siren, UserRound } from "lucide-react";
import { MockAdapter, type ConsoleAdapter } from "@/lib/adapter";
import { LiveAdapter } from "@/lib/live/client";
import { ReplayAdapter } from "@/lib/replay/adapter";
import { mockSnapshot } from "@/lib/mock";
import { fmtShort } from "@/lib/sim";
import { useRunSnapshot } from "@/lib/use-run";
import { callView } from "@/lib/view";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { LANGUAGE, OutcomeTag, PromiseBadge, SourceTag, Tag } from "@/components/console/bits";


function Pill({ ok, icon: Icon, label, detail }: { ok: boolean; icon: typeof Mic; label: string; detail: string }) {
  return (
    <div className={cn("flex items-center gap-2 rounded-md border px-3 py-1.5", ok ? "border-safety-ok/40 text-safety-ok" : "border-safety-pending/50 text-safety-pending")}>
      <Icon aria-hidden className="size-4" />
      <div className="leading-tight">
        <div className="text-xs font-semibold">
          {ok ? "✓" : "◔"} {label}
        </div>
        <div className="text-[11px] text-muted-foreground">{detail}</div>
      </div>
    </div>
  );
}

type Props = { callId: string; runId?: string; relay?: string | null; replay?: boolean; adapter?: ConsoleAdapter };

export function CallView({ callId, runId, relay = null, replay = false, adapter }: Props) {
  const isReplay = replay || adapter instanceof ReplayAdapter;
  const live = !isReplay && (Boolean(relay) || (adapter !== undefined && !(adapter instanceof MockAdapter)));
  const [source] = useState<ConsoleAdapter>(() => adapter ?? (isReplay ? new ReplayAdapter() : relay ? new LiveAdapter(relay) : new MockAdapter()));
  const run = runId ?? (live || isReplay ? null : mockSnapshot.run.run_id);
  const { snap, error, reload } = useRunSnapshot(source, run, live ? 3000 : 0);
  const [note, setNote] = useState<string | null>(null);

  async function escalate() {
    if (!run) return;
    try {
      await source.escalate(run, callId);
      setNote(
        isReplay
          ? "Escalation recorded in this replay only (this browser tab). In a live run it becomes an urgent proposal for a person."
          : "A person has been asked to follow up: it is now an urgent proposal in the coordinator inbox.",
      );
      await reload();
    } catch (e) {
      setNote(`Could not record the escalation (${(e as Error).message}). Reach the on-duty coordinator directly.`);
    }
  }

  const escalateButton = (
    <Button variant="destructive" className="ml-auto" onClick={escalate}>
      <UserRound aria-hidden /> Escalate to a human now
    </Button>
  );
  if (!snap) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        <header className="flex items-center gap-3 border-b bg-surface px-5 py-2.5">
          <Link href="/console" className="text-sm text-muted-foreground hover:text-ink">← Console</Link>
          <h1 className="text-xl font-semibold">Call {callId}</h1>
          {escalateButton}
        </header>
        {note && <p role="status" className="border-b px-5 py-2 text-sm">{note}</p>}
        <p className={error ? "p-8 text-promise-lapsed" : "p-8 text-muted-foreground"}>{error ?? (run ? "Loading call…" : "Which run? Open this call from the console.")}</p>
      </div>
    );
  }
  const v = callView(snap, callId);
  const back = live || isReplay ? `/console?run=${encodeURIComponent(snap.run.run_id)}` : "/console?mode=mock";
  if (!v) return <p className="p-8 text-promise-lapsed">No call {callId} in run {snap.run.run_id}. <Link href={back} className="underline">Back to the console</Link></p>;

  const day0 = snap.run.day0;
  const name = v.household?.name ?? v.request.household_id;
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto">
      <div className="sticky top-0 z-20 shrink-0">
        {v.safety.emergency && (
          <div role="alert" className="bg-safety-tripped px-5 py-3 text-white">
            <p className="flex items-center gap-2 text-base font-bold tracking-wide">
              <Siren aria-hidden className="size-5" /> EMERGENCY PHRASE DETECTED — LLM bypassed — escalating to human
            </p>
            {v.safety.phrase && <p className="text-sm">Heard: “{v.safety.phrase}”. Detected on the raw transcript before any model step.</p>}
          </div>
        )}
        <header className="flex flex-wrap items-center gap-3 border-b bg-surface px-5 py-2.5">
          <Link href={back} className="text-sm text-muted-foreground hover:text-ink">← Console</Link>
          <h1 className="text-xl font-semibold">Call · {name}</h1>
          {v.language && (
            <Tag icon={Languages}>
              <span lang={v.language}>prefers {LANGUAGE[v.language] ?? v.language}</span>
            </Tag>
          )}
          <OutcomeTag outcome={v.status} />
          <span className="text-sm text-muted-foreground" title={`${v.request._id} in run ${snap.run.run_id}`}>
            {fmtShort(day0, v.result?.ts ?? v.request.requested_ts)}
          </span>
          <div className="flex flex-wrap gap-2" role="group" aria-label="Safety state">
            <Pill ok={v.safety.optIn} icon={ShieldCheck} label={v.safety.optIn ? "Opt-in confirmed" : "Opt-in not confirmed"} detail="checked in code before dialing" />
            <Pill ok={v.safety.disclosure} icon={Mic} label={v.safety.disclosure ? "Disclosure played" : "Disclosure not played"} detail={v.result?.outcome === "no_answer" ? "nobody answered" : "fixed first message, word for word"} />
            {!v.safety.emergency && <Pill ok icon={Siren} label="Emergency detector listening" detail="raw transcript, before the LLM" />}
          </div>
          {escalateButton}
        </header>
        {note && (
          <p role="status" className="border-b bg-surface px-5 py-2 text-sm">
            {note}
          </p>
        )}
      </div>

      <main id="main" className="grid min-h-[22rem] flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[3fr_2fr]">
        <section aria-labelledby="transcript-title" className="flex min-h-0 flex-col rounded-lg border bg-surface">
          <h2 id="transcript-title" className="border-b px-4 py-2.5 text-sm font-semibold">
            Transcript
          </h2>
          <ol role="log" className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            {v.turns.length === 0 && <li className="text-muted-foreground">{v.result ? "No one answered. No message was left." : "The call has not been placed yet."}</li>}
            {v.turns.map((t, i) => (
              <li key={i} className={cn("flex", t.speaker === "resident" && "justify-end")}>
                <div className={cn("max-w-[85%] rounded-lg px-3 py-2", t.speaker === "relay" ? "bg-agent/10" : "border bg-surface")}>
                  <p className="mb-0.5 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
                    {t.speaker === "relay" ? <PhoneCall aria-hidden className="size-3.5" /> : <UserRound aria-hidden className="size-3.5" />}
                    {t.speaker === "relay" ? (i === 0 ? "Relay · fixed disclosure" : "Relay") : name}
                  </p>
                  <p lang={v.household?.language} className="text-base">{t.text}</p>
                </div>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="memory-title" className="flex min-h-0 flex-col rounded-lg border bg-surface">
          <h2 id="memory-title" className="border-b px-4 py-2.5 text-sm font-semibold">
            Memory used ({v.memory.length})
          </h2>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto p-3">
            {v.reason && <p className="text-sm"><span className="font-semibold">Why Relay called:</span> {v.reason}</p>}
            {v.promise && (
              <p className="flex flex-wrap items-center gap-2 text-sm">
                <span className="font-semibold">Promise behind the call:</span>
                <PromiseBadge status={v.promise.status} /> {v.promise.text}
                <span className="text-xs text-muted-foreground">due {fmtShort(day0, v.promise.due_ts)}</span>
              </p>
            )}
            <ul className="space-y-2">
              {v.memory.map((e) => (
                <li key={e._id} className="rounded-md border p-3">
                  <div className="flex items-center gap-2">
                    <Tag tone="teal">Day {Math.floor(e.ts / 24)}</Tag>
                    <SourceTag source={e.source} />
                    <span className="ml-auto text-xs text-muted-foreground" title={e._id}>{fmtShort(day0, e.ts)}</span>
                  </div>
                  <p className="mt-1">{e.text}</p>
                </li>
              ))}
            </ul>
          </div>
        </section>
      </main>

      <footer className="grid shrink-0 grid-cols-1 gap-3 border-t bg-bg p-3 lg:grid-cols-[3fr_2fr]">
        <section aria-labelledby="post-title" className="rounded-lg border bg-surface p-3">
          <h2 id="post-title" className="text-sm font-semibold">Written back after the call</h2>
          {v.promiseChanges.length === 0 ? (
            <p className="mt-1 text-muted-foreground">{v.result ? "No promise changed after this call." : "Nothing yet."}</p>
          ) : (
            <ul className="mt-1 space-y-1.5">
              {v.promiseChanges.map((p) => (
                <li key={p._id} className="flex flex-wrap items-center gap-2">
                  <PromiseBadge status={p.status} /> {p.text}
                  <span className="text-xs text-muted-foreground">{p.status_ts !== undefined ? fmtShort(day0, p.status_ts) : ""}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
        <section aria-labelledby="esc-title" aria-live="assertive" className="rounded-lg border bg-surface p-3">
          <h2 id="esc-title" className="text-sm font-semibold">Escalation</h2>
          {v.escalations.length === 0 ? (
            <p className="mt-1 text-muted-foreground">None.</p>
          ) : (
            <ul className="mt-1 space-y-1">
              {v.escalations.map((p) => (
                <li key={p._id} className={cn("flex items-center gap-2 font-semibold", p.kind === "emergency" ? "text-safety-tripped" : "text-promise-escalated")}>
                  {p.kind === "emergency" ? <Siren aria-hidden className="size-4" /> : <UserRound aria-hidden className="size-4" />}
                  {p.kind === "emergency" ? "Emergency handed to a person" : "Human follow-up requested"} · {p.status}
                </li>
              ))}
            </ul>
          )}
        </section>
      </footer>
    </div>
  );
}
