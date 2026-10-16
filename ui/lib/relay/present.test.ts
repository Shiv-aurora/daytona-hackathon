import { describe, expect, it } from "vitest";
import seed from "./seed.json";
import { plainName, plainText, presentBoard } from "./present";
import type { Board } from "./types";

describe("present", () => {
  it("drops the fictional/synthetic labels from names", () => {
    expect(plainName("Cedar Valley Storm (fictional)")).toBe("Cedar Valley Storm");
    expect(plainName("Fictional household A")).toBe("Household A");
    expect(plainName("Demo Food Collective")).toBe("Demo Food Collective");
  });

  it("drops label-only sentences but keeps the meaning", () => {
    expect(plainText("Synthetic scripted no-answer; no live call was made. Receipt remains unverified.")).toBe("Receipt remains unverified.");
    expect(plainText("Synthetic request for food.")).toBe("Request for food.");
    expect(plainText("Survivor reported assistance did not arrive.")).toBe("Survivor reported assistance did not arrive.");
  });

  it("only changes display fields; ids, run and disaster scope are untouched", () => {
    const s = seed as unknown as { disasters: Board["disaster"][]; survivors: Board["survivors"] };
    const board = { run_id: "r", disaster: s.disasters[0], survivors: s.survivors, organizations: [], requests: [], calls: [] } as unknown as Board;
    const out = presentBoard(board);
    expect(out.run_id).toBe("r");
    expect(out.disaster.id).toBe(board.disaster.id);
    expect(out.survivors.map((x) => x.id)).toEqual(board.survivors.map((x) => x.id));
    expect(JSON.stringify(out.survivors)).not.toMatch(/fictional/i);
    expect(board.survivors[0].display_name).toMatch(/fictional/i); // the source data is not mutated
  });
});
