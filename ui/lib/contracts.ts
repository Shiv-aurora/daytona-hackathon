// TypeScript mirror of the shared contracts in /schemas.py (integration-owned; do not diverge).
// Only the shapes the C1 console reads. Field names and optionality match schemas.py exactly.
// All simulated timestamps are HOURS since scenario day 0 (RunMeta.day0).
import { z } from "zod";

export const SCENARIO_RUN_ID = "scenario"; // run_id of scenario input events
const SimTime = z.number().min(0);

export const Event = z.object({
  _id: z.string(),
  run_id: z.string(),
  scenario_id: z.string(),
  ts: SimTime,
  source: z.string(),
  text: z.string(),
  household_id: z.string().optional(),
});

export const Household = z.object({
  run_id: z.string(),
  household_id: z.string(),
  name: z.string().optional(),
  address: z.string().optional(),
  language: z.string().optional(),
  applied_event_ids: z.array(z.string()),
});

export const RelayPromise = z.object({
  _id: z.string(),
  run_id: z.string(),
  scenario_id: z.string(),
  household_id: z.string(),
  text: z.string(),
  keywords: z.array(z.string()),
  made_ts: SimTime,
  due_ts: SimTime,
  status: z.enum(["open", "kept", "lapsed"]),
  source_event_id: z.string(),
  status_ts: SimTime.optional(),
  evidence_event_ids: z.array(z.string()).optional(),
});

export const RegistryEntry = z.object({
  household_id: z.string(),
  opt_in: z.boolean(),
  language: z.string().optional(),
  first_name: z.string().optional(),
  callback_number: z.string().optional(),
  scenario_id: z.string().optional(),
  name: z.string().optional(),
  address: z.string().optional(),
  registered_ts: SimTime.optional(),
});

export const Proposal = z.object({
  _id: z.string(),
  run_id: z.string(),
  scenario_id: z.string(),
  household_id: z.string(),
  kind: z.string(),
  status: z.string(),
  reason: z.string(),
  ts: SimTime,
  cited_event_ids: z.array(z.string()),
  promise_id: z.string().optional(),
  due_ts: SimTime.optional(),
  queue: z.string().optional(),
  urgent: z.boolean().optional(),
  early: z.boolean().optional(),
  suggested_action: z.enum(["call", "visit"]).optional(),
  rationale: z.string().optional(),
  status_ts: SimTime.optional(), // stamped by W2 decide_proposal (db/writes.py advance_status)
});

export const CallRequest = z.object({
  _id: z.string(),
  run_id: z.string(),
  scenario_id: z.string(),
  household_id: z.string(),
  proposal_id: z.string(),
  promise_id: z.string().optional(),
  purpose: z.string(),
  requested_ts: SimTime,
  status: z.string().optional(), // W2 stamps "queued" (db/writes.py schedule_call)
});

/** schemas.SystemEvent; modules add detail fields (e.g. prompt_tokens on runtime "llm_call"). */
export const SystemEvent = z.looseObject({
  run_id: z.string(),
  module: z.string(),
  action: z.string(),
  ts: SimTime,
  _id: z.string().optional(),
});

export const Metric = z.object({
  _id: z.string(),
  run_id: z.string(),
  name: z.string(),
  value: z.number(),
  scope: z.string(),
  ts: SimTime,
});

export const PolicyChange = z.object({
  _id: z.string(),
  run_id: z.string(),
  version: z.number().int(),
  what_changed: z.string(),
  params: z.record(z.string(), z.number()),
  metric_values: z.record(z.string(), z.number()),
  ts: SimTime,
});

/** Event written by W3 when a call ends (source "call_result"; W3-C1 shape, PR #1). */
export const CallResultEvent = Event.extend({
  source: z.literal("call_result"),
  call_id: z.string(),
  outcome: z.enum(["completed", "no_answer", "emergency_escalated", "refused_no_opt_in", "failed"]),
  answered: z.boolean().optional(),
  emergency_phrase: z.string().nullable().optional(),
});

export const RunMeta = z.object({
  run_id: z.string(),
  scenario_id: z.string(),
  day0: z.string(),
  mode: z.string(),
});

// Scenario truth: planted situations the evaluator scores. The console only uses them to let a
// presenter jump the playback clock to the next one.
export const Needle = z.object({
  needle_id: z.string(),
  household_id: z.string(),
  required_event_ids: z.array(z.string()),
  deadline: SimTime,
  people_at_risk: z.number().int(),
  danger_at: SimTime,
  response_hours: z.number(),
  kind: z.enum(["broken_promise", "cross_service_join", "silent_household"]),
});

export const PromiseRecallBucket = z.object({
  label: z.string(),
  min_days: z.number(),
  max_days: z.number().nullable(),
  open: z.number().int(),
  recalled: z.number().int(),
  recall: z.number().nullable(),
});

export const PromiseRecall = z.object({
  probe_times: z.array(SimTime),
  open: z.number().int(),
  recalled: z.number().int(),
  recall: z.number().nullable(),
  named_not_open: z.number().int(),
  by_age: z.array(PromiseRecallBucket),
});

export type Event = z.infer<typeof Event>;
export type Household = z.infer<typeof Household>;
export type RelayPromise = z.infer<typeof RelayPromise>;
export type RegistryEntry = z.infer<typeof RegistryEntry>;
export type Proposal = z.infer<typeof Proposal>;
export type RunMeta = z.infer<typeof RunMeta>;
export type CallRequest = z.infer<typeof CallRequest>;
export type SystemEvent = z.infer<typeof SystemEvent>;
export type Metric = z.infer<typeof Metric>;
export type PolicyChange = z.infer<typeof PolicyChange>;
export type CallResultEvent = z.infer<typeof CallResultEvent>;
export type Needle = z.infer<typeof Needle>;
export type PromiseRecall = z.infer<typeof PromiseRecall>;

/** UI assumption until the contract names them: coordinator statuses a proposal moves through. */
export const PROPOSAL_STATUS = { pending: "pending", approved: "approved", dismissed: "dismissed" } as const;
