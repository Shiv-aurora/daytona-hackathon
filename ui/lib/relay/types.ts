// TypeScript mirror of contracts/demo.md (integration-owned; do not diverge). Phone numbers never appear here:
// they are server-only. Optional fields marked "requested" are asks to the backend that the UI tolerates missing.

export type RequestStatus = "open" | "claimed" | "awaiting_verification" | "resolved" | "reopened";

export interface Core {
  id: string;
  run_id: string;
  disaster_id: string;
  created_at: string;
}

export interface Disaster {
  id: string;
  name: string;
  kind: string;
  region: string;
  started_at: string;
}

export interface Organization {
  id: string;
  name: string;
  capabilities: string[];
  region: string;
}

export interface Survivor extends Core {
  display_name: string;
  language: string;
  call_opt_in: boolean;
}

export interface RelayRequest extends Core {
  survivor_id: string;
  category: string;
  description: string;
  status: RequestStatus;
  due_at: string | null;
  organization_id: string | null;
  promised_at: string | null;
  source_report_id: string;
  delivery_notes?: string;
  conditions?: string[]; // requested: derived by intake, e.g. access_blocked
}

export type CallOutcome =
  | "pending"
  | "verified_received"
  | "not_received"
  | "unverified"
  | "no_answer"
  | "failed"
  | "refused_no_opt_in"
  | "emergency_escalated";

export interface RelayCall extends Core {
  request_id: string;
  survivor_id: string;
  status: "queued" | "active" | "completed" | string;
  provider_conversation_id: string | null;
  outcome: CallOutcome | string;
  summary: string;
  evidence_ids: string[];
  mode?: "scripted" | "live"; // requested
  disclosure?: string; // requested: fixed, code-owned text rendered verbatim
}

export interface Verification extends Core {
  request_id: string;
  received: boolean | null;
  source: "survivor_call" | "human_review";
  evidence_ids: string[];
  notes: string;
}

export interface Lesson {
  id: string;
  source_disaster_id: string;
  source_run_id: string;
  source_outcome_ids: string[];
  summary: string;
  conditions: string[];
  recommendation: string;
  approved: boolean;
  approved_at: string | null;
  created_at: string;
}

export interface Evaluation extends Core {
  experiment_id: string;
  variant: "without_history" | "with_history";
  case_count: number;
  metrics: Record<string, number | null>;
  measured_at: string;
  trace_url: string | null;
}

export interface SystemEvent extends Core {
  module: string;
  action: string;
  subject_id: string;
  details: Record<string, unknown>;
}

export interface Board {
  run_id: string;
  disaster: Disaster;
  organizations: Organization[];
  survivors: Survivor[];
  requests: RelayRequest[];
  calls: RelayCall[];
  verifications: Verification[];
  lessons: Lesson[];
  evaluations: Evaluation[];
  system_events: SystemEvent[];
  as_of?: string; // requested: server time
}

export interface RunInfo {
  run_id: string;
  disaster_id: string;
}

export interface Health {
  ok: boolean;
  store: string;
  live: { elevenlabs: boolean; arize: boolean; surreal: boolean; daytona?: boolean };
}

/**
 * A consent-checked browser voice session from POST /runs/{run}/requests/{id}/voice-session.
 * The server owns everything: the browser only gets an opaque session id to pass back as the Custom LLM extra body,
 * so every caller turn goes through the code-owned emergency check before any model.
 */
export interface VoiceSession {
  session_id: string;
  provider: "elevenlabs" | "fake" | string;
  live: boolean;
  run_id: string;
  disaster_id: string;
  request_id: string;
  call_id: string;
  signed_url: string | null;
  conversation_id: string | null;
  custom_llm_extra_body: Record<string, unknown>;
  disclosure: string;
  question: string;
}

export interface Recommendation {
  lesson_id: string;
  summary: string;
  recommendation: string;
  matched_conditions: string[];
  source_disaster_id: string;
  source_outcomes: { id: string; received: boolean | null; notes: string; source: string }[];
  applicability?: string;
}

export interface EvalCase {
  id: string;
  report: string;
  without_history: { decision: Record<string, unknown> };
  with_history: { decision: Record<string, unknown>; lesson_ids?: string[] };
  differs: boolean;
}

export interface CompareResult {
  evaluations: Evaluation[];
  cases?: EvalCase[]; // requested
  synthetic?: boolean; // requested
  case_count?: number;
}

export interface ReportResult {
  requests: RelayRequest[];
  escalated?: boolean;
  message?: string;
}

export type ScriptedAnswer = "no" | "yes" | "no_answer";

/** Everything the workspace needs from a backend. Implemented by HttpApi (live) and MockApi (simulated). */
export interface RelayApi {
  readonly kind: "live" | "mock";
  /** null when the backend has no /health route (live-service status unknown). */
  health(): Promise<Health | null>;
  runs(): Promise<RunInfo[]>;
  disasters(): Promise<Disaster[]>;
  board(runId: string): Promise<Board>;
  report(runId: string, input: { disaster_id: string; survivor_id: string; text: string }): Promise<ReportResult>;
  claim(runId: string, requestId: string, input: { organization_id: string; promised_at: string }): Promise<RelayRequest>;
  deliver(runId: string, requestId: string, input: { organization_id: string; notes: string }): Promise<RelayRequest>;
  verify(
    runId: string,
    requestId: string,
    input: { received: boolean | null; notes: string },
  ): Promise<{ request: RelayRequest; verification: Verification }>;
  queueFollowUp(runId: string, requestId: string): Promise<RelayCall>;
  startCall(runId: string, callId: string, answer: ScriptedAnswer): Promise<{ call: RelayCall; request?: RelayRequest }>;
  /** null when the backend has no recommendations route yet. */
  recommendations(runId: string, requestId: string): Promise<Recommendation[] | null>;
  draftLesson(
    runId: string,
    input: { source_outcome_ids: string[]; summary: string; conditions: string[]; recommendation: string },
  ): Promise<Lesson>;
  approveLesson(runId: string, lessonId: string): Promise<Lesson>;
  compare(runId: string): Promise<CompareResult>;
  /** null when the backend has no reset route. */
  reset(): Promise<boolean>;
  /** Live API only: open a voice session with the ElevenLabs agent for a delivered, opted-in request. */
  startVoiceSession?(runId: string, requestId: string, input: { idempotency_key: string }): Promise<VoiceSession>;
}

export class RelayError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = "RelayError";
  }
}
