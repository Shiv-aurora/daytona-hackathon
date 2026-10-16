"use client";

import type { Proposal } from "@/lib/contracts";
import type { ConsoleSnapshot } from "@/lib/adapter";
import { cn } from "@/lib/utils";
import { ProposalRow } from "./ProposalCard";
import { BAND, KIND_OF, Tag, bandOf, type Band } from "./bits";

type Props = {
  snap: ConsoleSnapshot;
  pending: Proposal[];
  decided: Proposal[];
  selectedId: string | null;
  busyId?: string | null;
  /** Row sliding out after a decision. */
  leavingId?: string | null;
  /** Just decided: flagged next to "Decided" for a moment. */
  justDecided?: { id: string; approved: boolean } | null;
  onSelect: (p: Proposal) => void;
};

const DOT = { red: "bg-promise-lapsed", amber: "bg-promise-due-soon", neutral: "bg-line" } as const;

export function ProposalInbox({ snap, pending, decided, selectedId, busyId = null, leavingId = null, justDecided = null, onSelect }: Props) {
  const household = (id: string) => snap.households.find((h) => h.household_id === id);
  // Bands only label the deadline order; they never reorder it.
  const bands: { band: Band; items: Proposal[] }[] = [];
  for (const p of pending) {
    const band = bandOf(p.due_ts, snap.now_ts);
    const last = bands.at(-1);
    if (last?.band === band) last.items.push(p);
    else bands.push({ band, items: [p] });
  }
  return (
    <section aria-labelledby="inbox-title" className="flex min-h-0 flex-col rounded-lg border bg-surface">
      <header className="flex items-center gap-2 border-b px-3 py-2" title="Sorted by deadline only. Keys: J/K move, A approve, D dismiss">
        <h2 id="inbox-title" className="text-base font-semibold">
          To decide<span className="sr-only"> · {pending.length} awaiting approval</span>
        </h2>
        <Tag tone={pending.length ? "teal" : "neutral"}>{pending.length}</Tag>
        {busyId && (
          <span role="status" className="ml-auto text-sm text-muted-foreground">
            Sending decision…
          </span>
        )}
      </header>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {pending.length === 0 && <p className="py-8 text-center text-base text-muted-foreground">All caught up</p>}
        {bands.map(({ band, items }, i) => (
          <div key={`${band}-${i}`} className="mb-2">
            <h3 className="mb-1 flex items-center gap-1.5 px-1 text-sm text-muted-foreground">
              <span className={cn("size-2 rounded-full", DOT[BAND[band].tone as keyof typeof DOT])} aria-hidden />
              {BAND[band].title} <span>{items.length}</span>
            </h3>
            <div className="space-y-1">
              {items.map((p) => (
                <div key={p._id} className={cn(p._id === leavingId && "motion-safe:animate-leave")}>
                  <ProposalRow p={p} household={household(p.household_id)} now={snap.now_ts} selected={p._id === selectedId} onSelect={() => onSelect(p)} />
                </div>
              ))}
            </div>
          </div>
        ))}
        {decided.length > 0 && (
          <details className="mt-2 px-1">
            <summary className="cursor-pointer text-sm text-muted-foreground">
              Decided {decided.length}
              {justDecided && decided.some((p) => p._id === justDecided.id) && (
                <Tag tone={justDecided.approved ? "green" : "neutral"} glyph={justDecided.approved ? "✓" : "–"} className="ml-2 motion-safe:animate-arrive">
                  {household(decided.find((p) => p._id === justDecided.id)!.household_id)?.name ?? ""}
                </Tag>
              )}
            </summary>
            <ul className="mt-1 space-y-1" aria-label="Decided proposals">
              {decided.map((p) => {
                const approved = p.status === "approved";
                const k = KIND_OF(p.kind, p.queue);
                const reason = snap.decisions[p._id]?.reason;
                return (
                  <li key={p._id}>
                    <button onClick={() => onSelect(p)} title={reason ?? undefined} className="flex w-full items-center gap-2 rounded-md px-1 py-1 text-left text-base hover:bg-bg">
                      <Tag tone={approved ? "green" : "neutral"} glyph={approved ? "✓" : "–"}>
                        {approved ? "Approved" : "Dismissed"}
                      </Tag>
                      <span className="truncate font-medium">{household(p.household_id)?.name ?? p.household_id}</span>
                      <k.icon aria-label={k.label} className={cn("ml-auto size-4 shrink-0", k.text)} />
                    </button>
                  </li>
                );
              })}
            </ul>
          </details>
        )}
      </div>
    </section>
  );
}
