// Plain-language facts for the decision hero, built only from records the console already holds.
// Every fact carries its citations (the records it came from) so the UI can show provenance.
import type { Event, Household, Proposal, RelayPromise } from "./contracts";
import type { ConsoleSnapshot } from "./adapter";
import { fmtShort } from "./sim";

export type Cite = { id: string; source: string; ts: number; text: string; real: boolean; callId?: string; outcome?: string };
export type Fact = { lead: string; cites: Cite[]; tail?: string };

const day = (day0: string, ts: number) => fmtShort(day0, ts).split(" ").slice(0, 2).join(" ");
const cite = (e: Event): Cite => {
  const x = e as Event & { origin?: string; call_id?: string; outcome?: string };
  return { id: e._id, source: e.source, ts: e.ts, text: e.text ?? "", real: x.origin === "real", callId: x.call_id, outcome: x.outcome };
};
const MISSED = new Set(["no_answer", "failed"]);

// Short phrases for common record contents. Fallback: the record's own first clause.
const PHRASES: [RegExp, string][] = [
  [/oxygen/i, "uses home oxygen, backup running low"],
  [/restoration[^.]*delayed|new estimate/i, "power restoration delayed"],
  [/meter room flooded/i, "meter room flooded, power not reconnected"],
  [/restored/i, "power restored"],
  [/without power|no power|power out/i, "no power"],
  [/sewage still|nobody came/i, "sewage still there, nobody came"],
  [/sewage/i, "sewage on the floor"],
  [/moving out|nowhere to go/i, "host moving out, nowhere to go"],
  [/evacuated/i, "evacuated safely"],
  [/trapped/i, "reported trapped"],
  [/no one answered|nobody answered/i, "no one answered the door"],
];

export function phrase(text: string): string {
  const hits = PHRASES.filter(([re]) => re.test(text)).map(([, p]) => p);
  // Don't repeat power facts ("power restoration delayed" already implies no power).
  const picked = hits.filter((p, i) => !(p === "no power" && hits.some((q, j) => j !== i && q.includes("power")))).slice(0, 2);
  if (picked.length) return cap(picked.join(", "));
  const body = text.includes(": ") ? text.slice(text.indexOf(": ") + 2) : text;
  const first = body.split(/[.;,](\s|$)/)[0]!.trim();
  return cap(first.length > 70 ? `${first.slice(0, 67)}…` : first);
}
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1);

function promiseFact(p: RelayPromise, source: Event | undefined, day0: string, now: number): Fact {
  const [who, what] = p.text.includes(": ") ? p.text.split(/:\s(.+)/) : [null, p.text];
  const subject = who ?? `"${what}"`;
  const cites = source ? [cite(source)] : [];
  const settled = p.status_ts === undefined || p.status_ts <= now ? p.status : "open";
  if (settled === "kept") return { lead: `${subject} came through`, cites };
  if (settled === "lapsed") return { lead: `${subject} was due ${day(day0, p.due_ts)}`, cites, tail: ", no sign it happened" };
  return { lead: `${subject} is due ${day(day0, p.due_ts)}`, cites };
}

/** Facts behind a proposal: its promise(s), missed calls, then the other cited records in time order. */
export function evidenceOf(p: Proposal, snap: ConsoleSnapshot): Fact[] {
  const day0 = snap.run.day0;
  const now = snap.now_ts;
  const byId = new Map(snap.events.map((e) => [e._id, e]));
  const cited = new Set(p.cited_event_ids);
  const facts: Fact[] = [];
  const used = new Set<string>();

  for (const pr of snap.promises) {
    if (pr.household_id !== p.household_id || pr.made_ts > now) continue;
    if (pr._id !== p.promise_id && !cited.has(pr.source_event_id)) continue;
    facts.push(promiseFact(pr, byId.get(pr.source_event_id), day0, now));
    used.add(pr.source_event_id);
  }

  const missed = snap.events
    .filter((e) => e.source === "call_result" && e.household_id === p.household_id && e.ts <= now && MISSED.has((e as { outcome?: string }).outcome ?? ""))
    .sort((a, b) => a.ts - b.ts);
  if (missed.length) {
    facts.push({ lead: missed.length === 1 ? "Call unanswered" : "Calls unanswered", cites: missed.map(cite) });
    missed.forEach((e) => used.add(e._id));
  }

  const rest = p.cited_event_ids
    .map((id) => byId.get(id))
    .filter((e): e is Event => e !== undefined && !used.has(e._id) && e.ts <= now)
    .sort((a, b) => a.ts - b.ts);
  for (const e of rest) facts.push({ lead: phrase(e.text ?? ""), cites: [cite(e)] });
  return facts;
}

/** One muted line about the household, from its own records: "82 · lives alone · basement unit · no power". */
export function profileOf(h: Household, events: Event[]): string[] {
  const own = events.filter((e) => h.applied_event_ids.includes(e._id)).sort((a, b) => a.ts - b.ts);
  const all = own.map((e) => e.text ?? "").join("\n");
  const out: string[] = [];
  const age = all.match(/\b(?:Mrs|Mr|Ms)\.\s[\w'-]+(?:\s[\w'-]+)?,\s(\d{2,3})\b/)?.[1];
  if (age) out.push(age);
  const family = all.match(/family of (\d+)/i)?.[1];
  if (family) out.push(`family of ${family}`);
  if (/lives alone/i.test(all)) out.push("lives alone");
  if (/\bbsmt\b|basement|cellar/i.test(`${h.address ?? ""}\n${all}`)) out.push("basement unit");
  // Power: whatever the latest record that mentions it says.
  const power = [...own].reverse().find((e) => /power|reconnect|outage|restor/i.test(e.text ?? ""));
  if (power && !/\brestored\b|power back/i.test(power.text) && /no power|without power|not reconnected|outage|delayed/i.test(power.text)) out.push("no power");
  return out.slice(0, 4);
}
