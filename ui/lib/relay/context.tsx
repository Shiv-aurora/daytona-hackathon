"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { HttpApi, SEEDED_RUNS } from "./http";
import { MockApi } from "./mock";
import { RelayError, type Board, type Disaster, type Health, type RelayApi, type RunInfo } from "./types";

export type Mode = "live" | "mock";
export type Connection = "connecting" | "ready" | "error";
export type Toast = { id: number; kind: "success" | "error" | "info"; text: string };

const API_URL = process.env.NEXT_PUBLIC_RELAY_API_URL?.trim() || "";
const POLL_MS = 4000;

let mockSingleton: MockApi | null = null;
const getMock = () => (mockSingleton ??= new MockApi());

const messageOf = (e: unknown) => (e instanceof RelayError || e instanceof Error ? e.message : "Something went wrong");

function safeStorage<T>(fn: () => T): T | undefined {
  try {
    return fn();
  } catch {
    return undefined; // private mode / blocked storage: the workspace works without it
  }
}

/**
 * A tiny session-scoped preference store. Using useSyncExternalStore keeps server and first client render
 * identical (the fallback), then switches to the remembered/URL value without a hydration mismatch.
 * A stored choice beats the URL parameter, so toggling in the UI sticks.
 */
function createPreference(key: string, fallback: string, urlParam?: string) {
  const listeners = new Set<() => void>();
  return {
    subscribe(cb: () => void) {
      listeners.add(cb);
      return () => void listeners.delete(cb);
    },
    get(): string {
      const stored = safeStorage(() => sessionStorage.getItem(key));
      if (stored) return stored;
      const fromUrl = urlParam ? new URLSearchParams(window.location.search).get(urlParam) : null;
      return fromUrl ?? fallback;
    },
    getServer: () => fallback,
    /** Remember a URL-supplied choice, so client-side navigation (which drops the query string) keeps it. */
    adoptUrl() {
      const fromUrl = urlParam ? new URLSearchParams(window.location.search).get(urlParam) : null;
      if (fromUrl && !safeStorage(() => sessionStorage.getItem(key))) this.set(fromUrl);
    },
    set(value: string) {
      safeStorage(() => sessionStorage.setItem(key, value));
      listeners.forEach((l) => l());
    },
  };
}

const modePref = createPreference("relay-mode", API_URL ? "live" : "mock", "mode");
const orgPref = createPreference("relay-org", "demo-food");

interface Ctx {
  mode: Mode;
  apiConfigured: boolean;
  apiUrl: string;
  setMode: (m: Mode) => void;
  api: RelayApi;
  connection: Connection;
  connectionError: string | null;
  retryConnection: () => void;
  health: Health | null;
  runs: RunInfo[];
  disasters: Disaster[];
  runId: string;
  selectRun: (runId: string) => void;
  board: Board | null;
  boardError: string | null;
  refresh: () => Promise<void>;
  orgId: string;
  setOrgId: (id: string) => void;
  selectedRequestId: string | null;
  selectRequest: (id: string | null) => void;
  busy: (key: string) => boolean;
  act: <T>(key: string, success: string | ((r: T) => string), fn: () => Promise<T>) => Promise<T | undefined>;
  toasts: Toast[];
  notify: (kind: Toast["kind"], text: string) => void;
  dismissToast: (id: number) => void;
  escalation: { message: string } | null;
  setEscalation: (e: { message: string } | null) => void;
  resetDemo: () => Promise<void>;
  guideOpen: boolean;
  setGuideOpen: (open: boolean) => void;
  now: number;
}

const RelayContext = createContext<Ctx | null>(null);

export function useRelay(): Ctx {
  const ctx = useContext(RelayContext);
  if (!ctx) throw new Error("useRelay must be used inside <RelayProvider>");
  return ctx;
}

type Conn = { key: string; status: "ready" | "error"; error: string | null; health: Health | null; runs: RunInfo[]; disasters: Disaster[] };

