import { describe, expect, it, vi } from "vitest";
import { HttpApi, SEEDED_RUNS, assertBoardScope, newKey } from "./http";
import { RelayError, type Board } from "./types";

const RUN = "demo-current";
const DISASTER = "demo-storm-2026";
const OTHER_RUN = "demo-history";
const OTHER_DISASTER = "demo-flood-2025";
const core = (id: string, over: { run_id?: string; disaster_id?: string } = {}) => ({
  id,
  run_id: RUN,
  disaster_id: DISASTER,
  created_at: "2026-10-16T12:00:00Z",
  ...over,
});

/** A small, valid board with one row in every scoped table. */
function validBoard(): Board {
  return {
    run_id: RUN,
    disaster: { id: DISASTER, name: "Storm", kind: "storm", region: "Region", started_at: "2026-10-15T00:00:00Z" },
    organizations: [{ id: "org", name: "Org", capabilities: ["food"], region: "Region" }],
    survivors: [{ ...core("s1"), display_name: "Household A", language: "en", call_opt_in: true }],
    requests: [
      {
        ...core("r1"),
        survivor_id: "s1",
        category: "food",
        description: "Synthetic request.",
        status: "open",
        due_at: null,
        organization_id: null,
        promised_at: null,
        source_report_id: "report-1",
      },
    ],
    calls: [
      {
        ...core("c1"),
        request_id: "r1",
        survivor_id: "s1",
        status: "queued",
        provider_conversation_id: null,
        outcome: "pending",
        summary: "",
        evidence_ids: [],
      },
    ],
    verifications: [{ ...core("v1"), request_id: "r1", received: true, source: "human_review", evidence_ids: [], notes: "" }],
    lessons: [
      {
        id: "lesson-own-draft",
        source_disaster_id: DISASTER,
        source_run_id: RUN,
        source_outcome_ids: ["v1"],
        summary: "Own draft",
        conditions: ["food"],
        recommendation: "Do the thing",
        approved: false,
        approved_at: null,
        created_at: "2026-10-16T12:00:00Z",
      },
    ],
    evaluations: [
      {
        ...core("ev1"),
        experiment_id: "exp",
        variant: "with_history",
        case_count: 3,
        metrics: { groundedness: 1 },
        measured_at: "2026-10-16T12:00:00Z",
        trace_url: null,
      },
    ],
    system_events: [{ ...core("evt1"), module: "recovery", action: "request_created", subject_id: "r1", details: {} }],
  };
}

const foreignLesson = (approved: boolean): Board["lessons"][number] => ({
  id: "lesson-foreign",
  source_disaster_id: OTHER_DISASTER,
  source_run_id: OTHER_RUN,
  source_outcome_ids: ["history-received-1"],
  summary: "Foreign",
  conditions: ["food"],
  recommendation: "Do it",
  approved,
  approved_at: approved ? "2025-09-05T12:00:00Z" : null,
  created_at: "2025-09-04T13:00:00Z",
});

function scopeError(board: Board, runId = RUN): RelayError | undefined {
  try {
    assertBoardScope(board, runId);
  } catch (e) {
    return e as RelayError;
  }
  return undefined;
}

function expectRejected(board: Board, message?: RegExp, runId = RUN) {
  const err = scopeError(board, runId);
  expect(err).toBeInstanceOf(RelayError);
  expect(err?.status).toBe(502);
  if (message) expect(err?.message).toMatch(message);
}

const TABLES = ["survivors", "requests", "calls", "verifications", "evaluations", "system_events"] as const;

