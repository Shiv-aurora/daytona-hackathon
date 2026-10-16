import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { DATA_LABEL } from "./labels";

describe("fixed data label", () => {
  it("uses the exact approved wording", () => {
    expect(DATA_LABEL).toBe(
      "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated.",
    );
  });

  it("renders on every page that shows the Ida 311 data (legacy console layout)", () => {
    const layout = readFileSync(new URL("../app/(legacy)/layout.tsx", import.meta.url), "utf8");
    expect(layout).toContain('import { DATA_LABEL } from "@/lib/labels"');
    expect(layout).toContain("{DATA_LABEL}");
  });
});
