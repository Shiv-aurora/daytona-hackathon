"use client";

import { BookOpen, Check, CheckCircle2, ClipboardCheck, Hourglass, Phone, PhoneOff, RotateCcw, ShieldAlert, ShieldCheck, Truck, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { canCall, categoryLabel, conditionLabel, eventText, fmtTime, householdOf, isEscalation, orgName, relTime, requestStory } from "@/lib/relay/selectors";
import { STATUS_META } from "@/lib/relay/selectors";
import type { Board, Recommendation, RelayRequest } from "@/lib/relay/types";
import { journey, type NodeState } from "@/lib/relay/viz";
import { CategoryIcon } from "./ResponseView";
import { ActionButton, Callout, Field, Input, Pill, Select, SectionTitle, StatusBadge } from "./ui";

const PROMISE_WINDOWS = [
  { label: "in 1 hour", hours: 1 },
  { label: "in 2 hours", hours: 2 },
  { label: "in 4 hours", hours: 4 },
  { label: "in 24 hours", hours: 24 },
];

const DISCLAIMER =
  "Suggestions are de-identified, approved by a person, and from another disaster. They inform a coordinator's judgment; they never act on their own.";

/* ---------- Progress: four nodes, the last is the independent check ---------- */

const NODE_RING: Record<NodeState, string> = {
  done: "border-ink bg-ink text-panel",
  current: "border-promise-due-soon text-promise-due-soon",
  todo: "border-line-strong bg-panel text-muted-foreground",
  bad: "border-promise-lapsed bg-promise-lapsed text-panel",
};

function Stepper({ request }: { request: RelayRequest }) {
  const nodes = journey(request);
  const accent = STATUS_META[request.status].color;
  return (
    <ol aria-label="Request progress" className="flex">
      {nodes.map((n, i) => {
        const last = i === nodes.length - 1;
        const verifiedDone = last && n.state === "done";
        return (
          <li key={n.id} className="relative flex flex-1 flex-col items-center gap-1.5">
            {!last ? <span aria-hidden className={cn("absolute left-1/2 top-[9px] h-px w-full", nodes[i + 1].state === "todo" ? "border-t border-dashed border-line-strong" : "bg-ink/50")} /> : null}
            <span
              className={cn("relative grid size-[19px] place-items-center rounded-full border-[1.5px]", NODE_RING[n.state], verifiedDone && "border-promise-kept bg-promise-kept")}
              style={n.state === "current" ? { borderColor: accent, color: accent } : undefined}
            >
              {n.state === "done" ? <Check aria-hidden className="size-3" /> : n.state === "bad" ? <RotateCcw aria-hidden className="size-2.5" /> : n.state === "current" ? <Hourglass aria-hidden className="size-2.5" /> : null}
            </span>
            <span className={cn("text-center text-[11px] font-medium leading-tight", n.state === "todo" ? "text-muted-foreground" : n.state === "bad" ? "text-promise-lapsed" : "text-ink")}>{n.label}</span>
            <span className="sr-only">{n.state === "done" ? "done" : n.state === "todo" ? "pending" : n.state === "current" ? "waiting" : "needs a person"}</span>
          </li>
        );
      })}
    </ol>
  );
}

/* ---------- Two tracks: what the organization says vs what the household / a person says ---------- */

function Track({ icon: Icon, label, children, time, accent = false }: { icon: LucideIcon; label: string; children: ReactNode; time?: string; accent?: boolean }) {
  return (
    <div className="min-w-0 space-y-1 rounded-md border border-line bg-panel px-3 py-2.5">
      <p className="flex items-center gap-1.5 text-2xs font-medium uppercase tracking-wider text-muted-foreground">
        <Icon aria-hidden className={cn("size-3", accent ? "text-agent" : "text-muted-foreground")} />
        {label}
      </p>
      <div className="text-sm leading-snug text-ink">{children}</div>
      {time ? <p className="text-2xs text-muted-foreground">{time}</p> : null}
    </div>
  );
}

/* ---------- Next step (one primary action area) ---------- */

function ClaimAction({ request, board }: { request: RelayRequest; board: Board }) {
  const { api, runId, act, busy, orgId, setOrgId } = useRelay();
  const [windowHours, setWindowHours] = useState(2);
  const acting = board.organizations.find((o) => o.id === orgId);
  const capable = board.organizations.find((o) => o.capabilities.includes(request.category));
  const canClaim = Boolean(acting && acting.capabilities.includes(request.category));
  const key = `claim:${request.id}`;

  if (!canClaim) {
    return (
      <Callout tone="neutral" title={`${acting?.name ?? "This organization"} can't supply ${categoryLabel(request.category).toLowerCase()}`}>
        {capable ? (
          <Button size="sm" variant="outline" className="mt-1" onClick={() => setOrgId(capable.id)}>
            Act as {capable.name}
          </Button>
        ) : (
          "No seeded organization supports this need."
        )}
      </Callout>
    );
  }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <Field label="Deliver within" htmlFor={`promise-${request.id}`}>
        <Select id={`promise-${request.id}`} value={windowHours} onChange={(e) => setWindowHours(Number(e.target.value))}>
          {PROMISE_WINDOWS.map((w) => (
            <option key={w.hours} value={w.hours}>
              {w.label}
            </option>
          ))}
        </Select>
      </Field>
      <ActionButton
        busy={busy(key)}
        onClick={() =>
          void act(key, `Claimed by ${acting!.name}.`, () =>
            api.claim(runId, request.id, {
              organization_id: acting!.id,
              promised_at: new Date(Date.now() + windowHours * 3600_000).toISOString(),
            }),
          )
        }
      >
        Claim as {acting!.name}
      </ActionButton>
    </div>
  );
}

