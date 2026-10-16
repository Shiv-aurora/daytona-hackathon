// Public Replay: read one completed run from recorded snapshots, server side only (Next.js route handlers).
// Read-only. Every per-run query filters by run_id; scenario inputs are read by scenario_id with
// run_id "scenario". Collection names are W2's (db/bootstrap.py). The browser never sees the
// connection string and never talks to the database; it gets the same ConsoleSnapshot the relay API returns.
import { assertRunScoped } from "../live/client";
import type { ConsoleSnapshot } from "../adapter";

/** The slice of the document-reader interface this module uses, so tests can pass an in-memory stand-in. */
export type Doc = Record<string, unknown> & { _id?: unknown };
export interface Coll {
  find(filter: Doc, options?: { projection?: Doc; sort?: Record<string, 1 | -1>; limit?: number }): { toArray(): Promise<Doc[]> };
  findOne(filter: Doc, options?: { projection?: Doc }): Promise<Doc | null>;
}
export interface ReadDb {
  collection(name: string): Coll;
}

// RunMeta.day0 per scenario (data/scenarios/<id>/scenario.json); RELAY_DAY0 overrides.
const DAY0: Record<string, string> = { s1: "2021-09-01T20:00:00-04:00" };
const TRACE_LIMIT = 5000;
const PER_RUN = ["households", "promises", "proposals", "call_requests", "metrics", "policy_changes"] as const;

const plain = (docs: Doc[]) => docs.map((d) => ({ ...d, _id: String(d._id) }) as Doc & { _id: string });

export async function listRuns(db: ReadDb) {
  const states = await db.collection("run_state").find({}, { projection: { run_id: 1, scenario_id: 1, now_ts: 1 } }).toArray();
  return states
    .map((s) => ({ run_id: String(s.run_id ?? s._id), scenario_id: s.scenario_id as string | undefined, now_ts: s.now_ts as number | undefined }))
    .sort((a, b) => (b.now_ts ?? 0) - (a.now_ts ?? 0) || a.run_id.localeCompare(b.run_id)); // most complete run first
}

export async function readConsole(db: ReadDb, runId: string): Promise<ConsoleSnapshot | null> {
  const state = await db.collection("run_state").findOne({ _id: runId }); // W2 keys run state by run_id
  if (!state) return null;
  const scenarioId = String(state.scenario_id);
  const [households, promises, proposals, callRequests, metrics, policyChanges] = await Promise.all(
    PER_RUN.map((c) => db.collection(c).find({ run_id: runId }).toArray().then(plain)),
  );
  const trace = plain(await db.collection("system_events").find({ run_id: runId }, { sort: { ts: 1 }, limit: TRACE_LIMIT }).toArray());

  // Scenario inputs this run applied or cited, plus the run's own call results.
  const ids = new Set<string>();
  for (const h of households) for (const id of (h.applied_event_ids as string[] | undefined) ?? []) ids.add(id);
  for (const p of proposals) for (const id of (p.cited_event_ids as string[] | undefined) ?? []) ids.add(id);
  for (const p of promises) if (p.source_event_id) ids.add(String(p.source_event_id));
  const [inputs, own] = await Promise.all([
    db.collection("events").find({ scenario_id: scenarioId, run_id: { $in: ["scenario", runId] }, _id: { $in: [...ids] } }).toArray(),
    db.collection("events").find({ scenario_id: scenarioId, run_id: runId, source: "call_result" }).toArray(),
  ]);
  const events = [...new Map(plain([...inputs, ...own]).map((e) => [e._id, e])).values()];

  // Registry entries for this run's households, never the callback number.
  const registry = await db
    .collection("registry")
    .find({ household_id: { $in: households.map((h) => String(h.household_id)) } }, { projection: { _id: 0, callback_number: 0 } })
    .toArray();
  const needles = await db
    .collection("needles")
    .find({ scenario_id: scenarioId }, { projection: { _id: 0 } })
    .toArray()
    .catch(() => []);

  const reasons = new Map(trace.filter((s) => s.action === "proposal_decided").map((s) => [String(s.proposal_id), (s.reason as string | undefined) ?? null]));
  const decisions = Object.fromEntries(
    proposals
      .filter((p) => p.status === "approved" || p.status === "dismissed")
      .map((p) => [p._id, { status: p.status, ts: (p.status_ts as number | undefined) ?? (p.ts as number), reason: reasons.get(p._id) ?? null }]),
  );

  const snap = {
    run: { run_id: runId, scenario_id: scenarioId, day0: process.env.RELAY_DAY0 || DAY0[scenarioId] || DAY0.s1!, mode: "replay" },
    now_ts: Number(state.now_ts ?? 0),
    start_ts: 0, // replay plays the run from the storm's first hour
    households,
    events,
    promises,
    proposals,
    decisions,
    registry,
    call_requests: callRequests,
    system_events: trace,
    metrics,
    policy_changes: policyChanges,
    needles,
    comparison: null, // W4-C3's comparison payload is not in recorded snapshots yet: "Prove it" says "Not yet measured"
  } as unknown as ConsoleSnapshot;
  assertRunScoped(snap, runId);
  return snap;
}
