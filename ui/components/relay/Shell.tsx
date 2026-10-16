"use client";

import { BookOpen, Building2, CircleAlert, Compass, LayoutList, Phone, RefreshCw, RotateCcw, ShieldCheck, X } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { Callout, Pill, Select } from "./ui";
import { DemoGuide } from "./DemoGuide";
import { RequestDrawer } from "./RequestDrawer";

const NAV = [
  { href: "/response", label: "Response", icon: LayoutList },
  { href: "/organizations", label: "Organizations", icon: Building2 },
  { href: "/calls", label: "Calls", icon: Phone },
  { href: "/intelligence", label: "Intelligence", icon: BookOpen },
] as const;

function Nav({ orientation }: { orientation: "side" | "top" }) {
  const path = usePathname();
  return (
    <nav aria-label="Workspace" className={cn(orientation === "side" ? "flex flex-col gap-1" : "flex gap-1 overflow-x-auto")}>
      {NAV.map(({ href, label, icon: Icon }) => {
        const active = path === href || path.startsWith(`${href}/`);
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "flex items-center gap-2 rounded-lg px-3 py-2 text-sm font-medium whitespace-nowrap outline-none transition focus-visible:ring-3 focus-visible:ring-ring/50",
              active ? "bg-agent/10 text-agent" : "text-muted-foreground hover:bg-muted hover:text-ink",
            )}
          >
            <Icon aria-hidden className="size-4" />
            {label}
          </Link>
        );
      })}
    </nav>
  );
}

function Brand() {
  return (
    <Link href="/response" className="flex items-center gap-2 rounded-lg outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
      <span aria-hidden className="grid size-7 place-items-center rounded-lg bg-agent text-sm font-bold text-white">
        R
      </span>
      <span className="text-base font-semibold tracking-tight text-ink">Relay</span>
    </Link>
  );
}

function Dot({ on }: { on: boolean }) {
  return <span aria-hidden className={cn("size-2 shrink-0 rounded-full", on ? "bg-safety-ok" : "bg-muted-foreground/40")} />;
}

