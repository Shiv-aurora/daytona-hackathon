"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Image from "next/image";
import { usePathname, useRouter } from "next/navigation";
import type { Proposal } from "@/lib/contracts";
import { MockAdapter, type ConsoleAdapter } from "@/lib/adapter";
import { atTime, nextNeedle } from "@/lib/clock";
import { evidenceOf, profileOf } from "@/lib/evidence";
import { LiveAdapter } from "@/lib/live/client";
import { ReplayAdapter } from "@/lib/replay/adapter";
import { mockSnapshot } from "@/lib/mock";
import { hideMock, runLabel } from "@/lib/mode";
import { fmtClock, fmtShort } from "@/lib/sim";
import { cn } from "@/lib/utils";
import { useRunSnapshot } from "@/lib/use-run";
import { callsOf, goalOf, policyLine } from "@/lib/view";
import { GoalBar } from "./GoalBar";
import { HouseholdTimeline } from "./HouseholdTimeline";
import { ProposalInbox } from "./ProposalInbox";
import { DecisionPanel } from "./ProposalCard";
import { ProveIt } from "./ProveIt";
import { SimControls } from "./SimControls";
import { Toast, type ToastMsg } from "./Toast";
import { TraceStrip } from "./TraceStrip";
import { KIND_OF, Tag } from "./bits";

const TYPING = new Set(["INPUT", "TEXTAREA", "SELECT"]);
const byDeadline = (a: Proposal, b: Proposal) => (a.due_ts ?? Infinity) - (b.due_ts ?? Infinity) || a._id.localeCompare(b._id);
const PLAY_STEP_H = 0.5; // sim hours per tick while playing: one sim day in ~10 seconds
const PLAY_TICK_MS = 200;
const reducedMotion = () => typeof window.matchMedia !== "function" || window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const pause = (ms: number) => new Promise((r) => setTimeout(r, ms));

type Props = {
  /** Relay base URL for live mode; null/undefined renders the built-in mock run (no backend). */
  relay?: string | null;
  /** Public Replay: a completed run read from recorded snapshots, decisions sandboxed in this tab. */
  replay?: boolean;
  initialRun?: string;
  adapter?: ConsoleAdapter;
};