describe("assertBoardScope", () => {
  it("accepts a valid board and returns it unchanged", () => {
    const board = validBoard();
    expect(assertBoardScope(board, RUN)).toBe(board);
  });

  it("rejects a board for a different run", () => {
    expectRejected(validBoard(), /asked for run demo-history, got run demo-current/, OTHER_RUN);
    const wrong = validBoard();
    wrong.run_id = OTHER_RUN;
    expectRejected(wrong, /got run demo-history/);
  });

  it("rejects a board with no disaster", () => {
    const board = validBoard();
    (board as unknown as { disaster?: unknown }).disaster = undefined;
    expectRejected(board, /no disaster/);
  });

  describe.each(TABLES)("a %s row from elsewhere", (table) => {
    it.each([
      ["another run", { run_id: OTHER_RUN }],
      ["another disaster", { disaster_id: OTHER_DISASTER }],
    ])("is rejected when it belongs to %s", (_label, patch) => {
      const board = validBoard();
      Object.assign((board[table] as unknown as Record<string, unknown>[])[0], patch);
      expectRejected(board, new RegExp(table));
    });

    it("is rejected even when only one of several rows is foreign", () => {
      const board = validBoard();
      const rows = board[table] as unknown as Record<string, unknown>[];
      rows.push({ ...rows[0], id: `${rows[0].id}-foreign`, run_id: OTHER_RUN, disaster_id: OTHER_DISASTER });
      expectRejected(board, new RegExp(table));
    });
  });

  it.each(["phone", "phone_number", "email", "address", "callback_number"])("rejects a survivor that exposes %s", (field) => {
    const board = validBoard();
    Object.assign(board.survivors[0], { [field]: "server-only" });
    expectRejected(board, new RegExp(`server-only field "${field}"`));
  });

  it("rejects an unapproved lesson from another disaster", () => {
    const board = validBoard();
    board.lessons.push(foreignLesson(false));
    expectRejected(board, /unapproved lesson from another disaster/);
  });

  it("allows an approved lesson from another disaster: the only cross-disaster channel", () => {
    const board = validBoard();
    board.lessons.push(foreignLesson(true));
    expect(scopeError(board)).toBeUndefined();
  });

  it("allows this run's own unapproved draft, but not an unapproved draft from another run of the same disaster", () => {
    expect(scopeError(validBoard())).toBeUndefined();
    const board = validBoard();
    board.lessons.push({ ...foreignLesson(false), source_disaster_id: DISASTER });
    expectRejected(board, /unapproved lesson/);
  });
});

// ---------------------------------------------------------------------------------------------------------------------

type Call = { url: string; method?: string; body?: Record<string, unknown> };

/** Fake fetch that records requests and answers by a handler (default: an empty 200 shaped for every response). */
function fakeFetch(handler: (url: string, method: string) => { status?: number; body?: unknown } = () => ({})) {
  const calls: Call[] = [];
  const fn = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const method = init?.method ?? "GET";
    calls.push({ url, method, body: typeof init?.body === "string" ? (JSON.parse(init.body) as Record<string, unknown>) : undefined });
    const { status = 200, body = { request: {}, verification: {}, call: {}, lesson: {}, evaluations: [], requests: [] } } = handler(url, method);
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  });
  return { calls, fetch: fn as unknown as typeof fetch };
}

const BASE = "http://relay.test";
const api = (handler?: Parameters<typeof fakeFetch>[0]) => {
  const f = fakeFetch(handler);
  return { ...f, api: new HttpApi(BASE, f.fetch) };
};
const notFound = () => ({ status: 404, body: { error: "not found" } });