export function RelayProvider({ children }: { children: ReactNode }) {
  const preferred = useSyncExternalStore(modePref.subscribe, modePref.get, modePref.getServer);
  const mode: Mode = preferred === "live" && API_URL ? "live" : "mock";
  const orgId = useSyncExternalStore(orgPref.subscribe, orgPref.get, orgPref.getServer);

  const [attempt, setAttempt] = useState(0);
  const [conn, setConn] = useState<Conn | null>(null);
  const [runId, setRunId] = useState("demo-current");
  const [board, setBoard] = useState<Board | null>(null);
  const [boardError, setBoardError] = useState<string | null>(null);
  const [selectedRequestId, setSelectedRequestId] = useState<string | null>(null);
  const [busyKeys, setBusyKeys] = useState<Set<string>>(new Set());
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [escalation, setEscalation] = useState<{ message: string } | null>(null);
  const [guideOpen, setGuideOpen] = useState(false);
  const [now, setNow] = useState(() => Date.now());
  const toastId = useRef(0);
  const refreshSeq = useRef(0);

  const api: RelayApi = useMemo(() => (mode === "live" ? new HttpApi(API_URL) : getMock()), [mode]);

  useEffect(() => {
    modePref.adoptUrl();
  }, []);

  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 30000);
    return () => clearInterval(t);
  }, []);

  // Connect: health, runs, disasters. A failure is shown, never hidden (and never silently swapped for mock data).
  const connKey = `${mode}:${attempt}`;
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [health, runs, disasters] = await Promise.all([api.health(), api.runs(), api.disasters()]);
        if (cancelled) return;
        setConn({ key: connKey, status: "ready", error: null, health, runs, disasters });
        setRunId((cur) => (runs.some((x) => x.run_id === cur) ? cur : (runs.find((x) => x.run_id === "demo-current") ?? runs[0]).run_id));
      } catch (e) {
        if (cancelled) return;
        setConn({ key: connKey, status: "error", error: messageOf(e), health: null, runs: SEEDED_RUNS, disasters: [] });
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [api, connKey]);

  const current = conn?.key === connKey ? conn : null;
  const connection: Connection = current ? current.status : "connecting";

  // Latest request wins: a slow poll can never overwrite a newer board, or another run's board.
  const refresh = useCallback(async () => {
    const seq = ++refreshSeq.current;
    try {
      const b = await api.board(runId);
      if (seq !== refreshSeq.current) return;
      setBoard(b);
      setBoardError(null);
    } catch (e) {
      if (seq === refreshSeq.current) setBoardError(messageOf(e));
    }
  }, [api, runId]);

  useEffect(() => {
    if (connection !== "ready") return;
    const seq = ++refreshSeq.current;
    api
      .board(runId)
      .then((b) => {
        if (seq !== refreshSeq.current) return;
        setBoard(b);
        setBoardError(null);
      })
      .catch((e) => {
        if (seq === refreshSeq.current) setBoardError(messageOf(e));
      });
  }, [connection, api, runId]);

  useEffect(() => {
    if (connection !== "ready" || api.kind !== "live") return;
    const t = setInterval(() => {
      if (!document.hidden) void refresh();
    }, POLL_MS);
    return () => clearInterval(t);
  }, [connection, api, refresh]);

  const setMode = useCallback((m: Mode) => {
    setBoard(null);
    setSelectedRequestId(null);
    setEscalation(null);
    modePref.set(m);
  }, []);

  const selectRun = useCallback((id: string) => {
    setBoard(null);
    setSelectedRequestId(null);
    setEscalation(null);
    setRunId(id);
  }, []);

  const notify = useCallback((kind: Toast["kind"], text: string) => {
    const id = ++toastId.current;
    setToasts((t) => [...t.slice(-3), { id, kind, text }]);
    if (kind !== "error") setTimeout(() => setToasts((t) => t.filter((x) => x.id !== id)), 6000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts((t) => t.filter((x) => x.id !== id)), []);

  const act: Ctx["act"] = useCallback(
    async (key, success, fn) => {
      setBusyKeys((s) => new Set(s).add(key));
      try {
        const result = await fn();
        await refresh();
        notify("success", typeof success === "function" ? success(result) : success);
        return result;
      } catch (e) {
        notify("error", messageOf(e));
        await refresh(); // a 409 usually means someone else moved first: show the current state
        return undefined;
      } finally {
        setBusyKeys((s) => {
          const next = new Set(s);
          next.delete(key);
          return next;
        });
      }
    },
    [refresh, notify],
  );

  const resetDemo = useCallback(async () => {
    try {
      const ok = await api.reset();
      if (!ok) {
        notify("info", "This backend has no reset route yet. Restart the API to restore the seed.");
        return;
      }
      setSelectedRequestId(null);
      setEscalation(null);
      await refresh();
      notify("success", "Demo reset to the seeded state.");
    } catch (e) {
      notify("error", messageOf(e));
    }
  }, [api, refresh, notify]);

  const value: Ctx = {
    mode,
    apiConfigured: Boolean(API_URL),
    apiUrl: API_URL,
    setMode,
    api,
    connection,
    connectionError: current?.error ?? null,
    retryConnection: () => setAttempt((n) => n + 1),
    health: current?.health ?? null,
    runs: current?.runs ?? SEEDED_RUNS,
    disasters: current?.disasters ?? [],
    runId,
    selectRun,
    board,
    boardError,
    refresh,
    orgId,
    setOrgId: orgPref.set,
    selectedRequestId,
    selectRequest: setSelectedRequestId,
    busy: (key) => busyKeys.has(key),
    act,
    toasts,
    notify,
    dismissToast,
    escalation,
    setEscalation,
    resetDemo,
    guideOpen,
    setGuideOpen,
    now,
  };
  return <RelayContext.Provider value={value}>{children}</RelayContext.Provider>;
}
