// HttpApi: the workspace's only path to live data. The browser talks to the Relay Python API
// (NEXT_PUBLIC_RELAY_API_URL) and holds no database driver or service secret.
import {
  RelayError,
  type Board,
  type CompareResult,
  type Disaster,
  type Health,
  type Lesson,
  type Recommendation,
  type RelayApi,
  type RelayCall,
  type RelayRequest,
  type ReportResult,
  type RunInfo,
  type ScriptedAnswer,
  type Verification,
} from "./types";

type Fetch = typeof fetch;

const SERVER_ONLY_FIELDS = ["phone", "phone_number", "email", "address", "callback_number"];

/** Seeded demo runs, used only when the backend's /runs route is missing or still has the old shape. */
export const SEEDED_RUNS: RunInfo[] = [
  { run_id: "demo-current", disaster_id: "demo-storm-2026" },
  { run_id: "demo-history", disaster_id: "demo-flood-2025" },
];

export function newKey(prefix: string): string {
  const id = globalThis.crypto?.randomUUID?.() ?? `${Date.now()}-${Math.random().toString(36).slice(2)}`;
  return `${prefix}:${id}`;
}

/**
 * Reject a board that mixes runs or disasters, or carries contact details. The server is the authority on
 * isolation; this guards the UI from ever rendering another run's survivor records.
 */
export function assertBoardScope(board: Board, runId: string): Board {
  if (board.run_id !== runId) throw new RelayError(`asked for run ${runId}, got run ${board.run_id}`, 502);
  const disasterId = board.disaster?.id;
  if (!disasterId) throw new RelayError("board has no disaster", 502);
  for (const table of ["survivors", "requests", "calls", "verifications", "evaluations", "system_events"] as const) {
    const foreign = (board[table] as { run_id?: string; disaster_id?: string }[]).find(
      (row) => row.run_id !== runId || row.disaster_id !== disasterId,
    );
    if (foreign) throw new RelayError(`${table} contains a record from another run or disaster`, 502);
  }
  for (const survivor of board.survivors) {
    const leaked = SERVER_ONLY_FIELDS.find((field) => field in (survivor as unknown as Record<string, unknown>));
    if (leaked) throw new RelayError(`survivor payload exposed server-only field "${leaked}"`, 502);
  }
  // Another disaster's lessons are allowed only when approved: that is the sole cross-disaster channel.
  const badLesson = board.lessons.find((lesson) => {
    const own = lesson.source_run_id === runId && lesson.source_disaster_id === disasterId;
    return !own && lesson.approved !== true;
  });
  if (badLesson) throw new RelayError("board contains an unapproved lesson from another disaster", 502);
  return board;
}

export class HttpApi implements RelayApi {
  readonly kind = "live" as const;

  constructor(
    private readonly base: string,
    private readonly fetchImpl: Fetch = (...a) => fetch(...a),
    private readonly timeoutMs = 8000,
  ) {}

  private url(path: string) {
    return `${this.base.replace(/\/$/, "")}${path}`;
  }