describe("HttpApi reads", () => {
  it("health() is null for the old {ok:true} route with no live-service status", async () => {
    expect(await api(() => ({ body: { ok: true } })).api.health()).toBeNull();
  });

  it("health() returns the report when live status is present, and null on 404", async () => {
    const report = { ok: true, store: "surreal", live: { elevenlabs: false, arize: false, surreal: true } };
    expect(await api(() => ({ body: report })).api.health()).toEqual(report);
    expect(await api(notFound).api.health()).toBeNull();
  });

  it("health() surfaces other failures instead of hiding them", async () => {
    await expect(api(() => ({ status: 503, body: { error: "down" } })).api.health()).rejects.toMatchObject({ status: 503, message: "down" });
  });

  it("runs() falls back to the seeded runs for the old {runs:[{run_id,scenario_id}]} shape", async () => {
    const old = { runs: [{ run_id: "run-1", scenario_id: "scenario-1" }] };
    expect(await api(() => ({ body: old })).api.runs()).toEqual(SEEDED_RUNS);
  });

  it("runs() falls back to the seeded runs on a 404 and on an empty list", async () => {
    expect(await api(notFound).api.runs()).toEqual(SEEDED_RUNS);
    expect(await api(() => ({ body: { runs: [] } })).api.runs()).toEqual(SEEDED_RUNS);
  });

  it("runs() returns the backend's runs when they have the new shape, dropping malformed rows", async () => {
    const body = { runs: [{ run_id: "r1", disaster_id: "d1" }, { run_id: "r2", scenario_id: "old" }] };
    expect(await api(() => ({ body })).api.runs()).toEqual([{ run_id: "r1", disaster_id: "d1" }]);
  });

  it("recommendations() is null on a 404 and the list otherwise", async () => {
    expect(await api(notFound).api.recommendations(RUN, "r1")).toBeNull();
    const recs = [{ lesson_id: "l1" }];
    expect(await api(() => ({ body: { recommendations: recs } })).api.recommendations(RUN, "r1")).toEqual(recs);
  });

  it("reset() is false on a 404 and true when the backend resets", async () => {
    expect(await api(notFound).api.reset()).toBe(false);
    expect(await api(() => ({ body: { ok: true } })).api.reset()).toBe(true);
  });

  it("board() refuses a payload that mixes runs", async () => {
    const mixed = validBoard();
    mixed.requests[0].run_id = OTHER_RUN;
    await expect(api(() => ({ body: mixed })).api.board(RUN)).rejects.toMatchObject({ status: 502 });
    expect(await api(() => ({ body: validBoard() })).api.board(RUN)).toMatchObject({ run_id: RUN });
  });
});

