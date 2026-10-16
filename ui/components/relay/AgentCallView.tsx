"use client";

// "Start the Agent Call": a judge plays the household and talks to Relay's live ElevenLabs follow-up agent.
// The browser never talks to the agent on its own authority: the API checks opt-in and delivery state, opens a
// server-owned session, and hands back a signed URL plus an opaque session id. That id rides along as the Custom LLM
// extra body, so every caller turn passes the code-owned emergency check before any model. Only an explicit answer,
// recorded by the server, can verify the request; this page just shows what the board says afterwards.
import { AudioLines, Loader2, Mic, MicOff, PhoneCall, PhoneOff, Plug, ShieldAlert, Sparkles } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type CSSProperties } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { categoryLabel, householdOf, orgName, outcomeLabel } from "@/lib/relay/selectors";
import type { Board, RelayRequest, VoiceSession } from "@/lib/relay/types";
import { CategoryIcon } from "./ResponseView";
import { DaytonaLogo, ElevenLabsLogo } from "./logos";
import { Callout, PageHeader, Panel, Select, StatusBadge, shortOrg } from "./ui";

type Phase = "idle" | "preparing" | "connecting" | "live" | "ending" | "ended" | "error";
type Line = { id: number; role: "agent" | "you"; text: string };
// Only the parts of the SDK conversation this page uses.
type Session = { endSession(): Promise<void>; setMicMuted(m: boolean): void; getInputVolume(): number; getOutputVolume(): number };

// Delivered (or reopened) requests for households that opted in. One with a call already active, e.g. interrupted
// by a reload, is left for a person to review: the API refuses a second session for it.
const eligible = (board: Board) =>
  board.requests.filter(
    (r) =>
      (r.status === "awaiting_verification" || r.status === "reopened") &&
      householdOf(board, r.survivor_id)?.call_opt_in === true &&
      !board.calls.some((c) => c.request_id === r.id && c.status === "active"),
  );

const TRY = [
  { say: "“Yes, it all arrived.”", then: "Resolves the request" },
  { say: "“No, nobody came.”", then: "Reopens it and alerts a person" },
  { say: "“Someone is hurt, we need help.”", then: "Emergency line first, then a person" },
];

const sessionKey = (requestId: string) => `agent-call:${requestId}:${crypto.randomUUID()}`;
const hoursFromNow = (h: number) => new Date(Date.now() + h * 3600_000).toISOString();

const clock = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

/* ------------------------------------------------------------------ the orb */

function Orb({ phase, speaking, level }: { phase: Phase; speaking: boolean; level: React.RefObject<HTMLDivElement | null> }) {
  const live = phase === "live";
  const c = speaking ? "var(--st-verify)" : "var(--st-respond)";
  return (
    <div ref={level} className="relative grid size-56 place-items-center" style={{ "--c": c, "--v": 0 } as CSSProperties}>
      {/* rings scale with the live audio level (written to --v without re-rendering) */}
      <span aria-hidden className={cn("absolute inset-0 rounded-full transition-colors duration-500", live ? "bg-[color-mix(in_srgb,var(--c)_8%,transparent)]" : "bg-hover")} style={{ transform: "scale(calc(0.86 + var(--v) * 0.22))" }} />
      <span aria-hidden className={cn("absolute inset-6 rounded-full transition-colors duration-500", live ? "bg-[color-mix(in_srgb,var(--c)_14%,transparent)]" : "bg-[var(--ds-gray-200)]")} style={{ transform: "scale(calc(0.9 + var(--v) * 0.16))" }} />
      {phase === "connecting" ? <span aria-hidden className="absolute inset-0 animate-call-ring rounded-full" /> : null}
      <span
        className={cn(
          "relative grid size-28 place-items-center rounded-full shadow-[var(--ds-shadow-border-medium)] transition-colors duration-500",
          live ? "bg-[var(--c)] text-white" : "bg-panel text-ink",
        )}
      >
        {phase === "connecting" || phase === "preparing" ? (
          <Loader2 aria-hidden className="size-8 animate-spin" />
        ) : live && speaking ? (
          <AudioLines aria-hidden className="size-9" />
        ) : live ? (
          <Mic aria-hidden className="size-9" />
        ) : (
          <PhoneCall aria-hidden className="size-9" />
        )}
      </span>
    </div>
  );
}