  private async send<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    let res: Response;
    try {
      res = await this.fetchImpl(this.url(path), {
        method,
        cache: "no-store",
        signal: controller.signal,
        headers: body === undefined ? undefined : { "Content-Type": "application/json" },
        body: body === undefined ? undefined : JSON.stringify(body),
      });
    } catch (e) {
      const why = (e as Error).name === "AbortError" ? "timed out" : (e as Error).message;
      throw new RelayError(`Relay API unreachable (${why})`, 0);
    } finally {
      clearTimeout(timer);
    }
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) throw new RelayError((payload as { error?: string }).error ?? `${res.status} ${res.statusText}`, res.status);
    return payload as T;
  }

  async health(): Promise<Health | null> {
    try {
      const h = await this.send<Partial<Health>>("GET", "/health");
      // The old reference route answers {ok: true} with no service status: treat that as "not reported".
      return h.live ? (h as Health) : null;
    } catch (e) {
      if (e instanceof RelayError && e.status === 404) return null;
      throw e;
    }
  }

  async runs(): Promise<RunInfo[]> {
    try {
      const { runs } = await this.send<{ runs: Partial<RunInfo>[] }>("GET", "/runs");
      const valid = runs.filter((r): r is RunInfo => typeof r.run_id === "string" && typeof r.disaster_id === "string");
      return valid.length ? valid : SEEDED_RUNS;
    } catch (e) {
      if (e instanceof RelayError && e.status === 404) return SEEDED_RUNS;
      throw e;
    }
  }

  async disasters(): Promise<Disaster[]> {
    return (await this.send<{ disasters: Disaster[] }>("GET", "/disasters")).disasters;
  }

  async board(runId: string): Promise<Board> {
    return assertBoardScope(await this.send<Board>("GET", `/runs/${encodeURIComponent(runId)}/board`), runId);
  }

  private run(runId: string, ...rest: string[]) {
    return ["/runs", runId, ...rest].map((p, i) => (i === 0 ? p : encodeURIComponent(p))).join("/");
  }

  report(runId: string, input: { disaster_id: string; survivor_id: string; text: string }): Promise<ReportResult> {
    return this.send("POST", this.run(runId, "reports"), { ...input, idempotency_key: newKey("report") });
  }

  async claim(runId: string, requestId: string, input: { organization_id: string; promised_at: string }): Promise<RelayRequest> {
    const { request } = await this.send<{ request: RelayRequest }>("POST", this.run(runId, "requests", requestId, "claim"), {
      ...input,
      idempotency_key: newKey("claim"),
    });
    return request;
  }

  async deliver(runId: string, requestId: string, input: { organization_id: string; notes: string }): Promise<RelayRequest> {
    const { request } = await this.send<{ request: RelayRequest }>("POST", this.run(runId, "requests", requestId, "delivery"), {
      ...input,
      idempotency_key: newKey("delivery"),
    });
    return request;
  }

  verify(runId: string, requestId: string, input: { received: boolean | null; notes: string }) {
    // A UI submission is always a human review; survivor_call evidence is server-generated only.
    return this.send<{ request: RelayRequest; verification: Verification }>("POST", this.run(runId, "requests", requestId, "verify"), {
      ...input,
      source: "human_review",
      evidence_ids: [],
      idempotency_key: newKey("verify"),
    });
  }

  async queueFollowUp(runId: string, requestId: string): Promise<RelayCall> {
    const { call } = await this.send<{ call: RelayCall }>("POST", this.run(runId, "requests", requestId, "follow-up"), {
      idempotency_key: newKey("follow-up"),
    });
    return call;
  }

  async startCall(runId: string, callId: string, answer: ScriptedAnswer) {
    try {
      return await this.send<{ call: RelayCall; request?: RelayRequest }>("POST", this.run(runId, "calls", callId, "start"), {
        idempotency_key: newKey("call-start"),
        mode: "scripted",
        scripted_answer: answer,
      });
    } catch (e) {
      if (e instanceof RelayError && e.status === 404) {
        throw new RelayError("This backend cannot start a call yet (the call-start route is not available).", 404);
      }
      throw e;
    }
  }

  async recommendations(runId: string, requestId: string): Promise<Recommendation[] | null> {
    try {
      return (await this.send<{ recommendations: Recommendation[] }>("GET", this.run(runId, "requests", requestId, "recommendations")))
        .recommendations;
    } catch (e) {
      if (e instanceof RelayError && e.status === 404) return null;
      throw e;
    }
  }

  async draftLesson(runId: string, input: { source_outcome_ids: string[]; summary: string; conditions: string[]; recommendation: string }) {
    const { lesson } = await this.send<{ lesson: Lesson }>("POST", this.run(runId, "lessons"), { ...input, idempotency_key: newKey("lesson") });
    return lesson;
  }

  async approveLesson(runId: string, lessonId: string) {
    const { lesson } = await this.send<{ lesson: Lesson }>("POST", this.run(runId, "lessons", lessonId, "approve"), {
      idempotency_key: newKey("approve"),
    });
    return lesson;
  }

  compare(runId: string): Promise<CompareResult> {
    return this.send("POST", this.run(runId, "evaluations", "compare"), { idempotency_key: newKey("compare") });
  }

  async reset(): Promise<boolean> {
    try {
      await this.send("POST", "/demo/reset", { idempotency_key: newKey("reset") });
      return true;
    } catch (e) {
      if (e instanceof RelayError && e.status === 404) return false;
      throw e;
    }
  }
}
