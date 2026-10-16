import "server-only";
import { relayBase } from "./live/client";
import { replayConfigured } from "./replay/server";

export type SourceKind = "live" | "replay" | "mock";

/**
 * Where a page reads from. `?mode=` wins over NEXT_PUBLIC_MODE. Direct database replay is disabled; the backend API uses NEXT_PUBLIC_RELAY_API_URL. Anything unavailable falls back to the mock run.
 */
export function pickSource(mode: unknown): { kind: SourceKind; relay: string | null } {
  const want = (typeof mode === "string" ? mode : process.env.NEXT_PUBLIC_MODE ?? "").trim().toLowerCase();
  if (want === "mock") return { kind: "mock", relay: null };
  if (want === "replay" && replayConfigured()) return { kind: "replay", relay: null };
  const relay = relayBase();
  return relay ? { kind: "live", relay } : { kind: "mock", relay: null };
}