describe("HttpApi requests and errors", () => {
  it("startCall() on a 404 throws a clear RelayError", async () => {
    const { api: http } = api(notFound);
    const err = await http.startCall(RUN, "call-1", "yes").catch((e: unknown) => e);
    expect(err).toBeInstanceOf(RelayError);
    expect((err as RelayError).status).toBe(404);
    expect((err as RelayError).message).toMatch(/cannot start a call yet/);
  });

  it("startCall() passes other backend errors through unchanged", async () => {
    const { api: http } = api(() => ({ status: 409, body: { error: "call is not queued" } }));
    await expect(http.startCall(RUN, "call-1", "no")).rejects.toMatchObject({ status: 409, message: "call is not queued" });
  });

  it("startCall() asks for a scripted call only", async () => {
    const { api: http, calls } = api();
    await http.startCall(RUN, "call-1", "no_answer");
    expect(calls[0]).toMatchObject({ method: "POST", url: `${BASE}/runs/${RUN}/calls/call-1/start` });
    expect(calls[0].body).toMatchObject({ mode: "scripted", scripted_answer: "no_answer" });
  });

  it("startVoiceSession() posts the idempotency key to the run-scoped voice-session route", async () => {
    const { api: http, calls } = api(() => ({ body: { session_id: "s", call_id: "call-1", signed_url: "wss://x", custom_llm_extra_body: { relay_session_id: "s" } } }));
    const session = await http.startVoiceSession(RUN, "req 1", { idempotency_key: "k1" });
    expect(calls[0]).toMatchObject({ method: "POST", url: `${BASE}/runs/${RUN}/requests/req%201/voice-session` });
    expect(calls[0].body).toEqual({ idempotency_key: "k1" });
    expect(session.custom_llm_extra_body).toEqual({ relay_session_id: "s" });
  });

  it("startVoiceSession() surfaces the consent refusal from the server", async () => {
    const { api: http } = api(() => ({ status: 409, body: { error: "confirmed survivor call opt-in is required" } }));
    await expect(http.startVoiceSession(RUN, "req-1", { idempotency_key: "k" })).rejects.toMatchObject({ status: 409, message: "confirmed survivor call opt-in is required" });
  });

  it("uses the contract routes under the base URL with no /api prefix, and encodes ids", async () => {
    const f = fakeFetch();
    const http = new HttpApi(`${BASE}/`, f.fetch);
    await http.claim("run/1", "req 1", { organization_id: "org", promised_at: "2026-10-16T18:00:00Z" });
    await http.report(RUN, { disaster_id: DISASTER, survivor_id: "s1", text: "We need food" });
    expect(f.calls.map((c) => c.url)).toEqual([`${BASE}/runs/run%2F1/requests/req%201/claim`, `${BASE}/runs/${RUN}/reports`]);
  });

  it("turns an error body into a RelayError with its status and message", async () => {
    const { api: http } = api(() => ({ status: 409, body: { error: "request already claimed or closed" } }));
    await expect(http.claim(RUN, "r1", { organization_id: "o", promised_at: "x" })).rejects.toMatchObject({
      name: "RelayError",
      status: 409,
      message: "request already claimed or closed",
    });
  });

  it("reports an unreachable API as status 0", async () => {
    const http = new HttpApi(BASE, (async () => {
      throw new TypeError("fetch failed");
    }) as unknown as typeof fetch);
    await expect(http.disasters()).rejects.toMatchObject({ status: 0, message: expect.stringContaining("unreachable") });
  });

  it("verify() always sends source human_review with no evidence, whatever the caller passes", async () => {
    const { api: http, calls } = api();
    await http.verify(RUN, "r1", { received: true, notes: "Confirmed by phone" });
    // A UI submission must never fabricate a survivor call, even if a caller tries to smuggle one in.
    await http.verify(RUN, "r1", { received: false, notes: "x", source: "survivor_call", evidence_ids: ["fake-call:utterance:1"] } as never);
    expect(calls).toHaveLength(2);
    for (const c of calls) {
      expect(c.url).toBe(`${BASE}/runs/${RUN}/requests/r1/verify`);
      expect(c.body).toMatchObject({ source: "human_review", evidence_ids: [] });
    }
    expect(calls.map((c) => c.body?.received)).toEqual([true, false]);
  });

  it("sends a distinct, non-empty idempotency_key on every mutation", async () => {
    const { api: http, calls } = api();
    await http.report(RUN, { disaster_id: DISASTER, survivor_id: "s1", text: "food" });
    await http.claim(RUN, "r1", { organization_id: "o", promised_at: "2026-10-16T18:00:00Z" });
    await http.deliver(RUN, "r1", { organization_id: "o", notes: "dropped off" });
    await http.verify(RUN, "r1", { received: null, notes: "" });
    await http.queueFollowUp(RUN, "r1");
    await http.startCall(RUN, "c1", "yes");
    await http.draftLesson(RUN, { source_outcome_ids: ["v1"], summary: "s", conditions: ["food"], recommendation: "r" });
    await http.approveLesson(RUN, "l1");
    await http.compare(RUN);
    await http.reset();
    // Repeating the same mutation is a new action, so it gets a new key.
    await http.claim(RUN, "r1", { organization_id: "o", promised_at: "2026-10-16T18:00:00Z" });

    const posts = calls.filter((c) => c.method === "POST");
    expect(posts).toHaveLength(11);
    const keys = posts.map((c) => c.body?.idempotency_key);
    for (const key of keys) {
      expect(typeof key).toBe("string");
      expect((key as string).length).toBeGreaterThan(0);
    }
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("sends no body on reads", async () => {
    const { api: http, calls } = api(() => ({ body: { disasters: [] } }));
    await http.disasters();
    expect(calls[0]).toMatchObject({ method: "GET", body: undefined });
  });
});

describe("newKey", () => {
  it("prefixes and never repeats", () => {
    const keys = Array.from({ length: 50 }, () => newKey("claim"));
    expect(keys.every((k) => k.startsWith("claim:") && k.length > "claim:".length)).toBe(true);
    expect(new Set(keys).size).toBe(50);
  });
});
