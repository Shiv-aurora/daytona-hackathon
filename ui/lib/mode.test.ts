import { afterEach, describe, expect, it, vi } from "vitest";
import { hideMock, runLabel } from "./mode";

afterEach(() => vi.unstubAllEnvs());

describe("presentation mode", () => {
  it("shows mock scaffolding by default", () => {
    vi.stubEnv("NEXT_PUBLIC_MODE", "");
    expect(hideMock()).toBe(false);
    expect(runLabel("mock-queens-s1")).toBe("mock-queens-s1");
  });
  it.each(["replay", "live", "Replay"])("hides it in %s mode", (mode) => {
    vi.stubEnv("NEXT_PUBLIC_MODE", mode);
    expect(hideMock()).toBe(true);
    expect(runLabel("mock-queens-s1")).toBe("queens-s1");
    expect(runLabel("run-7")).toBe("run-7");
  });
});
