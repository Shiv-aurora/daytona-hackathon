// Mock console run (no backend). See the _note field in queens-s1.json for provenance.
import bundle from "./queens-s1.json";
import type {
  CallRequest,
  Event,
  Household,
  Metric,
  Needle,
  PolicyChange,
  PromiseRecall,
  Proposal,
  RegistryEntry,
  RelayPromise,
  RunMeta,
  SystemEvent,
} from "../contracts";

export type Decision = { status: "approved" | "dismissed"; ts: number; reason: string | null };

/** Everything the console shows for one run. Live and mock adapters return the same shape. */
export type ConsoleSnapshot = {
  run: RunMeta;
  now_ts: number;
  households: Household[];
  events: Event[]; // scenario inputs + this run's own events (e.g. W3 call_result events)
  promises: RelayPromise[];
  proposals: Proposal[];
  decisions: Record<string, Decision>;
  registry: RegistryEntry[];
  call_requests: CallRequest[];
  system_events: SystemEvent[];
  metrics: Metric[];
  policy_changes: PolicyChange[];
  /** Where playback starts (sim hours). Omitted: the console opens at now_ts, the run head. */
  start_ts?: number;
  /** Scenario needles, for the presenter's "next needle" jump. */
  needles?: Needle[];
  /** W4 comparison (Relay vs the long-context baseline) once the evaluator has run; else absent. */
  comparison?: Comparison | null;
};

export type Comparison = { relay: { promise_recall: PromiseRecall }; baseline: { promise_recall: PromiseRecall } };

export const mockSnapshot = bundle as unknown as ConsoleSnapshot & { _note: string };
