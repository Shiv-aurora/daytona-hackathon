import { afterEach, describe, expect, it, vi } from "vitest";
import { pickSource } from "./source";

afterEach(() => vi.unstubAllEnvs());

describe("pickSource", () => {
  it("falls back to mock data with no backend", () => {
    vi.stubEnv("NEXT_PUBLIC_MODE", "replay");
    vi.stubEnv("NEXT_PUBLIC_RELAY_API_URL", "");
    expect(pickSource(undefined)).toEqual({ kind: "mock", relay: null });
  });
  it("never enables direct database replay from service credentials", () => {
    vi.stubEnv("SURREAL_URL", "ws://localhost:8000/rpc");
    vi.stubEnv("NEXT_PUBLIC_RELAY_API_URL", "");
    expect(pickSource("replay").kind).toBe("mock");
  });
  it("uses only the configured backend API and lets mock mode override it", () => {
    vi.stubEnv("NEXT_PUBLIC_MODE", "");
    vi.stubEnv("NEXT_PUBLIC_RELAY_API_URL", "http://relay.local");
    expect(pickSource(undefined)).toEqual({ kind: "live", relay: "http://relay.local" });
    expect(pickSource("mock").kind).toBe("mock");
  });
});
