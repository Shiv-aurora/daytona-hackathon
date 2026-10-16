"use client";
// One run's snapshot, kept fresh by bounded polling. Guarantees:
// - state is keyed by run: after a switch nothing from the previous run renders;
// - polls never overlap (the next one is scheduled only after the previous finishes);
// - every response is sequenced, so a late or superseded response (any run) is dropped;
// - a failure keeps the last good snapshot of the same run and reports a recoverable error.
import { useCallback, useEffect, useRef, useState } from "react";
import type { ConsoleAdapter, ConsoleSnapshot } from "./adapter";

type State = { runId: string | null; snap: ConsoleSnapshot | null; error: string | null };
const MAX_BACKOFF_MS = 15_000;

export function useRunSnapshot(adapter: ConsoleAdapter, runId: string | null, pollMs = 0) {
  const [state, setState] = useState<State>({ runId: null, snap: null, error: null });
  const current = useRef<string | null>(null);
  const seq = useRef(0);
  const applied = useRef(0);

  const fetchOnce = useCallback(async (): Promise<boolean> => {
    const asked = current.current;
    if (!asked) return true;
    const mine = ++seq.current;
    try {
      const snap = await adapter.load(asked);
      if (current.current !== asked || snap.run.run_id !== asked || mine < applied.current) return true;
      applied.current = mine;
      setState({ runId: asked, snap, error: null });
      return true;
    } catch (e) {
      if (current.current !== asked || mine < applied.current) return false;
      setState((s) => ({ runId: asked, snap: s.runId === asked ? s.snap : null, error: (e as Error).message }));
      return false;
    }
  }, [adapter]);

  useEffect(() => {
    current.current = runId;
    applied.current = seq.current; // anything already in flight belongs to the previous run
    let stopped = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let delay = pollMs;
    const loop = async () => {
      const ok = await fetchOnce();
      if (stopped || !pollMs) return;
      delay = ok ? pollMs : Math.min(delay * 2, MAX_BACKOFF_MS);
      timer = setTimeout(loop, delay);
    };
    if (runId) loop();
    return () => {
      stopped = true;
      clearTimeout(timer);
    };
  }, [runId, pollMs, fetchOnce]);

  const fresh = state.runId === runId;
  return { snap: fresh ? state.snap : null, error: fresh ? state.error : null, reload: fetchOnce };
}