function Services() {
  const { mode, health } = useRelay();
  const live = mode === "live";
  const rows = [
    {
      name: "Database",
      on: live && Boolean(health?.live.surreal),
      text: !live ? "Simulated" : health ? (health.live.surreal ? "SurrealDB" : "In-memory") : "Unknown",
      title: !live ? "Simulated in browser" : health ? (health.live.surreal ? "SurrealDB" : `In-memory (${health.store})`) : "Not reported",
    },
    {
      name: "Voice",
      on: live && Boolean(health?.live.elevenlabs),
      text: live && health?.live.elevenlabs ? "ElevenLabs" : "Scripted",
      title: live && health?.live.elevenlabs ? "ElevenLabs connected" : "Scripted rehearsal only",
    },
    {
      name: "Evaluation",
      on: live && Boolean(health?.live.arize),
      text: live && health?.live.arize ? "Arize" : "Local",
      title: live && health?.live.arize ? "Arize export on" : "Local scoring, no Arize export",
    },
  ];
  return (
    <div className="space-y-2">
      <p className="text-[11px] font-medium uppercase tracking-wide text-muted-foreground">What is live</p>
      <ul className="space-y-1.5">
        {rows.map((r) => (
          <li key={r.name} title={r.title} className="flex items-center gap-2 text-xs">
            <Dot on={r.on} />
            <span className="font-medium text-ink">{r.name}</span>
            <span className="text-muted-foreground">{r.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Safeguards() {
  return (
    <details className="group rounded-lg border border-line bg-surface">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-3 py-2 text-xs font-medium text-ink outline-none focus-visible:ring-3 focus-visible:ring-ring/50">
        <ShieldCheck aria-hidden className="size-4 text-safety-ok" /> Safeguards
        <span aria-hidden className="ml-auto text-muted-foreground group-open:rotate-90">›</span>
      </summary>
      <ul className="space-y-1.5 border-t border-line px-3 py-2 text-xs text-muted-foreground">
        <li>Emergencies alert a person first.</li>
        <li>Calls need confirmed opt-in.</li>
        <li>Delivery reports never resolve requests.</li>
        <li>Only approved, de-identified lessons travel.</li>
        <li>No medical advice. No ranking people.</li>
        <li>Every action logs its run and disaster.</li>
      </ul>
    </details>
  );
}

function ScopeChip() {
  const { board } = useRelay();
  if (!board) return null;
  return (
    <span className="inline-flex flex-wrap items-center gap-x-2 rounded-lg border border-line bg-muted/60 px-2 py-1 font-mono text-[11px] text-muted-foreground" title="Every record on screen belongs to this run and disaster">
      <span>run {board.run_id}</span>
      <span aria-hidden>·</span>
      <span>disaster {board.disaster.id}</span>
    </span>
  );
}

function TopBar() {
  const { runs, disasters, runId, selectRun, board, orgId, setOrgId, mode, apiConfigured, setMode, setGuideOpen, guideOpen, resetDemo } = useRelay();
  const orgs = board?.organizations ?? [];
  const name = (disasterId: string) => disasters.find((d) => d.id === disasterId)?.name ?? disasterId;
  return (
    <div className="flex flex-wrap items-end gap-x-4 gap-y-2 border-b border-line bg-surface px-4 py-2.5 lg:px-6">
      <label className="space-y-0.5">
        <span className="block text-[11px] font-medium text-muted-foreground">Disaster</span>
        <Select value={runId} onChange={(e) => selectRun(e.target.value)} className="min-w-52">
          {runs.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {name(r.disaster_id)}
            </option>
          ))}
        </Select>
      </label>
      <label className="space-y-0.5">
        <span className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground">
          Acting as
          <span title="Demo organization selector. Not production authorization." className="rounded-md border border-line px-1 font-normal">
            simulated
          </span>
        </span>
        <Select value={orgId} onChange={(e) => setOrgId(e.target.value)} className="min-w-52" disabled={!orgs.length}>
          {(orgs.length ? orgs : [{ id: orgId, name: orgId }]).map((o) => (
            <option key={o.id} value={o.id}>
              {o.name}
            </option>
          ))}
        </Select>
      </label>
      <ScopeChip />
      <div className="ml-auto flex flex-wrap items-center gap-2">
        {mode === "live" ? <Pill tone="green">Live API</Pill> : <Pill tone="amber">Simulated data</Pill>}
        {apiConfigured ? (
          <Button variant="ghost" size="sm" onClick={() => setMode(mode === "live" ? "mock" : "live")}>
            {mode === "live" ? "Use simulated" : "Use live API"}
          </Button>
        ) : null}
        <Button variant="outline" size="sm" onClick={() => void resetDemo()}>
          <RotateCcw aria-hidden /> Reset demo
        </Button>
        <Button variant={guideOpen ? "default" : "outline"} size="sm" aria-pressed={guideOpen} onClick={() => setGuideOpen(!guideOpen)}>
          <Compass aria-hidden /> Demo guide
        </Button>
      </div>
    </div>
  );
}

function Banners() {
  const { connection, connectionError, retryConnection, mode, setMode, boardError, refresh, health, apiUrl } = useRelay();
  return (
    <div className="space-y-2 px-4 pt-3 empty:hidden lg:px-6">
      {connection === "error" ? (
        <Callout tone="danger" icon={CircleAlert} role="alert" title={mode === "live" ? "API offline" : "Backend failed"}>
          <p title={mode === "live" ? `Expected at ${apiUrl}` : undefined}>
            {connectionError}
            {mode === "live" ? " · run make api" : ""}
          </p>
          <div className="mt-2 flex gap-2">
            <Button size="sm" variant="outline" onClick={retryConnection}>
              <RefreshCw aria-hidden /> Retry
            </Button>
            {mode === "live" ? (
              <Button size="sm" variant="ghost" onClick={() => setMode("mock")}>
                Use simulated
              </Button>
            ) : null}
          </div>
        </Callout>
      ) : null}
      {boardError && connection === "ready" ? (
        <Callout tone="warn" icon={CircleAlert} role="alert" title="Showing last data">
          <p title={boardError}>
            Refresh failed.{" "}
            <button className="font-medium text-ink underline underline-offset-2" onClick={() => void refresh()}>
              Retry
            </button>
          </p>
        </Callout>
      ) : null}
      {mode === "live" && connection === "ready" && health === null ? (
        <div title="This API doesn't report which services are live.">
          <Callout tone="neutral" title="Service status unknown" />
        </div>
      ) : null}
    </div>
  );
}

function Toasts() {
  const { toasts, dismissToast } = useRelay();
  return (
    <div className="pointer-events-none fixed bottom-4 left-1/2 z-50 flex w-[min(92vw,28rem)] -translate-x-1/2 flex-col gap-2">
      {toasts.map((t) => (
        <div
          key={t.id}
          role={t.kind === "error" ? "alert" : "status"}
          className={cn(
            "pointer-events-auto flex items-start gap-2 rounded-lg border bg-surface px-3 py-2 text-sm shadow-lg animate-toast",
            t.kind === "error" ? "border-promise-lapsed/50" : t.kind === "success" ? "border-promise-kept/40" : "border-line",
          )}
        >
          <span className="min-w-0 flex-1 text-ink">{t.text}</span>
          <button aria-label="Dismiss" onClick={() => dismissToast(t.id)} className="rounded p-0.5 text-muted-foreground hover:text-ink">
            <X aria-hidden className="size-4" />
          </button>
        </div>
      ))}
    </div>
  );
}

export function Shell({ children }: { children: ReactNode }) {
  const { board, selectedRequestId } = useRelay();
  const path = usePathname();
  // Lessons need the full width; the request drawer is for the board, organizations and calls.
  const showDrawer = !path.startsWith("/intelligence");
  const drawerOpen = showDrawer && Boolean(selectedRequestId && board?.requests.some((r) => r.id === selectedRequestId));
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="hidden w-56 shrink-0 flex-col gap-5 border-r border-line bg-surface p-4 lg:sticky lg:top-0 lg:flex lg:h-screen lg:overflow-y-auto">
        <Brand />
        <Nav orientation="side" />
        <div className="mt-auto space-y-4">
          <Services />
          <Safeguards />
        </div>
      </aside>
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-2 lg:hidden">
        <Brand />
        <Nav orientation="top" />
      </header>
      <div className={cn("flex min-w-0 flex-1 flex-col transition-[margin] sm:duration-150", drawerOpen && "sm:mr-[26rem]")}>
        <p role="note" className="bg-ink px-4 py-1 text-center text-xs text-bg">
          Demo · synthetic data · simulated access · no real calls
        </p>
        <TopBar />
        <Banners />
        <DemoGuide />
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 py-4 outline-none lg:px-6 lg:py-5">
          {children}
        </main>
        <div className="space-y-4 border-t border-line bg-surface p-4 lg:hidden">
          <Services />
          <Safeguards />
        </div>
      </div>
      {showDrawer ? <RequestDrawer /> : null}
      <Toasts />
    </div>
  );
}
