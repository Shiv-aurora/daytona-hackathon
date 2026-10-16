"use client";

import { ArrowRight, Check, Pause, Play, RotateCcw, Timer } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import type { Board } from "@/lib/relay/types";
import { Card } from "./ui";

const happened = (b: Board, module: string, action: string) => b.system_events.some((e) => e.module === module && e.action === action);

interface Step {
  id: string;
  title: string;
  doThis: string;
  notice: string;
  href: string;
  done: (b: Board) => boolean;
}

export const STEPS: Step[] = [
  {
    id: "report",
    title: "File report",
    doThis: "On Response, pick “Food + supplies, road blocked” and file it.",
    notice: "One request per need; emergency wording checked first.",
    href: "/response",
    done: (b) => happened(b, "intake", "report_received"),
  },
  {
    id: "claim",
    title: "Org claims",
    doThis: "Act as Demo Food Collective, open the Food request and claim it with a promised time.",
    notice: "Only a capable organization can claim, and only one.",
    href: "/response",
    done: (b) => happened(b, "recovery", "request_claimed"),
  },
  {
    id: "delivery",
    title: "Delivery reported",
    doThis: "On the same request, report delivery.",
    notice: "Awaiting verification, not Resolved: delivery is not receipt.",
    href: "/response",
    done: (b) => happened(b, "recovery", "delivery_reported"),
  },
  {
    id: "call",
    title: "Follow-up call",
    doThis: "Queue the follow-up call, then in Calls run the scripted reply “did not arrive”.",
    notice: "Opt-in only; Household C never opted in, so no call.",
    href: "/calls",
    done: (b) => happened(b, "calls", "follow_up_finished") && b.calls.some((c) => c.outcome === "not_received" || c.outcome === "verified_received"),
  },
  {
    id: "reopen",
    title: "Reopen + alert",
    doThis: "Open the request: it is Reopened, with an escalation in its audit trail.",
    notice: "Non-receipt never closes anything; a human takes over.",
    href: "/response",
    done: (b) => happened(b, "recovery", "human_escalation"),
  },
  {
    id: "resolve",
    title: "Verify receipt",
    doThis: "Claim again, report delivery, then record a human review: it arrived.",
    notice: "Only confirmed receipt, recorded separately, resolves a request.",
    href: "/response",
    done: (b) => b.verifications.some((v) => v.received === true),
  },
  {
    id: "lesson",
    title: "Share lesson",
    doThis: "On Intelligence, read the approved 2025 flood lesson and its source outcomes. Draft one from this outcome, then approve it.",
    notice: "De-identified, cited, person-approved; survivor records never cross.",
    href: "/intelligence",
    done: (b) => b.lessons.some((l) => l.source_disaster_id === b.disaster.id && l.approved),
  },
  {
    id: "measure",
    title: "Measure history",
    doThis: "Run the comparison.",
    notice: "Same inputs, history off vs on; small synthetic sample.",
    href: "/intelligence",
    done: (b) => b.evaluations.length >= 2,
  },
];

const LIMIT = 180;

function PitchTimer() {
  const [elapsed, setElapsed] = useState(0);
  const [running, setRunning] = useState(false);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setElapsed((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [running]);
  const mm = String(Math.floor(elapsed / 60)).padStart(1, "0");
  const ss = String(elapsed % 60).padStart(2, "0");
  return (
    <div className="flex items-center gap-1.5" role="group" aria-label="Pitch timer">
      <Timer aria-hidden className="size-4 text-muted-foreground" />
      <span
        className={cn("font-mono text-sm tabular-nums", elapsed > LIMIT ? "font-semibold text-promise-lapsed" : elapsed > LIMIT - 30 ? "text-promise-due-soon" : "text-ink")}
        aria-label={`${mm} minutes ${ss} seconds of 3`}
      >
        {mm}:{ss} / 3:00
      </span>
      <Button size="icon-xs" variant="ghost" aria-label={running ? "Pause timer" : "Start timer"} onClick={() => setRunning((r) => !r)}>
        {running ? <Pause aria-hidden /> : <Play aria-hidden />}
      </Button>
      <Button
        size="icon-xs"
        variant="ghost"
        aria-label="Reset timer"
        onClick={() => {
          setRunning(false);
          setElapsed(0);
        }}
      >
        <RotateCcw aria-hidden />
      </Button>
    </div>
  );
}

export function DemoGuide() {
  const { guideOpen, board, runs, selectRun, disasters } = useRelay();
  const [expanded, setExpanded] = useState(true);
  if (!guideOpen) return null;

  const storm = runs.find((r) => r.disaster_id === "demo-storm-2026");
  const onStory = board?.run_id === storm?.run_id;
  const doneFlags = board && onStory ? STEPS.map((s) => s.done(board)) : STEPS.map(() => false);
  const current = doneFlags.findIndex((d) => !d);
  const step = current === -1 ? null : STEPS[current];

  return (
    <div className="px-4 pt-3 lg:px-6">
      <Card className="rounded-lg p-2" aria-label="Demo guide" role="region">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
          {board && !onStory ? (
            <span className="min-w-0 flex-1 text-sm text-ink">
              Demo runs in <strong>{disasters.find((d) => d.id === "demo-storm-2026")?.name ?? "the 2026 storm"}</strong>
              {storm ? (
                <Button variant="link" size="sm" className="ml-1" onClick={() => selectRun(storm.run_id)}>
                  Switch
                </Button>
              ) : null}
            </span>
          ) : (
            <ol className="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto" aria-label="Demo steps">
              {STEPS.map((s, i) => {
                const done = doneFlags[i];
                const active = i === current && onStory;
                return (
                  <li key={s.id} className="flex shrink-0 items-center gap-1" aria-current={active ? "step" : undefined} title={s.doThis}>
                    {i > 0 ? <span aria-hidden className={cn("h-px w-3", done || active ? "bg-agent" : "bg-line")} /> : null}
                    <span
                      className={cn(
                        "flex size-5 items-center justify-center rounded-full border text-[11px] font-medium tabular-nums",
                        done ? "border-agent bg-agent text-white" : active ? "border-agent text-agent ring-2 ring-agent/20" : "border-line text-muted-foreground",
                      )}
                    >
                      {done ? <Check aria-label="Done" className="size-3" /> : i + 1}
                    </span>
                    <span className={cn("text-xs", active ? "font-medium text-ink" : "text-muted-foreground", !active && "hidden 2xl:inline")}>{s.title}</span>
                  </li>
                );
              })}
            </ol>
          )}
          <div className="ml-auto flex items-center gap-2">
            <PitchTimer />
            {step && onStory ? (
              <Link
                href={step.href}
                className="inline-flex h-7 items-center gap-1 rounded-md bg-agent px-2.5 text-[0.8rem] font-medium text-white outline-none hover:bg-agent/90 focus-visible:ring-3 focus-visible:ring-ring/50"
              >
                Go <ArrowRight aria-hidden className="size-3.5" />
              </Link>
            ) : null}
            <Button variant="ghost" size="sm" aria-expanded={expanded} onClick={() => setExpanded((e) => !e)}>
              {expanded ? "Hide" : "Notes"}
            </Button>
          </div>
        </div>
        {expanded && onStory ? (
          <p className="mt-2 border-t border-line pt-2 text-xs text-muted-foreground" aria-live="polite">
            {step ? (
              <>
                <span className="font-medium text-ink">Notice:</span> {step.notice}
              </>
            ) : (
              <span className="font-medium text-ink">Story complete.</span>
            )}
          </p>
        ) : null}
      </Card>
    </div>
  );
}
