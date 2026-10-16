"use client";

import { BookOpen, Building2, ChevronsUpDown, CircleAlert, Compass, LayoutList, Moon, Phone, Play, Plug, RefreshCw, RotateCcw, ShieldCheck, Sun, X, type LucideIcon } from "lucide-react";
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

function Nav({ orientation, compact = false, dark = true }: { orientation: "side" | "top"; compact?: boolean; dark?: boolean }) {
  const path = usePathname();
  const badges = useBadges();
  return (
    <nav aria-label="Workspace" className={cn(orientation === "side" ? "flex flex-col gap-0.5" : "flex gap-1 overflow-x-auto")}>
      {NAV.map(({ href, label, icon: Icon, badge }) => {
        const active = path === href || path.startsWith(`${href}/`);
        const n = badge ? badges[badge] : 0;
        const side = dark;
        return (
          <Link
            key={href}
            href={href}
            title={compact ? label : undefined}
            aria-label={compact ? label : undefined}
            aria-current={active ? "page" : undefined}
            className={cn(
              "group relative flex h-8 items-center gap-2.5 rounded-md text-sm whitespace-nowrap outline-none transition-colors",
              compact ? "size-9 justify-center" : "px-2.5",
              side
                ? active
                  ? "bg-rail-2 font-medium text-rail-ink shadow-[inset_0_0_0_1px_var(--rail-line)]"
                  : "text-rail-muted hover:bg-rail-2 hover:text-rail-ink"
                : active
                  ? "bg-panel font-medium text-ink shadow-[0_0_0_1px_var(--border)]"
                  : "text-ink-2 hover:bg-hover hover:text-ink",
            )}
          >
            <Icon aria-hidden className={cn("size-[15px]", active ? "text-agent" : side ? "text-rail-muted group-hover:text-rail-ink" : "text-muted-foreground")} />
            {compact ? null : label}
            {n && !compact ? (
              <span className={cn("num ml-auto rounded-[4px] px-1.5 text-2xs font-medium", side ? "bg-rail-line text-rail-ink" : "bg-hover text-ink-2")} aria-label={`${n} need attention`}>
                {n}
              </span>
            ) : null}
            {n && compact ? <span aria-hidden className="absolute right-1.5 top-1.5 size-1.5 rounded-full bg-agent" /> : null}
          </Link>
        );
      })}
    </nav>
  );
}

/** The mark: two relay nodes joined by a baton line. */
function Mark({ size = 24 }: { size?: number }) {
  return (
    <svg aria-hidden width={size} height={size} viewBox="0 0 24 24" fill="none">
      <rect width="24" height="24" rx="7" fill="var(--agent)" />
      <path d="M7.5 15.5c3.4 0 5-7 9-7" stroke="#fff" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="7.5" cy="15.5" r="2.1" fill="#fff" />
      <circle cx="16.5" cy="8.5" r="2.1" fill="#fff" />
    </svg>
  );
}

function Brand({ compact = false, onDark = false }: { compact?: boolean; onDark?: boolean }) {
  return (
    <Link href="/live" className="flex items-center gap-2 rounded-md outline-none" aria-label="Relay home">
      <Mark />
      {compact ? null : <span className={cn("text-[15px] font-semibold tracking-[-0.02em]", onDark ? "text-rail-ink" : "text-ink")}>Relay</span>}
    </Link>
  );
}

/** Workspace switcher, in the Linear mould: the current disaster is the "workspace". */
function DisasterSwitcher({ onDark = false }: { onDark?: boolean }) {
  const { runs, disasters, runId, selectRun, board } = useRelay();
  const name = (disasterId: string) => disasters.find((d) => d.id === disasterId)?.name ?? disasterId;
  const current = runs.find((r) => r.run_id === runId);
  const d = disasters.find((x) => x.id === (board?.disaster.id ?? current?.disaster_id));
  return (
    <label className="relative block">
      <span className="sr-only">Disaster</span>
      <span className={cn("pointer-events-none flex items-center gap-2.5 rounded-md border px-2.5 py-2", onDark ? "border-rail-line bg-rail-2" : "border-line bg-panel")}>
        <span aria-hidden className="grid size-6 shrink-0 place-items-center rounded-[5px] bg-st-verify font-mono text-[10px] font-semibold text-white">
          {(d?.kind ?? "dz").slice(0, 2).toUpperCase()}
        </span>
        <span className="min-w-0 flex-1 leading-tight">
          <span className={cn("block truncate text-[12.5px] font-medium", onDark ? "text-rail-ink" : "text-ink")}>{d ? name(d.id) : "Loading…"}</span>
          <span className={cn("block truncate text-[10.5px]", onDark ? "text-rail-muted" : "text-muted-foreground")}>{d ? `${d.kind} · ${d.region}` : ""}</span>
        </span>
        <ChevronsUpDown aria-hidden className={cn("size-3.5 shrink-0", onDark ? "text-rail-muted" : "text-muted-foreground")} />
      </span>
      <select value={runId} onChange={(e) => selectRun(e.target.value)} className="absolute inset-0 size-full cursor-pointer rounded-md opacity-0">
        {runs.map((r) => (
          <option key={r.run_id} value={r.run_id}>
            {name(r.disaster_id)}
          </option>
        ))}
      </select>
    </label>
  );
}