function DeliveryAction({ request, board }: { request: RelayRequest; board: Board }) {
  const { api, runId, act, busy, orgId, setOrgId } = useRelay();
  const [notes, setNotes] = useState("");
  const claimer = board.organizations.find((o) => o.id === request.organization_id);
  const key = `delivery:${request.id}`;

  if (request.organization_id !== orgId) {
    return (
      <Callout tone="neutral" title={`Only ${claimer?.name ?? "the claiming organization"} can report delivery`}>
        {claimer ? (
          <Button size="sm" variant="outline" className="mt-1" onClick={() => setOrgId(claimer.id)}>
            Act as {claimer.name}
          </Button>
        ) : null}
      </Callout>
    );
  }

  return (
    <div className="flex flex-wrap items-end gap-2">
      <div className="min-w-40 flex-1">
        <Field label="Delivery note (optional)" htmlFor={`notes-${request.id}`}>
          <Input id={`notes-${request.id}`} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
      <ActionButton
        busy={busy(key)}
        onClick={() => void act(key, "Delivery reported. The request now awaits independent verification.", () => api.deliver(runId, request.id, { organization_id: orgId, notes }))}
      >
        Report delivery
      </ActionButton>
    </div>
  );
}

function VerifyAction({ request, board }: { request: RelayRequest; board: Board }) {
  const { api, runId, act, busy } = useRelay();
  const [answer, setAnswer] = useState("no");
  const [notes, setNotes] = useState("");
  const call = canCall(board, request);
  const key = `verify:${request.id}`;
  const followKey = `follow:${request.id}`;

  return (
    <div className="space-y-2">
      <p className="text-xs font-semibold text-ink">Verify receipt</p>
      <div className="flex flex-wrap items-center gap-2">
        {call.optedIn ? (
          call.queued ? (
            <p className="text-sm text-muted-foreground">
              Call queued.{" "}
              <Link href="/calls" className="font-medium text-agent underline underline-offset-2">
                Run in Calls
              </Link>
            </p>
          ) : (
            <>
              <Pill tone="green" icon={ShieldCheck}>
                Opted in
              </Pill>
              <ActionButton
                size="sm"
                variant="outline"
                busy={busy(followKey)}
                onClick={() => void act(followKey, "Follow-up call queued. Nothing is dialed until you run it in Calls.", () => api.queueFollowUp(runId, request.id))}
              >
                <Phone aria-hidden /> Queue call
              </ActionButton>
            </>
          )
        ) : (
          <>
            <Pill tone="red" icon={PhoneOff}>
              No opt-in
            </Pill>
            <span className="text-xs text-muted-foreground">Human review only</span>
          </>
        )}
      </div>
      <div className="grid gap-2 sm:grid-cols-[10rem_1fr]">
        <Field label="Received?" htmlFor={`recv-${request.id}`}>
          <Select id={`recv-${request.id}`} value={answer} onChange={(e) => setAnswer(e.target.value)}>
            <option value="no">No</option>
            <option value="yes">Yes</option>
            <option value="unsure">Unsure</option>
          </Select>
        </Field>
        <Field label="Notes" htmlFor={`vnotes-${request.id}`}>
          <Input id={`vnotes-${request.id}`} value={notes} onChange={(e) => setNotes(e.target.value)} />
        </Field>
      </div>
      <ActionButton
        size="sm"
        busy={busy(key)}
        onClick={() =>
          void act(
            key,
            (r) =>
              r.verification.received === true
                ? "Receipt confirmed: request resolved."
                : r.verification.received === false
                  ? "Not received: request reopened and escalated to a human."
                  : "Recorded as unconfirmed. The request stays open.",
            () => api.verify(runId, request.id, { received: answer === "yes" ? true : answer === "no" ? false : null, notes }),
          )
        }
      >
        Record human review
      </ActionButton>
    </div>
  );
}

