"use client";

import Link from "next/link";
import { NotebookPen, PhoneOff } from "lucide-react";
import type { Cite, Fact } from "@/lib/evidence";
import { fmtClock, fmtShort } from "@/lib/sim";
import { cn } from "@/lib/utils";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { OUTCOME, OutcomeTag, SOURCE, Tag } from "./bits";

const day = (day0: string, ts: number) => fmtShort(day0, ts).split(" ").slice(0, 2).join(" ");

/** Inline citation: source icon + date. Opens the record's provenance. */
export function CiteChip({ c, day0, runId, dateOnly = false }: { c: Cite; day0: string; runId: string; dateOnly?: boolean }) {
  const missed = c.source === "call_result" && c.outcome !== undefined && c.outcome !== "completed";
  const s = SOURCE[c.source] ?? { label: c.source, icon: NotebookPen };
  const Icon = missed ? PhoneOff : s.icon;
  const date = day(day0, c.ts);
  return (
    <Popover>
      <PopoverTrigger
        render={
          <button
            aria-label={`${s.label} record, ${date}. Show source`}
            className={cn(
              "ml-1 first:ml-0 inline-flex -translate-y-px items-center gap-1 rounded-md border px-1.5 align-middle text-sm font-medium leading-6",
              missed ? "border-promise-due-soon/40 bg-promise-due-soon/10 text-promise-due-soon" : "bg-bg text-muted-foreground hover:border-agent hover:text-agent",
            )}
          />
        }
      >
        <Icon aria-hidden className="size-3.5" />
        {dateOnly ? date : `${s.label} ${date}`}
      </PopoverTrigger>
      <PopoverContent align="start" className="w-96 gap-2">
        <div className="flex flex-wrap items-center gap-1.5">
          <Tag icon={Icon}>{s.label}</Tag>
          {c.outcome && <OutcomeTag outcome={c.outcome} />}
          {c.real ? (
            <Tag tone="blue" title="Real NYC Open Data 311 request from Ida (2021)">
              Real 311
            </Tag>
          ) : (
            <Tag>Simulated</Tag>
          )}
        </div>
        <p className="text-base leading-relaxed">{c.text || OUTCOME[c.outcome ?? ""]?.label || "No text"}</p>
        <dl className="grid grid-cols-[auto_1fr] gap-x-3 text-sm text-muted-foreground">
          <dt>When</dt>
          <dd>{fmtClock(day0, c.ts)}</dd>
          <dt>Record</dt>
          <dd className="font-mono text-xs break-all">{c.id}</dd>
        </dl>
        {c.callId && (
          <Link href={`/call/${encodeURIComponent(c.callId)}?run=${encodeURIComponent(runId)}`} className="text-sm font-medium text-agent underline underline-offset-2">
            Open call
          </Link>
        )}
      </PopoverContent>
    </Popover>
  );
}

/** "Son Wei was due Sep 7 [Visit Sep 3], no sign it happened. Calls unanswered [Sep 8] [Sep 11]." */
export function EvidenceSentence({ facts, day0, runId }: { facts: Fact[]; day0: string; runId: string }) {
  return (
    <p className="max-w-[70ch] text-base leading-8">
      {facts.map((f, i) => (
        <span key={i}>
          {f.lead}{" "}
          {f.cites.map((c) => (
            <CiteChip key={c.id} c={c} day0={day0} runId={runId} dateOnly={f.cites.length > 1} />
          ))}
          {f.tail ?? ""}.{" "}
        </span>
      ))}
    </p>
  );
}
