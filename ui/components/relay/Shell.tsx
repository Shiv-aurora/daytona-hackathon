"use client";

import { BookOpen, Building2, ChevronsUpDown, CircleAlert, Compass, LayoutList, Moon, Phone, Play, RefreshCw, RotateCcw, ShieldCheck, Sun, X, type LucideIcon } from "lucide-react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSyncExternalStore, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { useRelay } from "@/lib/relay/context";
import { Callout, Monogram, shortOrg } from "./ui";
import { DemoGuide } from "./DemoGuide";
import { RequestDrawer } from "./RequestDrawer";

const NAV: { href: string; label: string; icon: LucideIcon; badge?: "requests" | "calls" | "lessons" }[] = [
  { href: "/live", label: "Live demo", icon: Play },
  { href: "/response", label: "Response", icon: LayoutList, badge: "requests" },
  { href: "/organizations", label: "Organizations", icon: Building2 },
  { href: "/calls", label: "Calls", icon: Phone, badge: "calls" },
  { href: "/intelligence", label: "Intelligence", icon: BookOpen, badge: "lessons" },
];

function useBadges() {
  const { board } = useRelay();
  if (!board) return {} as Record<string, number>;
  return {
    requests: board.requests.filter((r) => r.status === "open" || r.status === "reopened").length,
    calls: board.calls.filter((c) => c.status === "queued").length,
    lessons: board.lessons.filter((l) => l.source_disaster_id !== board.disaster.id && l.approved).length,
  } as Record<string, number>;
}

function Nav({ orientation }: { orientation: "side" | "top" }) {
  const path = usePathname();
  const badges = useBadges();
  return (
    <nav aria-label="Workspace" className={cn(orientation === "side" ? "flex flex-col gap-0.5" : "flex gap-1 overflow-x-auto")}>
      {NAV.map(({ href, label, icon: Icon, badge }) => {
        const active = path === href || path.startsWith(`${href}/`);
        const n = badge ? badges[badge] : 0;
        return (
          <Link
            key={href}
            href={href}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex h-8 items-center gap-2.5 rounded-md px-2.5 text-sm whitespace-nowrap outline-none transition-colors",
              active ? "bg-panel font-medium text-ink shadow-[0_0_0_1px_var(--border)]" : "text-ink-2 hover:bg-hover hover:text-ink",
            )}
          >
            {active && orientation === "side" ? <span aria-hidden className="absolute -left-2.5 top-2 h-4 w-[2px] rounded-full bg-agent" /> : null}
            <Icon aria-hidden className={cn("size-[15px]", active ? "text-agent" : "text-muted-foreground group-hover:text-ink-2")} />
            {label}
            {n ? (
              <span className="num ml-auto rounded-[4px] bg-hover px-1.5 text-2xs font-medium text-ink-2" aria-label={`${n} need attention`}>
                {n}
              </span>
            ) : null}
          </Link>
        );
      })}
    </nav>
  );
}

/** The mark: two relay nodes joined by a baton line. */
function Mark({ size = 22 }: { size?: number }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect width="24" height="24" rx="6" fill="var(--agent)" />
      <path d="M7.5 15.5c3.4 0 5-7 9-7" stroke="var(--panel)" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="7.5" cy="15.5" r="2.1" fill="var(--panel)" />
      <circle cx="16.5" cy="8.5" r="2.1" fill="var(--panel)" />
    </svg>
  );
}

function Brand() {
  return (
    <Link href="/live" className="flex items-center gap-2 rounded-md outline-none" aria-label="Relay home">
      <Mark />
      <span className="text-[15px] font-semibold tracking-[-0.02em] text-ink">Relay</span>
    </Link>
  );
}