export function Console({ relay = null, replay = false, initialRun, adapter }: Props) {
  const isReplay = replay || adapter instanceof ReplayAdapter;
  // Live runs follow the runtime's head; replay and mock runs have a presenter playback clock.
  const live = !isReplay && (Boolean(relay) || (adapter !== undefined && !(adapter instanceof MockAdapter)));
  const remote = live || isReplay; // runs are listed by a backend rather than the built-in mock
  const router = useRouter();
  const pathname = usePathname();
  const [source] = useState<ConsoleAdapter>(() => adapter ?? (isReplay ? new ReplayAdapter() : relay ? new LiveAdapter(relay) : new MockAdapter()));
  const [runs, setRuns] = useState<string[]>(remote ? [] : [mockSnapshot.run.run_id]);
  const [runId, setRunId] = useState<string | null>(initialRun ?? (remote ? null : mockSnapshot.run.run_id));
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [householdId, setHouseholdId] = useState<string | null>(null);
  const [dismissFor, setDismissFor] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null); // proposal id with a decision in flight
  const [leaving, setLeaving] = useState<string | null>(null);
  const [justDecided, setJustDecided] = useState<{ id: string; approved: boolean } | null>(null);
  const [toast, setToast] = useState<ToastMsg | null>(null);
  const [celebrate, setCelebrate] = useState(0);
  const [tab, setTab] = useState<"console" | "prove">("console");
  // Playback clock (recorded or mock runs). Live runs always show the head.
  const [clock, setClock] = useState<{ run: string; t: number } | null>(null);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    source
      .runs()
      .then((rs) => {
        setRuns(rs.map((r) => r.run_id));
        setRunId((cur) => cur ?? rs[0]?.run_id ?? null);
      })
      .catch((e: Error) => setActionError(`Could not list runs: ${e.message}`));
  }, [source]);

  const { snap: raw, error, reload } = useRunSnapshot(source, runId, live ? 3000 : 0);
  const head = raw?.now_ts ?? 0;
  const t = live || !raw ? head : Math.min(clock?.run === runId ? clock.t : (raw.start_ts ?? head), head);
  const snap = useMemo(() => (raw && !live ? atTime(raw, t) : raw), [raw, live, t]);
  const atHead = live || t >= head;
  const needleAt = raw && !live ? nextNeedle(raw, t) : null;

  const moveTo = useCallback((to: number) => runId && setClock({ run: runId, t: Math.min(to, head) }), [runId, head]);

  const isPlaying = playing && !atHead; // playback stops by itself at the run head
  useEffect(() => {
    if (!isPlaying) return;
    const id = setTimeout(() => moveTo(t + PLAY_STEP_H), PLAY_TICK_MS);
    return () => clearTimeout(id);
  }, [isPlaying, t, moveTo]);

  function switchRun(next: string) {
    setRunId(next);
    setSelectedId(null);
    setHouseholdId(null);
    setDismissFor(null);
    setActionError(null);
    setPlaying(false);
    router.replace(`${pathname}?run=${encodeURIComponent(next)}`);
  }

  // Proposals sort by deadline only; Relay never ranks people.
  const pending = useMemo(() => (snap?.proposals ?? []).filter((p) => p.status === "pending").sort(byDeadline), [snap]);
  const decided = useMemo(() => (snap?.proposals ?? []).filter((p) => p.status !== "pending").sort(byDeadline), [snap]);
  const selected = pending.find((p) => p._id === selectedId) ?? pending[0] ?? null;
  const goal = useMemo(() => (snap ? goalOf(snap) : null), [snap]);

  function select(p: Proposal) {
    setSelectedId(p._id);
    setHouseholdId(p.household_id);
  }
  async function decide(p: Proposal, status: "approved" | "dismissed", reason?: string) {
    if (!runId || !snap || busy || p.status !== "pending") return;
    if (status === "dismissed" && !reason?.trim()) return; // the dismiss control requires a reason
    setDismissFor(null);
    setActionError(null);
    setBusy(p._id);
    setLeaving(p._id);
    if (!reducedMotion()) await pause(200); // let the card slide out first
    const name = snap.households.find((h) => h.household_id === p.household_id)?.name ?? "this household";
    try {
      await source.decide(runId, p._id, status, reason, live ? undefined : snap.now_ts);
      setHouseholdId(p.household_id);
      setJustDecided({ id: p._id, approved: status === "approved" });
      setToast({ id: Date.now(), text: status === "approved" ? `Approved ${KIND_OF(p.kind, p.queue).label.toLowerCase()} for ${name}` : `Dismissed: ${reason}` });
      if (status === "approved") setCelebrate((c) => c + 1);
    } catch (e) {
      setActionError(`Could not ${status === "approved" ? "approve" : "dismiss"} ${p._id}: ${(e as Error).message}. Showing the backend's current state.`);
    } finally {
      await reload(); // reconcile with the backend either way; never assume the transition happened
      setLeaving(null);
      setBusy(null);
    }
  }
  const clearToast = useCallback(() => {
    setToast(null);
    setJustDecided(null);
  }, []);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement;
      if (e.metaKey || e.ctrlKey || e.altKey || TYPING.has(el.tagName) || el.isContentEditable || dismissFor) return;
      const key = e.key.toLowerCase();
      const i = selected ? pending.indexOf(selected) : -1;
      if (key === "j" || key === "k") {
        const next = pending[Math.max(0, Math.min(pending.length - 1, i + (key === "j" ? 1 : -1)))];
        if (next) {
          select(next);
          document.getElementById(`proposal-${next._id}`)?.focus();
        }
      } else if (key === "a" && selected && !busy) decide(selected, "approved");
      else if (key === "d" && selected && !busy) setDismissFor(selected._id);
      else if (key === "n" && needleAt !== null) moveTo(needleAt);
      else if (key === "p" && !live && !atHead) setPlaying(!isPlaying);
      else return;
      e.preventDefault();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  const header = (
    <header className="flex flex-wrap items-center gap-x-5 gap-y-1 border-b bg-surface px-5 py-2.5">
      <h1 className="flex items-center">
        <Image src="/relay-logo.png" alt="Relay" width={342} height={128} priority className="h-7 w-auto" />
        <span className="sr-only"> coordinator console</span>
      </h1>
      {snap && (
        <time className="flex items-center gap-2" aria-label={`Simulated time ${fmtClock(snap.run.day0, snap.now_ts)}`}>
          <Tag tone="teal" className="text-sm">
            Day {Math.floor(snap.now_ts / 24)}
          </Tag>
          <span className="font-mono text-lg font-semibold tabular-nums">{fmtShort(snap.run.day0, snap.now_ts)}</span>
        </time>
      )}
      {snap && !live && (
        <SimControls playing={isPlaying} atHead={atHead} canNeedle={needleAt !== null} onPlay={setPlaying} onStep={(h) => moveTo(t + h)} onNeedle={() => needleAt !== null && moveTo(needleAt)} />
      )}
      <label className="flex items-center gap-2 text-sm text-muted-foreground">
        Run
        <select
          value={runId ?? ""}
          onChange={(e) => switchRun(e.target.value)}
          className="rounded border bg-surface px-2 py-1 font-mono text-sm text-ink"
          disabled={runs.length < 2}
        >
          {runId && !runs.includes(runId) && <option value={runId}>{runLabel(runId)}</option>}
          {runs.map((r) => (
            <option key={r} value={r}>
              {runLabel(r)}
            </option>
          ))}
        </select>
      </label>
      <div role="tablist" aria-label="View" className="ml-auto flex rounded-lg border p-0.5">
        {(
          [
            ["console", "Console"],
            ["prove", "Prove it"],
          ] as const
        ).map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={cn("rounded-md px-3 py-1 text-sm font-medium", tab === key ? "bg-agent text-primary-foreground" : "text-muted-foreground hover:text-ink")}
          >
            {label}
          </button>
        ))}
      </div>
      {live ? (
        <Tag tone="green" glyph="●" title="Reading this run from the Relay run API">
          Live
        </Tag>
      ) : isReplay ? (
        <Tag tone="teal" glyph="▶" title="A completed run read from recorded snapshots. Your decisions stay in this browser tab.">
          Replay
        </Tag>
      ) : (
        !hideMock() && (
          <Tag tone="amber" glyph="◔" title="Simulated households and no backend. Decisions stay in this browser tab.">
            Mock data
          </Tag>
        )
      )}
    </header>
  );

  if (!runId) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {header}
        <p className={actionError ? "p-8 text-promise-lapsed" : "p-8 text-muted-foreground"}>
          {actionError ?? (remote ? "Looking for runs…" : "Loading…")}{" "}
          {remote && <a href="/console?mode=mock" className="underline">Open the mock run instead</a>}
        </p>
      </div>
    );
  }
  if (!snap || !goal) {
    return (
      <div className="flex min-h-0 flex-1 flex-col">
        {header}
        <p className={error ? "p-8 text-promise-lapsed" : "p-8 text-muted-foreground"} role={error ? "alert" : undefined}>
          {error ? `Could not load run ${runLabel(runId)}: ${error}.${live ? " Retrying…" : ""}` : isReplay ? `Loading the recorded run ${runLabel(runId)}…` : `Loading run ${runLabel(runId)}…`}{" "}
          {error && <a href="/console?mode=mock" className="underline">Open the mock run instead</a>}
        </p>
      </div>
    );
  }

  const hid = householdId ?? selected?.household_id ?? snap.households[0]?.household_id;
  const household = snap.households.find((h) => h.household_id === hid);
  const applied = new Set(household?.applied_event_ids ?? []);
  const householdProposal = pending.find((p) => p.household_id === hid) ?? decided.find((p) => p.household_id === hid);
  // The decision panel follows the selected proposal, or the shown household's pending one.
  const focus = (selected && selected.household_id === hid ? selected : pending.find((p) => p.household_id === hid)) ?? null;
  // The latest policy change, shown on a proposal made under it.
  const policy = [...snap.policy_changes].sort((a, b) => b.version - a.version)[0];

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      {header}
      {(actionError || error) && (
        <p role="alert" className="border-b bg-surface px-5 py-1.5 text-base text-promise-lapsed">
          {actionError ?? `Live update failed: ${error}. Showing the last good data for this run; retrying.`}
        </p>
      )}
      {tab === "prove" ? (
        <ProveIt comparison={raw?.comparison} />
      ) : (
        <>
          <GoalBar goal={goal} day0={snap.run.day0} onSelectHousehold={setHouseholdId} celebrate={celebrate} />
          <main id="main" className="grid min-h-0 flex-1 grid-cols-1 gap-3 p-3 lg:grid-cols-[22rem_1fr]">
            <ProposalInbox
              snap={snap}
              pending={pending}
              decided={decided}
              selectedId={focus?._id ?? null}
              busyId={busy}
              leavingId={leaving}
              justDecided={justDecided}
              onSelect={select}
            />
            <div className="flex min-h-0 flex-col gap-3">
              {focus && (
                <DecisionPanel
                  key={focus._id}
                  p={focus}
                  household={household}
                  facts={evidenceOf(focus, snap)}
                  profile={household ? profileOf(household, snap.events) : []}
                  policyLine={policy && policy.ts <= focus.ts ? policyLine(policy) : null}
                  day0={snap.run.day0}
                  runId={snap.run.run_id}
                  now={snap.now_ts}
                  dismissOpen={dismissFor === focus._id}
                  busy={busy !== null}
                  onDismissOpen={(o) => setDismissFor(o ? focus._id : null)}
                  onApprove={() => decide(focus, "approved")}
                  onDismiss={(r) => decide(focus, "dismissed", r)}
                />
              )}
              {household ? (
                <HouseholdTimeline
                  household={household}
                  events={snap.events.filter((e) => applied.has(e._id) && e.ts <= snap.now_ts)}
                  promises={snap.promises.filter((p) => p.household_id === household.household_id && p.run_id === snap.run.run_id)}
                  registry={snap.registry.find((r) => r.household_id === household.household_id)}
                  calls={callsOf(snap, household.household_id)}
                  citedIds={householdProposal?.cited_event_ids ?? []}
                  runId={snap.run.run_id}
                  day0={snap.run.day0}
                  now={snap.now_ts}
                  nameShown={focus !== null}
                />
              ) : (
                <p className="rounded-lg border bg-surface p-6 text-base text-muted-foreground">No household selected.</p>
              )}
            </div>
          </main>
          <TraceStrip
            trace={snap.system_events}
            day0={snap.run.day0}
            now={snap.now_ts}
            names={Object.fromEntries(snap.households.map((h) => [h.household_id, h.name ?? h.household_id]))}
            policyVersion={policy?.version ?? 1}
          />
        </>
      )}
      <Toast msg={toast} onDone={clearToast} />
    </div>
  );
}