function NextStep({ request, board }: { request: RelayRequest; board: Board }) {
  if (request.status === "resolved") {
    const story = requestStory(board, request);
    const confirmed = story.verifications.findLast((v) => v.received === true);
    const by = confirmed?.source === "survivor_call" ? "the household on a call" : "a coordinator's review";
    return (
      <Callout tone="good" icon={CheckCircle2} title="Resolved">
        {`Confirmed by ${by}, separate from the delivery report.`}
      </Callout>
    );
  }

  const claimable = request.status === "open" || request.status === "reopened";
  const verifying = request.status === "awaiting_verification" || request.status === "reopened";

  return (
    <section aria-label="Next step" className="space-y-3 rounded-md border border-line bg-panel p-3">
      {claimable ? <ClaimAction request={request} board={board} /> : null}
      {request.status === "claimed" ? <DeliveryAction request={request} board={board} /> : null}
      {verifying ? (
        <div className={claimable ? "border-t border-line pt-3" : undefined}>
          <VerifyAction request={request} board={board} />
        </div>
      ) : null}
    </section>
  );
}

/* ---------- Suggestions ---------- */

function titleCase(s: string) {
  return s.replace(/\b\w/g, (c) => c.toUpperCase());
}

function Suggestions({ request, board }: { request: RelayRequest; board: Board }) {
  const { api, runId } = useRelay();
  const [state, setState] = useState<{ key: string; items: Recommendation[]; basis: "server" | "category" } | null>(null);
  const key = `${runId}:${request.id}:${request.status}`;

  useEffect(() => {
    let cancelled = false;
    (async () => {
      let items: Recommendation[] | null = null;
      try {
        items = await api.recommendations(runId, request.id);
      } catch {
        items = null;
      }
      if (cancelled) return;
      if (items) return setState({ key, items, basis: "server" });
      // Backend has no recommendations route yet: match approved cross-disaster lessons on category/conditions.
      const have = new Set([request.category, ...(request.conditions ?? [])]);
      const fallback = board.lessons
        .filter((l) => l.source_disaster_id !== board.disaster.id && l.approved)
        .map((l) => ({ l, matched: l.conditions.filter((c) => have.has(c)) }))
        .filter((m) => m.matched.length)
        .map(({ l, matched }) => ({
          lesson_id: l.id,
          summary: l.summary,
          recommendation: l.recommendation,
          matched_conditions: matched,
          source_disaster_id: l.source_disaster_id,
          source_outcomes: l.source_outcome_ids.map((id) => ({ id, received: null, notes: "", source: "" })),
        }));
      setState({ key, items: fallback, basis: "category" });
    })();
    return () => {
      cancelled = true;
    };
    // board.lessons only matters for the fallback; re-running on every poll would flicker.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [api, runId, request.id, request.status]);

  if (request.status === "resolved") return null;
  const current = state?.key === key ? state : null;
  const source = (id: string) => (board.disaster.id === id ? "this disaster" : titleCase(id.replace(/^demo-/, "").replace(/-/g, " ")));

  return (
    <section className="space-y-2 rounded-md border border-line bg-panel p-3">
      <SectionTitle icon={BookOpen} aside={<span title={DISCLAIMER}><Pill>For a person to weigh</Pill></span>}>
        Similar past recoveries
      </SectionTitle>
      {!current ? (
        <p className="text-sm text-muted-foreground">Checking lessons…</p>
      ) : current.items.length === 0 ? (
        <p className="text-sm text-muted-foreground">None apply.</p>
      ) : (
        <>
          {current.basis === "category" ? (
            <div>
              <Pill>Matched on need category only</Pill>
            </div>
          ) : null}
          <ul className="space-y-2">
            {current.items.map((r) => {
              const n = r.source_outcomes.length;
              return (
                <li key={r.lesson_id} className="space-y-1.5 rounded-md border border-agent/40 bg-agent-soft p-2.5" title={`${r.summary}\nLesson ${r.lesson_id}`}>
                  <p className="truncate text-sm font-medium text-ink">{r.recommendation}</p>
                  <div className="flex flex-wrap items-center gap-1.5">
                    <Pill>{`from ${source(r.source_disaster_id)} · ${n} verified outcome${n === 1 ? "" : "s"}`}</Pill>
                    {r.matched_conditions.map((c) => (
                      <Pill key={c} tone="blue">
                        {conditionLabel(c)}
                      </Pill>
                    ))}
                  </div>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </section>
  );
}

/* ---------- Audit trail ---------- */

function Activity({ request, board }: { request: RelayRequest; board: Board }) {
  const { events } = requestStory(board, request);
  if (!events.length) return null;
  return (
    <details className="group rounded-md border border-line bg-panel" open={events.length <= 6}>
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-ink outline-none">
        Audit trail <span className="num font-normal text-muted-foreground">{events.length}</span>
        <span aria-hidden className="ml-auto text-muted-foreground transition-transform group-open:rotate-90">›</span>
      </summary>
      <ol className="border-t border-line px-3 py-2.5">
        {events.map((e, i) => (
          <li key={e.id} className="relative flex gap-3 pb-2.5 last:pb-0">
            {i < events.length - 1 ? <span aria-hidden className="absolute left-[3px] top-3 bottom-0 w-px bg-line" /> : null}
            <span aria-hidden className={cn("relative z-10 mt-[5px] size-[7px] shrink-0 rounded-full", isEscalation(e) ? "bg-promise-lapsed" : "bg-line-strong")} />
            <span className="min-w-0 flex-1">
              <span className={cn("block text-xs leading-snug text-ink", isEscalation(e) && "font-medium text-promise-lapsed")} title={eventText(e)}>
                {isEscalation(e) ? <ShieldAlert aria-hidden className="mr-1 inline size-3 -translate-y-px" /> : null}
                {eventText(e)}
              </span>
              <span className="block text-2xs tabular-nums text-muted-foreground">{fmtTime(e.created_at)}</span>
            </span>
          </li>
        ))}
      </ol>
      <p className="border-t border-line px-3 py-1.5 font-mono text-[10px] text-muted-foreground">
        run {board.run_id} · disaster {board.disaster.id}
      </p>
    </details>
  );
}

/* ---------- Drawer ---------- */

export function RequestDrawer() {
  const { board, selectedRequestId, selectRequest, now } = useRelay();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const request = board?.requests.find((r) => r.id === selectedRequestId) ?? null;

  useEffect(() => {
    if (selectedRequestId) headingRef.current?.focus();
  }, [selectedRequestId]);

  if (!board || !request) return null;
  const household = householdOf(board, request.survivor_id);
  const story = requestStory(board, request);
  const claimed = Boolean(request.organization_id) && request.status !== "open";
  const latest = story.latestVerification;

  return (
    <>
      <div aria-hidden className="fixed inset-0 z-30 bg-ink/30 lg:hidden" onClick={() => selectRequest(null)} />
      <aside
        role="dialog"
        aria-modal="false"
        aria-labelledby="drawer-title"
        onKeyDown={(e) => e.key === "Escape" && selectRequest(null)}
        className="fixed inset-y-0 right-0 z-40 flex w-full flex-col border-l border-line bg-surface shadow-[-12px_0_32px_-24px_rgba(0,0,0,0.35)] sm:w-[26rem]"
      >
        <header className="flex items-start gap-3 border-b border-line bg-panel px-4 py-3.5">
          <CategoryIcon category={request.category} className="mt-1 size-4 shrink-0 text-muted-foreground" />
          <div className="min-w-0 flex-1">
            <h2 id="drawer-title" ref={headingRef} tabIndex={-1} className="text-base font-semibold tracking-[-0.01em] text-ink outline-none">
              {categoryLabel(request.category)} request
            </h2>
            <p className="truncate text-xs text-muted-foreground">
              {household?.display_name ?? "Unknown household"}
              {request.promised_at && request.status === "claimed" ? ` · ${relTime(request.promised_at, now)}` : ""}
            </p>
            <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1">
              <StatusBadge status={request.status} />
              {request.conditions?.map((c) => (
                <span key={c} className="text-2xs text-muted-foreground">
                  {conditionLabel(c)}
                </span>
              ))}
            </div>
          </div>
          <Button variant="ghost" size="icon-sm" aria-label="Close details" onClick={() => selectRequest(null)}>
            <X aria-hidden />
          </Button>
        </header>

        <div className="border-b border-line bg-panel px-5 py-3.5">
          <Stepper request={request} />
        </div>

        <div className="flex-1 space-y-3 overflow-y-auto p-4">
          <p className="text-sm text-ink-2">{request.description}</p>

          <div className="relative grid grid-cols-2 gap-2">
            <Track icon={Truck} label="Organization says" time={claimed && request.promised_at ? fmtTime(request.promised_at) : undefined}>
              <span title={request.delivery_notes ?? undefined}>
                {claimed ? `${orgName(board, request.organization_id)} ${story.delivered ? "reported delivery" : "promised by"}` : <span className="text-muted-foreground">Unclaimed</span>}
              </span>
            </Track>
            <Track icon={ClipboardCheck} label="Household / person says" accent time={latest ? fmtTime(latest.created_at) : undefined}>
              <span title={latest?.notes || undefined}>
                {latest ? (
                  <>
                    <span className={cn("font-medium", latest.received === true ? "text-promise-kept" : latest.received === false ? "text-promise-lapsed" : "text-muted-foreground")}>
                      {latest.received === true ? "Received" : latest.received === false ? "Did not arrive" : "Unconfirmed"}
                    </span>
                    <span className="text-muted-foreground">{` · ${latest.source === "survivor_call" ? "survivor call" : "human review"}`}</span>
                  </>
                ) : (
                  <span className="text-muted-foreground">Not yet · independent</span>
                )}
              </span>
            </Track>
            <span aria-hidden className="absolute left-1/2 top-1/2 grid size-5 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full border border-line-strong bg-surface font-mono text-[11px] text-ink-2">
              ≠
            </span>
          </div>
          <p className="flex items-start gap-2 text-xs text-ink-2">
            <ShieldCheck aria-hidden className="mt-px size-3.5 shrink-0 text-agent" />
            Delivery report ≠ receipt. Only the household or a human review resolves.
          </p>

          <NextStep request={request} board={board} />
          <Suggestions request={request} board={board} />
          <Activity request={request} board={board} />
        </div>
      </aside>
    </>
  );
}