/** Workspace switcher, in the Linear mould: the current disaster is the "workspace". */
function DisasterSwitcher() {
  const { runs, disasters, runId, selectRun, board } = useRelay();
  const name = (disasterId: string) => disasters.find((d) => d.id === disasterId)?.name ?? disasterId;
  const current = runs.find((r) => r.run_id === runId);
  const d = disasters.find((x) => x.id === (board?.disaster.id ?? current?.disaster_id));
  return (
    <label className="relative block">
      <span className="sr-only">Disaster</span>
      <span className="pointer-events-none flex items-center gap-2.5 rounded-md border border-line bg-panel px-2.5 py-2">
        <span aria-hidden className="grid size-6 shrink-0 place-items-center rounded-[5px] bg-ink font-mono text-[10px] font-medium text-panel">
          {(d?.kind ?? "dz").slice(0, 2).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className="block truncate text-[12.5px] font-medium text-ink">{d ? name(d.id) : "Loading…"}</span>
          <span className="block truncate text-[10.5px] text-muted-foreground">{d ? `${d.kind} · ${d.region}` : ""}</span>
        </span>
        <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      </span>
      <select
        value={runId}
        onChange={(e) => selectRun(e.target.value)}
        className="absolute inset-0 size-full cursor-pointer rounded-md opacity-0"
      >
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {name(r.disaster_id)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ActingAs() {
  const { board, orgId, setOrgId } = useRelay();
  const orgs = board?.organizations ?? [];
  const current = orgs.find((o) => o.id === orgId);
  return (
    <label className="relative block">
      <span className="label mb-1 flex items-center gap-1.5">
        Acting as
        <span title="Demo organization selector. Not production authorization." className="rounded-[4px] border border-dashed border-line-strong px-1 text-[9px] normal-case tracking-normal">
          simulated
        </span>
      </span>
      <span className="pointer-events-none flex items-center gap-2 rounded-md border border-line bg-panel px-2 py-1.5">
        <Monogram name={current?.name ?? orgId} active />
        <span className="min-w-0 flex-1 truncate text-[12.5px] text-ink">{current ? shortOrg(current.name) : orgId}</span>
        <ChevronsUpDown aria-hidden className="size-3.5 shrink-0 text-muted-foreground" />
      </span>
      <select
        aria-label="Acting as (simulated access)"
        value={orgId}
        onChange={(e) => setOrgId(e.target.value)}
        disabled={!orgs.length}
        className="absolute inset-x-0 bottom-0 h-[34px] w-full cursor-pointer opacity-0"
      >
        {(orgs.length ? orgs : [{ id: orgId, name: orgId }]).map((o) => (
          <option key={o.id} value={o.id}>
            {o.name}
          </option>
        ))}
      </select>
    </label>
  );
}

function Services() {
  const { mode, health } = useRelay();
  const live = mode === "live";
  const rows = [
    { name: "Database", on: live && Boolean(health?.live.surreal), text: !live ? "Simulated" : health ? (health.live.surreal ? "SurrealDB" : "In-memory") : "Unknown" },
    { name: "Voice", on: live && Boolean(health?.live.elevenlabs), text: live && health?.live.elevenlabs ? "ElevenLabs" : "Scripted" },
    { name: "Evaluation", on: live && Boolean(health?.live.arize), text: live && health?.live.arize ? "Arize" : "Local" },
  ];
  return (
    <div>
      <p className="label mb-1.5">What is live</p>
      <ul className="space-y-1">
        {rows.map((r) => (
          <li key={r.name} className="flex items-center gap-2 text-xs">
            <span aria-hidden className={cn("size-1.5 shrink-0 rounded-full", r.on ? "bg-safety-ok" : "border border-line-strong")} />
            <span className="text-ink-2">{r.name}</span>
            <span className="ml-auto text-muted-foreground">{r.text}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Safeguards() {
  return (
    <details className="group rounded-md border border-line bg-panel">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-1.5 text-xs font-medium text-ink outline-none">
        <ShieldCheck aria-hidden className="size-3.5 text-agent" /> Safeguards
        <span aria-hidden className="ml-auto text-muted-foreground transition-transform group-open:rotate-90">›</span>
      </summary>
      <ul className="space-y-1.5 border-t border-line px-2.5 py-2 text-xs text-muted-foreground">
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

const themeListeners = new Set<() => void>();
const subscribeTheme = (cb: () => void) => {
  themeListeners.add(cb);
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener("change", cb);
  return () => {
    themeListeners.delete(cb);
    mq.removeEventListener("change", cb);
  };
};
const currentTheme = (): "light" | "dark" => {
  const set = document.documentElement.dataset.theme;
  if (set === "light" || set === "dark") return set;
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
};

function ThemeToggle() {
  const theme = useSyncExternalStore(subscribeTheme, currentTheme, () => "light" as const);
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      aria-label={theme === "dark" ? "Switch to light theme" : "Switch to dark theme"}
      title={theme === "dark" ? "Light theme" : "Dark theme"}
      onClick={() => {
        const next = theme === "dark" ? "light" : "dark";
        document.documentElement.dataset.theme = next;
        try {
          localStorage.setItem("relay-theme", next);
        } catch {
          /* storage blocked: the choice just lasts for this page */
        }
        themeListeners.forEach((l) => l());
      }}
    >
      {theme === "dark" ? <Sun aria-hidden /> : <Moon aria-hidden />}
    </Button>
  );
}

/** One quiet strip above everything: what is simulated, which run/disaster is on screen, and the global actions. */
function StatusStrip() {
  const { board, mode, apiConfigured, setMode, guideOpen, setGuideOpen, resetDemo } = useRelay();
  return (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-1 border-b border-line bg-surface px-4 py-1.5 lg:px-6">
      <p role="note" className="flex items-center gap-2 text-[11px] text-ink-2">
        <span aria-hidden className={cn("size-1.5 rounded-full", mode === "live" ? "bg-safety-ok" : "bg-promise-due-soon")} />
        <span className="font-medium">{mode === "live" ? "Live API" : "Simulated data"}</span>
        <span className="text-muted-foreground">· synthetic data · simulated access · no real calls</span>
      </p>
      {board ? (
        <p className="font-mono text-[10.5px] text-muted-foreground" title="Every record on screen belongs to this run and disaster">
          run {board.run_id} · disaster {board.disaster.id}
        </p>
      ) : null}
      <div className="ml-auto flex items-center gap-1">
        {apiConfigured ? (
          <Button variant="ghost" size="xs" onClick={() => setMode(mode === "live" ? "mock" : "live")}>
            {mode === "live" ? "Use simulated" : "Use live API"}
          </Button>
        ) : null}
        <Button variant="ghost" size="xs" onClick={() => void resetDemo()}>
          <RotateCcw aria-hidden /> Reset demo
        </Button>
        <Button variant="ghost" size="xs" aria-pressed={guideOpen} onClick={() => setGuideOpen(!guideOpen)} className={cn(guideOpen && "bg-hover text-ink")}>
          <Compass aria-hidden /> Demo guide
        </Button>
        <ThemeToggle />
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
            "pointer-events-auto flex items-start gap-2 rounded-md border border-l-2 bg-panel px-3 py-2 text-sm shadow-lg animate-toast",
            t.kind === "error" ? "border-line border-l-promise-lapsed" : t.kind === "success" ? "border-line border-l-promise-kept" : "border-line border-l-line-strong",
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
  const cinematic = path.startsWith("/live");
  const showDrawer = !path.startsWith("/intelligence") && !cinematic;
  const drawerOpen = showDrawer && Boolean(selectedRequestId && board?.requests.some((r) => r.id === selectedRequestId));
  return (
    <div className="flex min-h-screen flex-col lg:flex-row">
      <aside className="hidden w-[232px] shrink-0 flex-col gap-5 border-r border-line bg-surface px-3 py-3.5 lg:sticky lg:top-0 lg:flex lg:h-screen lg:overflow-y-auto">
        <div className="px-1">
          <Brand />
        </div>
        <DisasterSwitcher />
        <Nav orientation="side" />
        <div className="mt-auto space-y-4">
          <ActingAs />
          <Services />
          <Safeguards />
        </div>
      </aside>
      <header className="flex items-center gap-3 border-b border-line bg-surface px-4 py-2 lg:hidden">
        <Brand />
        <Nav orientation="top" />
      </header>
      <div className={cn("flex min-w-0 flex-1 flex-col transition-[margin] sm:duration-150", drawerOpen && "sm:mr-[26rem]")}>
        <StatusStrip />
        <div className="space-y-3 border-b border-line bg-surface px-4 py-2 empty:hidden lg:hidden">
          <DisasterSwitcher />
        </div>
        <Banners />
        <DemoGuide />
        <main id="main" tabIndex={-1} className="min-w-0 flex-1 px-4 py-5 outline-none lg:px-8 lg:py-6">
          {children}
        </main>
        <div className="space-y-4 border-t border-line bg-surface p-4 lg:hidden">
          <ActingAs />
          <Services />
          <Safeguards />
        </div>
      </div>
      {showDrawer ? <RequestDrawer /> : null}
      <Toasts />
    </div>
  );
}
