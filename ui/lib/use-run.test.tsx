// @vitest-environment jsdom
import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { ConsoleAdapter } from "./adapter";
import { mockSnapshot } from "./mock";
import { useRunSnapshot } from "./use-run";

/** Adapter whose loads resolve only when the test says so, to force out-of-order responses. */
function slowAdapter() {
  const pending: Record<string, () => void> = {};
  const adapter: ConsoleAdapter = {
    runs: async () => [],
    load: (runId) =>
      new Promise((resolve) => {
        pending[runId] = () => resolve({ ...structuredClone(mockSnapshot), run: { ...mockSnapshot.run, run_id: runId } });
      }),
    decide: async () => {
      throw new Error("unused");
    },
    escalate: async () => {
      throw new Error("unused");
    },
  };
  return { adapter, resolve: (runId: string) => act(async () => pending[runId]()) };
}

describe("useRunSnapshot", () => {
  it("never shows the previous run after a switch, even when its response arrives late", async () => {
    const { adapter, resolve } = slowAdapter();
    const { result, rerender } = renderHook(({ run }) => useRunSnapshot(adapter, run), { initialProps: { run: "run-a" } });
    rerender({ run: "run-b" });
    await resolve("run-a"); // late answer for the old run
    expect(result.current.snap).toBeNull();
    await resolve("run-b");
    await waitFor(() => expect(result.current.snap?.run.run_id).toBe("run-b"));
    rerender({ run: "run-a" });
    expect(result.current.snap).toBeNull(); // run-b's data is not shown while run-a loads
  });

  it("polls without overlapping requests and keeps the last good snapshot on failure", async () => {
    vi.useFakeTimers();
    let inFlight = 0;
    let maxInFlight = 0;
    let fail = false;
    const adapter: ConsoleAdapter = {
      runs: async () => [],
      load: async () => {
        inFlight++;
        maxInFlight = Math.max(maxInFlight, inFlight);
        await new Promise((r) => setTimeout(r, 2500)); // slower than the poll interval
        inFlight--;
        if (fail) throw new Error("relay unreachable");
        return structuredClone(mockSnapshot);
      },
      decide: async () => {
        throw new Error("unused");
      },
      escalate: async () => {
        throw new Error("unused");
      },
    };
    const { result, unmount } = renderHook(() => useRunSnapshot(adapter, mockSnapshot.run.run_id, 1000));
    await act(async () => vi.advanceTimersByTimeAsync(10_000));
    expect(result.current.snap?.run.run_id).toBe(mockSnapshot.run.run_id);
    fail = true;
    await act(async () => vi.advanceTimersByTimeAsync(10_000));
    expect(result.current.error).toBe("relay unreachable");
    expect(result.current.snap).not.toBeNull(); // recoverable: last good data stays on screen
    expect(maxInFlight).toBe(1);
    unmount();
    vi.useRealTimers();
  });
});
