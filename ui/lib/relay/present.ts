// Presentation-only cleanup. The demo seed labels its records "(fictional)" / "Synthetic" so nobody mistakes them for
// real people; that labelling stays in the data and the API. On screen the labels are noise, so names and summaries
// are shown without them. Nothing here is sent back to the backend.
import type { Board, Disaster } from "./types";

const NOISE = /synthetic|scripted|fictional|no live call/i;

/** "Cedar Valley Storm (fictional)" → "Cedar Valley Storm"; "Fictional household A" → "Household A". */
export function plainName(s: string): string {
  const out = s
    .replace(/\s*\(fictional\)/gi, "")
    .replace(/^(fictional|synthetic)\s+(\S)/i, (_, __, c: string) => c.toUpperCase())
    .trim();
  return out || s;
}

/** Drops sentences that only exist to say the record is synthetic. Keeps the original if nothing else is left. */
export function plainText(s: string): string {
  if (!s || !NOISE.test(s)) return s;
  const kept = s
    .split(/(?<=[.;])\s+/)
    .map((x) => x.trim())
    .filter((x) => x && !NOISE.test(x));
  if (kept.length) return kept.join(" ").replace(/;$/, ".");
  return plainName(s);
}

export const presentDisaster = (d: Disaster): Disaster => ({ ...d, name: plainName(d.name), region: plainName(d.region) });

export function presentBoard(b: Board): Board {
  return {
    ...b,
    disaster: presentDisaster(b.disaster),
    survivors: b.survivors.map((s) => ({ ...s, display_name: plainName(s.display_name) })),
    organizations: b.organizations.map((o) => ({ ...o, region: plainName(o.region) })),
    requests: b.requests.map((r) => ({ ...r, description: plainText(r.description) })),
    calls: b.calls.map((c) => ({ ...c, summary: plainText(c.summary) })),
  };
}
