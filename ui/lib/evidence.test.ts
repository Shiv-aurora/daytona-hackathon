import { describe, expect, it } from "vitest";
import { evidenceOf, phrase, profileOf } from "./evidence";
import { mockSnapshot as m } from "./mock";

const sentence = (facts: ReturnType<typeof evidenceOf>) =>
  facts.map((f) => `${f.lead} ${f.cites.map((c) => `[${c.source} ${c.id}]`).join(" ")}${f.tail ?? ""}.`).join(" ");

describe("hero evidence", () => {
  const chen = m.proposals.find((p) => p._id === "prop-s1_h_001")!;

  it("builds Mrs. Chen's sentence only from cited records and missed calls", () => {
    const facts = evidenceOf(chen, m);
    expect(sentence(facts)).toBe(
      "Son Wei was due Sep 7 [visit_note s1_e_000407], no sign it happened. " +
        "Calls unanswered [call_result call-s1_h_001-1:result] [call_result call-s1_h_001-2:result]. " +
        "Power restoration delayed [utility s1_e_000817]. " +
        "Meter room flooded, power not reconnected, no one answered the door [crew s1_e_001052].",
    );
    const cited = new Set([...chen.cited_event_ids, "call-s1_h_001-1:result", "call-s1_h_001-2:result"]);
    for (const f of facts) for (const c of f.cites) expect(cited.has(c.id)).toBe(true);
  });

  it("marks provenance: real only when the record says so", () => {
    const cites = evidenceOf(chen, m).flatMap((f) => f.cites);
    expect(cites.every((c) => c.real === false)).toBe(true);
    const real = { ...m, events: m.events.map((e) => (e._id === "s1_e_000817" ? { ...e, origin: "real" } : e)) };
    expect(evidenceOf(chen, real).flatMap((f) => f.cites).find((c) => c.id === "s1_e_000817")?.real).toBe(true);
  });

  it("describes the household from its own records", () => {
    const h = m.households.find((x) => x.household_id === "s1_h_001")!;
    expect(profileOf(h, m.events)).toEqual(["82", "lives alone", "basement unit", "no power"]);
  });

  it("falls back to the record's own first clause", () => {
    expect(phrase("311 call from a neighbor: water coming through the ceiling, again")).toBe("Water coming through the ceiling");
  });
});