function ActingAs({ onDark = false }: { onDark?: boolean }) {
  const { board, orgId, setOrgId } = useRelay();
  const orgs = board?.organizations ?? [];
  const current = orgs.find((o) => o.id === orgId);
  return (
    <label className="relative block">
      <span className={cn("label mb-1 block", onDark && "!text-rail-muted")}>Acting as</span>
      <span className={cn("pointer-events-none flex items-center gap-2 rounded-md border px-2 py-1.5", onDark ? "border-rail-line bg-rail-2" : "border-line bg-panel")}>
        <Monogram name={current?.name ?? orgId} active />
        <span className={cn("min-w-0 flex-1 truncate text-[12.5px]", onDark ? "text-rail-ink" : "text-ink")}>{current ? shortOrg(current.name) : orgId}</span>
        <ChevronsUpDown aria-hidden className={cn("size-3.5 shrink-0", onDark ? "text-rail-muted" : "text-muted-foreground")} />
      </span>
      <select
        aria-label="Acting as organization"
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

function Safeguards() {
  return (
    <details className="group rounded-md border border-rail-line bg-rail-2">
      <summary className="flex cursor-pointer list-none items-center gap-2 px-2.5 py-1.5 text-xs font-medium text-rail-ink outline-none">
        <ShieldCheck aria-hidden className="size-3.5 text-agent" /> Safeguards
        <span aria-hidden className="ml-auto text-rail-muted transition-transform group-open:rotate-90">›</span>
      </summary>
      <ul className="space-y-1.5 border-t border-rail-line px-2.5 py-2 text-xs text-rail-muted">
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

const railBtn = "text-rail-muted hover:bg-rail-2 hover:text-rail-ink";

function ThemeToggle({ className }: { className?: string }) {
  const theme = useSyncExternalStore(subscribeTheme, currentTheme, () => "light" as const);
  return (
    <Button
      variant="ghost"
      size="icon-sm"
      className={className}
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

/** Global actions: reset, guide, data source, theme. Icon-only so they never compete with the page. */
function Actions({ vertical = false, className, btn }: { vertical?: boolean; className?: string; btn?: string }) {
  const { mode, apiConfigured, setMode, guideOpen, setGuideOpen, resetDemo } = useRelay();
  return (
    <div className={cn("flex items-center gap-0.5", vertical && "flex-col", className)}>
      {apiConfigured ? (
        <Button variant="ghost" size="icon-sm" className={btn} title={mode === "live" ? "Connected to the API" : "Connect to the API"} aria-pressed={mode === "live"} onClick={() => setMode(mode === "live" ? "mock" : "live")}>
          <Plug aria-hidden className={cn(mode === "live" && "text-agent")} />
        </Button>
      ) : null}
      <Button variant="ghost" size="icon-sm" className={btn} title="Reset demo" aria-label="Reset demo" onClick={() => void resetDemo()}>
        <RotateCcw aria-hidden />
      </Button>
      <Button variant="ghost" size="icon-sm" className={cn(btn, guideOpen && "text-agent")} title="Demo guide" aria-label="Demo guide" aria-pressed={guideOpen} onClick={() => setGuideOpen(!guideOpen)}>
        <Compass aria-hidden />
      </Button>
      <ThemeToggle className={btn} />
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
  // Live is a single, fixed screen: the graph is the page. Lessons need the full width; the request drawer is for the
  // board, organizations and calls.
  const cinematic = path.startsWith("/live");
  const showDrawer = !path.startsWith("/intelligence") && !cinematic;
  const drawerOpen = showDrawer && Boolean(selectedRequestId && board?.requests.some((r) => r.id === selectedRequestId));
  return (
    <div className={cn("flex min-h-screen flex-col lg:flex-row", cinematic && "lg:h-screen lg:overflow-hidden")}>
      <aside
        className={cn(
          "hidden shrink-0 flex-col gap-5 bg-rail py-3.5 lg:sticky lg:top-0 lg:flex lg:h-screen lg:overflow-y-auto",
          cinematic ? "w-[60px] items-center px-2" : "w-[236px] px-3",
        )}
      >
        <div className={cn(!cinematic && "px-1")}>
          <Brand compact={cinematic} onDark />
        </div>
        {cinematic ? null : <DisasterSwitcher onDark />}
        <Nav orientation="side" compact={cinematic} />
        <div className={cn("mt-auto space-y-4", cinematic && "flex flex-col items-center")}>
          {cinematic ? null : (
            <>
              <ActingAs onDark />
              <Safeguards />
            </>
          )}
          <Actions vertical={cinematic} btn={railBtn} className={cn(!cinematic && "border-t border-rail-line pt-3")} />
        </div>
      </aside>
      <header className="flex items-center gap-3 bg-rail px-4 py-2 lg:hidden">
        <Brand compact onDark />
        <Nav orientation="top" compact />
        <Actions btn={railBtn} className="ml-auto" />
      </header>
      <div className={cn("flex min-w-0 flex-1 flex-col transition-[margin] sm:duration-150", drawerOpen && "sm:mr-[26rem]", cinematic && "lg:min-h-0")}>
        {cinematic ? null : (
          <div className="border-b border-line bg-surface px-4 py-2 lg:hidden">
            <DisasterSwitcher />
          </div>
        )}
        <Banners />
        <DemoGuide />
        <main id="main" tabIndex={-1} className={cn("min-w-0 flex-1 outline-none", cinematic ? "flex flex-col px-4 py-4 lg:min-h-0 lg:px-6" : "px-4 py-5 lg:px-8 lg:py-6")}>
          {children}
        </main>
        {cinematic ? null : (
          <div className="space-y-4 border-t border-line bg-surface p-4 lg:hidden">
            <ActingAs />
          </div>
        )}
      </div>
      {showDrawer ? <RequestDrawer /> : null}
      <Toasts />
    </div>
  );
}