/* ------------------------------------------------------------------ page */

export function AgentCallView() {
  const { board, mode, apiConfigured, setMode, api, runId, health, refresh, orgId, notify, connection } = useRelay();
  const [requestId, setRequestId] = useState<string>("");
  const [phase, setPhase] = useState<Phase>("idle");
  const [error, setError] = useState<string | null>(null);
  const [speaking, setSpeaking] = useState(false);
  const [muted, setMuted] = useState(false);
  const [lines, setLines] = useState<Line[]>([]);
  const [session, setSession] = useState<VoiceSession | null>(null);
  const [seconds, setSeconds] = useState(0);

  const conv = useRef<Session | null>(null);
  const level = useRef<HTMLDivElement>(null);
  const transcript = useRef<HTMLOListElement>(null);

  const list = board ? eligible(board) : [];
  const chosen = list.find((r) => r.id === requestId) ?? list[0] ?? null;
  const live = mode === "live";
  const agentReady = live && Boolean(health?.live.elevenlabs) && typeof api.startVoiceSession === "function";
  const inCall = phase === "connecting" || phase === "live" || phase === "ending";

  // Hang up if the judge leaves the page mid-call.
  useEffect(() => () => void conv.current?.endSession().catch(() => {}), []);

  // Call timer.
  useEffect(() => {
    if (phase !== "live") return;
    const t = setInterval(() => setSeconds((s) => s + 1), 1000);
    return () => clearInterval(t);
  }, [phase]);

  // Audio level → CSS variable, once per frame, without re-rendering React.
  useEffect(() => {
    if (phase !== "live") return;
    let raf = 0;
    const tick = () => {
      const c = conv.current;
      const v = c ? Math.min(1, (speaking ? c.getOutputVolume() : c.getInputVolume()) * 2.2) : 0;
      level.current?.style.setProperty("--v", v.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [phase, speaking]);

  useEffect(() => {
    transcript.current?.lastElementChild?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [lines.length]);

  // After the call the outcome arrives by the signed webhook; keep the board fresh until the call completes.
  const call = session && board ? board.calls.find((c) => c.id === session.call_id) : undefined;
  const settled = call?.status === "completed";
  useEffect(() => {
    if (phase !== "ended" || settled) return;
    const t = setInterval(() => void refresh(), 2000);
    const stop = setTimeout(() => clearInterval(t), 90_000);
    return () => {
      clearInterval(t);
      clearTimeout(stop);
    };
  }, [phase, settled, refresh]);

  /** Give the judge something to call about: a delivered request for a household that opted in. */
  async function prepare() {
    if (!board) return;
    setPhase("preparing");
    setError(null);
    try {
      const survivor = board.survivors.find((s) => s.call_opt_in);
      if (!survivor) throw new Error("No household in this run has opted in to calls.");
      let req: RelayRequest | undefined = board.requests.find((r) => householdOf(board, r.survivor_id)?.call_opt_in && (r.status === "open" || r.status === "claimed"));
      if (!req) {
        const res = await api.report(runId, { disaster_id: board.disaster.id, survivor_id: survivor.id, text: "We need food for the family." });
        req = res.requests[0];
        if (!req) throw new Error(res.message ?? "The report did not create a request.");
      }
      const org = board.organizations.find((o) => o.id === orgId && o.capabilities.includes(req!.category)) ?? board.organizations.find((o) => o.capabilities.includes(req!.category));
      if (!org) throw new Error(`No organization can supply ${categoryLabel(req.category).toLowerCase()}.`);
      if (req.status === "open") req = await api.claim(runId, req.id, { organization_id: org.id, promised_at: hoursFromNow(2) });
      req = await api.deliver(runId, req.id, { organization_id: req.organization_id ?? org.id, notes: "Delivered; household to confirm by phone." });
      await refresh();
      // A fresh delivery means a fresh call: drop the previous session so the panel and the button agree.
      setSession(null);
      setLines([]);
      setError(null);
      setRequestId(req.id);
      setPhase("idle");
    } catch (e) {
      setPhase("idle");
      notify("error", e instanceof Error ? e.message : "Could not prepare a delivery.");
    }
  }

  async function start() {
    if (!chosen || !api.startVoiceSession || inCall) return;
    setError(null);
    setLines([]);
    setSeconds(0);
    setSession(null);
    setPhase("connecting");
    try {
      // Ask for the microphone first so a denial gives a clear message before any session is opened.
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((t) => t.stop());
      const s = await api.startVoiceSession(runId, chosen.id, { idempotency_key: sessionKey(chosen.id) });
      setSession(s);
      if (!s.signed_url) throw new Error("The API has no ElevenLabs agent configured, so there is no one to talk to.");
      const { Conversation } = await import("@elevenlabs/client");
      let n = 0;
      conv.current = (await Conversation.startSession({
        signedUrl: s.signed_url,
        connectionType: "websocket",
        customLlmExtraBody: s.custom_llm_extra_body,
        onConnect: () => setPhase("live"),
        onDisconnect: () => {
          conv.current = null;
          setSpeaking(false);
          setPhase((p) => (p === "error" ? p : "ended"));
          void refresh();
        },
        onError: (message: string) => {
          setError(message);
          setPhase("error");
        },
        onModeChange: ({ mode: m }: { mode: string }) => setSpeaking(m === "speaking"),
        onMessage: ({ message, source }: { message: string; source: "user" | "ai" }) => {
          if (message.trim()) setLines((l) => [...l, { id: n++, role: source === "ai" ? "agent" : "you", text: message }]);
        },
      })) as unknown as Session;
      void refresh();
    } catch (e) {
      conv.current = null;
      const msg = e instanceof Error ? e.message : String(e);
      setError(/permission|denied|notallowed/i.test(msg) ? "Microphone access was blocked. Allow it in the browser and try again." : msg);
      setPhase("error");
      void refresh();
    }
  }

  async function hangUp() {
    setPhase("ending");
    await conv.current?.endSession().catch(() => {});
  }

  function toggleMute() {
    conv.current?.setMicMuted(!muted);
    setMuted(!muted);
  }

  /* ---------------------------------------------------------------- render */

  const status =
    phase === "preparing"
      ? "Preparing a delivery"
      : phase === "connecting"
        ? "Connecting to the agent"
        : phase === "live"
          ? speaking
            ? "Agent speaking"
            : muted
              ? "Muted"
              : "Listening"
          : phase === "ending"
            ? "Hanging up"
            : phase === "ended"
              ? "Call ended"
              : phase === "error"
                ? "Call could not continue"
                : "Ready";

  const outcome = call?.status === "completed" ? outcomeLabel(call.outcome) : null;
  // During and after a call, show the request this session is about (it leaves the eligible list while active).
  const current = (session && board ? board.requests.find((r) => r.id === session.request_id) : undefined) ?? chosen;
  const emergency = call?.outcome === "emergency_escalated";

  return (
    <div className="@container space-y-5">
      <PageHeader
        title="Start the Agent Call"
        subtitle="You are the household. Relay's voice agent calls to check that help actually arrived."
        actions={
          <span className="inline-flex items-center gap-3 text-xs font-medium text-ink-2">
            <span className="inline-flex items-center gap-1.5">
              <ElevenLabsLogo aria-hidden className="size-3" /> ElevenLabs
            </span>
            <span className="inline-flex items-center gap-1.5">
              <DaytonaLogo aria-hidden className="size-3" /> Daytona
            </span>
            <span className="inline-flex items-center gap-1.5">
              <span aria-hidden className={cn("size-1.5 rounded-full", agentReady ? "bg-promise-kept" : "bg-line-strong")} />
              {agentReady ? "Agent online" : "Agent offline"}
            </span>
          </span>
        }
      />

      {!live ? (
        <Callout tone="neutral" icon={Plug} title="The agent runs through the Relay API">
          {apiConfigured ? (
            <div className="mt-2">
              <Button size="sm" onClick={() => setMode("live")}>
                <Plug aria-hidden /> Connect to the API
              </Button>
            </div>
          ) : (
            <p>
              Start it with <code className="font-mono text-[12px]">make serve</code> and set <code className="font-mono text-[12px]">NEXT_PUBLIC_RELAY_API_URL</code> for the UI.
            </p>
          )}
        </Callout>
      ) : connection === "ready" && !agentReady ? (
        <Callout tone="warn" icon={Plug} title="ElevenLabs is not configured on the API">
          <p>
            Set <code className="font-mono text-[12px]">ELEVENLABS_API_KEY</code> and <code className="font-mono text-[12px]">ELEVENLABS_AGENT_ID</code> for the API (see <code className="font-mono text-[12px]">calls/LIVE.md</code>), then reload.
          </p>
        </Callout>
      ) : null}

      <div className="grid gap-4 @4xl:grid-cols-[minmax(0,1.5fr)_minmax(18rem,1fr)]">
        {/* ---------------------------------------------------------- the call */}
        <section aria-label="Agent call" className="flex min-h-[34rem] flex-col overflow-hidden rounded-[12px] border border-line bg-panel shadow-[var(--ds-shadow-small)]">
          <div className="flex flex-1 flex-col items-center justify-center gap-5 bg-canvas px-6 py-10 [background-image:radial-gradient(var(--ds-gray-400)_1px,transparent_1px)] [background-size:20px_20px]">
            <Orb phase={phase} speaking={speaking} level={level} />
            <div className="text-center" aria-live="polite">
              <p className={cn("text-base font-semibold tracking-[-0.01em]", phase === "error" ? "text-promise-lapsed" : "text-ink")}>{status}</p>
              <p className="num mt-0.5 text-xs text-muted-foreground">{phase === "live" || phase === "ended" ? clock(seconds) : current ? `${categoryLabel(current.category)} · ${householdOf(board!, current.survivor_id)?.display_name ?? "Household"}` : " "}</p>
            </div>
            <div className="flex items-center gap-2">
              {inCall ? (
                <>
                  <Button variant="outline" size="lg" className="px-4" aria-pressed={muted} onClick={toggleMute} disabled={phase !== "live"}>
                    {muted ? <MicOff aria-hidden /> : <Mic aria-hidden />} {muted ? "Unmute" : "Mute"}
                  </Button>
                  <Button size="lg" className="bg-promise-lapsed px-5 text-white hover:bg-[color-mix(in_srgb,var(--promise-lapsed)_88%,black)]" onClick={() => void hangUp()} disabled={phase === "ending"}>
                    <PhoneOff aria-hidden /> End call
                  </Button>
                </>
              ) : (
                <Button size="lg" className="h-11 px-6 text-sm" disabled={!agentReady || !chosen || phase === "preparing"} onClick={() => void start()}>
                  <PhoneCall aria-hidden /> {phase === "ended" || phase === "error" ? "Call again" : "Start the call"}
                </Button>
              )}
            </div>
            {error ? (
              <p role="alert" className="max-w-md text-center text-xs text-promise-lapsed">
                {error}
              </p>
            ) : null}
          </div>

          {/* transcript */}
          <div className="border-t border-line">
            <p className="px-4 pt-3 text-sm font-semibold tracking-[-0.01em] text-ink">Conversation</p>
            {session?.disclosure && (inCall || phase === "ended") ? (
              <p className="mx-4 mt-2 rounded-md bg-hover px-2.5 py-1.5 text-xs text-ink-2">
                <span className="font-medium text-ink">Disclosure read first: </span>
                {session.disclosure}
              </p>
            ) : null}
            <ol ref={transcript} aria-label="Call transcript" aria-live="polite" className="max-h-72 space-y-2 overflow-y-auto px-4 py-3">
              {lines.map((l) => (
                <li key={l.id} className={cn("flex animate-arrive", l.role === "you" && "justify-end")}>
                  <span
                    className={cn(
                      "max-w-[80%] rounded-[10px] px-3 py-2 text-sm leading-snug",
                      l.role === "agent" ? "bg-[color-mix(in_srgb,var(--st-verify)_10%,transparent)] text-ink" : "bg-ink text-panel",
                    )}
                  >
                    <span className="mb-0.5 block text-[10px] font-medium uppercase tracking-wider opacity-60">{l.role === "agent" ? "Relay agent" : "You"}</span>
                    {l.text}
                  </span>
                </li>
              ))}
              {!lines.length ? <li className="py-4 text-center text-xs text-muted-foreground">{inCall ? "Say hello when the agent finishes its introduction." : "The transcript appears here during the call."}</li> : null}
            </ol>
          </div>
        </section>

        {/* ---------------------------------------------------------- context */}
        <div className="space-y-4">
          <Panel
            title="Calling about"
            aside={
              live && board && current && !inCall ? (
                <Button variant="ghost" size="xs" disabled={phase === "preparing"} onClick={() => void prepare()}>
                  {phase === "preparing" ? <Loader2 aria-hidden className="animate-spin" /> : <Sparkles aria-hidden />} New delivery
                </Button>
              ) : undefined
            }
          >
            {board && current ? (
              <div className="space-y-3">
                {list.length > 1 && !session ? (
                  <Select aria-label="Request to call about" value={chosen.id} onChange={(e) => setRequestId(e.target.value)} disabled={inCall} className="w-full">
                    {list.map((r) => (
                      <option key={r.id} value={r.id}>
                        {categoryLabel(r.category)} · {householdOf(board, r.survivor_id)?.display_name ?? "Household"}
                      </option>
                    ))}
                  </Select>
                ) : null}
                <div className="flex items-start gap-3">
                  <span className="grid size-9 shrink-0 place-items-center rounded-[8px] bg-[color-mix(in_srgb,var(--st-verify)_12%,transparent)] text-st-verify">
                    <CategoryIcon category={current.category} className="size-4" />
                  </span>
                  <div className="min-w-0 flex-1">
                    <p className="text-sm font-semibold text-ink">{categoryLabel(current.category)}</p>
                    <p className="text-xs text-muted-foreground">
                      {householdOf(board, current.survivor_id)?.display_name ?? "Household"} · delivered by {shortOrg(orgName(board, current.organization_id))}
                    </p>
                  </div>
                  <StatusBadge status={current.status} short />
                </div>
              </div>
            ) : board ? (
              <div className="space-y-3 text-sm text-ink-2">
                <p>Nothing is waiting for a household to confirm yet.</p>
                <Button variant="outline" disabled={!live || phase === "preparing"} onClick={() => void prepare()}>
                  {phase === "preparing" ? <Loader2 aria-hidden className="animate-spin" /> : <Sparkles aria-hidden />} Prepare a delivery to check
                </Button>
              </div>
            ) : (
              <p className="text-sm text-muted-foreground">Loading…</p>
            )}
          </Panel>

          <Panel title="Try saying">
            <ul className="space-y-2.5">
              {TRY.map((t) => (
                <li key={t.say} className="flex items-baseline justify-between gap-3 text-sm">
                  <span className="font-medium text-ink">{t.say}</span>
                  <span className="shrink-0 text-xs text-muted-foreground">{t.then}</span>
                </li>
              ))}
            </ul>
          </Panel>

          <Panel title="Result" aside={session ? <span className="font-mono">{session.call_id}</span> : undefined}>
            {emergency ? (
              <Callout tone="danger" icon={ShieldAlert} title="Emergency: a person on the team was alerted">
                <p>The agent gave the emergency line before anything else. No model decided this.</p>
              </Callout>
            ) : outcome ? (
              <div className="space-y-2">
                <p className={cn("text-sm font-semibold", outcome.tone === "good" ? "text-promise-kept" : outcome.tone === "bad" || outcome.tone === "alert" ? "text-promise-lapsed" : "text-ink")}>{outcome.label}</p>
                {current ? (
                  <p className="flex items-center gap-2 text-xs text-ink-2">
                    Request is now <StatusBadge status={current.status} />
                  </p>
                ) : null}
                <Link href="/response" className="inline-block text-xs font-medium text-agent underline-offset-4 hover:underline">
                  See it on the board
                </Link>
              </div>
            ) : phase === "ended" ? (
              <p className="flex items-center gap-2 text-sm text-ink-2">
                <Loader2 aria-hidden className="size-3.5 animate-spin" /> Waiting for the agent&apos;s report
              </p>
            ) : (
              <p className="text-sm text-muted-foreground">Only a clear yes or no changes the request. Anything else leaves it for a person.</p>
            )}
          </Panel>
        </div>
      </div>
    </div>
  );
}
