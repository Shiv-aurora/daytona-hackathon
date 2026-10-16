"use client";

import { useState } from "react";
import { Check, SlidersHorizontal, X } from "lucide-react";
import type { Household, Proposal } from "@/lib/contracts";
import type { Fact } from "@/lib/evidence";
import { DISMISS_REASONS } from "@/lib/labels";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Avatar, BAND, DeadlineTag, KIND_OF, KindTag, TONE_BORDER, bandOf } from "./bits";
import { EvidenceSentence } from "./Evidence";

/** One inbox row: deadline, name, kind icon. Details live in the decision panel. */
export function ProposalRow({ p, household, now, selected, onSelect }: {
  p: Proposal;
  household: Household | undefined;
  now: number;
  selected: boolean;
  onSelect: () => void;
}) {
  const name = household?.name ?? p.household_id;
  const band = bandOf(p.due_ts, now);
  const kind = KIND_OF(p.kind, p.queue);
  const Icon = kind.icon;
  return (
    <article id={`proposal-${p._id}`} tabIndex={-1} aria-current={selected || undefined} aria-label={`Proposal for ${name}`}>
      <button
        onClick={onSelect}
        className={cn(
          "flex w-full items-center gap-2.5 rounded-md border border-l-4 bg-surface px-2 py-1.5 text-left",
          TONE_BORDER[BAND[band].tone],
          selected ? "ring-2 ring-agent/50" : "hover:bg-bg",
        )}
      >
        <Avatar name={name} size={32} />
        <span className="min-w-0 flex-1 truncate text-base font-medium">{name}</span>
        <DeadlineTag due={p.due_ts} now={now} short />
        <Icon aria-label={kind.label} className={cn("size-4 shrink-0", kind.text)} />
      </button>
    </article>
  );
}

/** The selected proposal: who, the cited facts in one sentence, and the decision. */
export function DecisionPanel({ p, household, facts, profile, policyLine = null, day0, runId, now, dismissOpen, busy = false, onDismissOpen, onApprove, onDismiss }: {
  p: Proposal;
  household: Household | undefined;
  facts: Fact[];
  profile: string[];
  policyLine?: string | null;
  day0: string;
  runId: string;
  now: number;
  dismissOpen: boolean;
  busy?: boolean;
  onDismissOpen: (open: boolean) => void;
  onApprove: () => void;
  onDismiss: (reason: string) => void;
}) {
  const [reason, setReason] = useState<string | null>(null);
  const urgentLive = p.due_ts !== undefined && p.due_ts - now < 1;
  const name = household?.name ?? p.household_id;
  return (
    <section aria-label={`Decision for ${name}`} className="rounded-lg border bg-surface px-5 py-4">
      <div className="flex flex-wrap items-start gap-4">
        <Avatar name={name} size={52} />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-2xl font-semibold leading-tight">{name}</p>
            <span aria-live={urgentLive ? "assertive" : "polite"} aria-atomic>
              <DeadlineTag due={p.due_ts} now={now} />
            </span>
            <KindTag kind={p.kind} queue={p.queue} />
          </div>
          {profile.length > 0 && <p className="mt-0.5 text-base text-muted-foreground">{profile.join(" · ")}</p>}
        </div>
        <div className="flex items-center gap-2">
          <Button size="lg" onClick={onApprove} aria-keyshortcuts="A" disabled={busy} aria-busy={busy} title="Approve (A)">
            <Check aria-hidden /> Approve
          </Button>
          <Popover open={dismissOpen} onOpenChange={onDismissOpen}>
            <PopoverTrigger render={<Button size="lg" variant="ghost" aria-keyshortcuts="D" disabled={busy} title="Dismiss (D)" />}>
              <X aria-hidden /> Dismiss
            </PopoverTrigger>
            <PopoverContent align="end" className="w-72">
              <p id={`why-${p._id}`} className="font-medium">
                Why dismiss?
              </p>
              <p className="text-sm text-muted-foreground">Relay learns from this.</p>
              <RadioGroup aria-labelledby={`why-${p._id}`} value={reason} onValueChange={(v) => setReason(v as string)}>
                {DISMISS_REASONS.map((r) => (
                  <label key={r} className="flex cursor-pointer items-center gap-2 text-base">
                    <RadioGroupItem value={r} /> {r}
                  </label>
                ))}
              </RadioGroup>
              <Button variant="outline" disabled={!reason} onClick={() => reason && onDismiss(reason)}>
                Dismiss with this reason
              </Button>
            </PopoverContent>
          </Popover>
        </div>
      </div>
      <div className="mt-3">
        {facts.length ? <EvidenceSentence facts={facts} day0={day0} runId={runId} /> : <p className="max-w-[70ch] text-base">{p.reason}</p>}
      </div>
      {policyLine && (
        <p className="mt-1 flex items-center gap-2 text-base text-agent">
          <SlidersHorizontal aria-hidden className="size-4 shrink-0" />
          {policyLine}
        </p>
      )}
    </section>
  );
}
