import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import compareFixture from "./compare_fixture.json";
import { SEEDED_RUNS, assertBoardScope } from "./http";
import { FIXED_DISCLOSURE, MockApi, categoriesOf, conditionsOf, detectEmergency } from "./mock";
import { RelayError, type Board, type RelayRequest } from "./types";

const RUN = "demo-current";
const DISASTER = "demo-storm-2026";
const HISTORY = "demo-history";
const HISTORY_DISASTER = "demo-flood-2025";
const PROMISED = "2026-10-17T18:00:00Z";
const SURVIVOR_FIELDS = ["call_opt_in", "created_at", "disaster_id", "display_name", "id", "language", "run_id"];

// The mock simulates latency with setTimeout; run it instantly so the suite stays fast.
beforeEach(() => {
  vi.stubGlobal("setTimeout", ((fn: () => void) => {
    queueMicrotask(fn);
    return 0;
  }) as unknown as typeof setTimeout);
});
afterEach(() => vi.unstubAllGlobals());

async function expectStatus(promise: Promise<unknown>, status: number, message?: RegExp) {
  const err = await promise.then(
    () => null,
    (e: unknown) => e,
  );
  expect(err, "expected the call to be rejected").toBeInstanceOf(RelayError);
  expect((err as RelayError).status).toBe(status);
  if (message) expect((err as RelayError).message).toMatch(message);
}

const find = (board: Board, id: string): RelayRequest => board.requests.find((r) => r.id === id)!;
const statusOf = async (api: MockApi, id: string, run = RUN) => find(await api.board(run), id).status;
const eventsOf = (board: Board, action: string, subject?: string) =>
  board.system_events.filter((e) => e.action === action && (subject === undefined || e.subject_id === subject));
const withoutAsOf = (board: Board) => ({ ...board, as_of: undefined });

/** Claim and deliver a request so it is awaiting verification. */
async function toAwaiting(api: MockApi, id = "current-food-1", org = "demo-food") {
  await api.claim(RUN, id, { organization_id: org, promised_at: PROMISED });
  await api.deliver(RUN, id, { organization_id: org, notes: "Left at the door" });
}

const report = (api: MockApi, text: string, survivor = "current-survivor-1") =>
  api.report(RUN, { disaster_id: DISASTER, survivor_id: survivor, text });

describe("MockApi basics", () => {
  it("is a clearly simulated backend that claims no live services", async () => {
    const api = new MockApi();
    expect(api.kind).toBe("mock");
    expect(await api.health()).toEqual({ ok: true, store: "mock", live: { elevenlabs: false, arize: false, surreal: false } });
    expect(await api.runs()).toEqual(SEEDED_RUNS);
    expect((await api.disasters()).map((d) => d.id).sort()).toEqual([HISTORY_DISASTER, DISASTER]);
  });

  it("rejects an unknown run with 404", async () => {
    await expectStatus(new MockApi().board("nope"), 404);
  });
});

describe("claim", () => {
  it("claims an open request with a capable organization", async () => {
    const api = new MockApi();
    const claimed = await api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED });
    expect(claimed).toMatchObject({ status: "claimed", organization_id: "demo-food", promised_at: PROMISED });
    const board = await api.board(RUN);
    expect(find(board, "current-food-1")).toMatchObject({ status: "claimed", organization_id: "demo-food" });
    expect(eventsOf(board, "request_claimed", "current-food-1")).toHaveLength(1);
  });

  it("allows a reopened request to be claimed again", async () => {
    const api = new MockApi();
    expect(await statusOf(api, "current-transport-1")).toBe("reopened");
    const claimed = await api.claim(RUN, "current-transport-1", { organization_id: "demo-transport", promised_at: PROMISED });
    expect(claimed.status).toBe("claimed");
  });

  it("returns 409 unless the request is open or reopened, and a second claim changes nothing", async () => {
    const api = new MockApi();
    await api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED });
    await expectStatus(api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: "2026-10-18T09:00:00Z" }), 409);
    // awaiting_verification (seeded) and resolved are not claimable either.
    await expectStatus(api.claim(RUN, "current-supplies-1", { organization_id: "demo-supplies", promised_at: PROMISED }), 409);
    await api.verify(RUN, "current-supplies-1", { received: true, notes: "Confirmed" });
    await expectStatus(api.claim(RUN, "current-supplies-1", { organization_id: "demo-supplies", promised_at: PROMISED }), 409);

    const board = await api.board(RUN);
    expect(find(board, "current-food-1")).toMatchObject({ status: "claimed", promised_at: PROMISED });
    expect(eventsOf(board, "request_claimed", "current-food-1")).toHaveLength(1);
    expect(find(board, "current-supplies-1").status).toBe("resolved");
  });

  it("returns 400 when the organization cannot supply the category, leaving the request open", async () => {
    const api = new MockApi();
    await expectStatus(api.claim(RUN, "current-food-1", { organization_id: "demo-supplies", promised_at: PROMISED }), 400, /category/);
    expect(find(await api.board(RUN), "current-food-1")).toMatchObject({ status: "open", organization_id: null, promised_at: null });
  });

  it("validates the organization, the request scope and the promised time", async () => {
    const api = new MockApi();
    await expectStatus(api.claim(RUN, "current-food-1", { organization_id: "missing", promised_at: PROMISED }), 404);
    await expectStatus(api.claim(RUN, "history-food-1", { organization_id: "demo-food", promised_at: PROMISED }), 404);
    await expectStatus(api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: "2026-10-17T18:00:00" }), 400, /timezone/);
    await expectStatus(api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: "soon" }), 400);
    expect(await statusOf(api, "current-food-1")).toBe("open");
  });
});

describe("delivery", () => {
  it("by the claiming organization yields awaiting_verification, never resolved, with no verification", async () => {
    const api = new MockApi();
    const before = (await api.board(RUN)).verifications.length;
    await api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED });
    const delivered = await api.deliver(RUN, "current-food-1", { organization_id: "demo-food", notes: "Dropped off 12 meals" });
    expect(delivered.status).toBe("awaiting_verification");
    expect(delivered.status).not.toBe("resolved");
    expect(delivered.delivery_notes).toBe("Dropped off 12 meals");

    const board = await api.board(RUN);
    expect(find(board, "current-food-1").status).toBe("awaiting_verification");
    expect(board.verifications).toHaveLength(before);
    expect(board.verifications.some((v) => v.request_id === "current-food-1")).toBe(false);
    expect(eventsOf(board, "delivery_reported", "current-food-1")).toHaveLength(1);
  });

  it("returns 409 for an unclaimed request or a different organization", async () => {
    const api = new MockApi();
    await expectStatus(api.deliver(RUN, "current-food-1", { organization_id: "demo-food", notes: "" }), 409);
    await api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED });
    await expectStatus(api.deliver(RUN, "current-food-1", { organization_id: "demo-supplies", notes: "" }), 409, /claiming organization/);
    expect(await statusOf(api, "current-food-1")).toBe("claimed");
    // A second delivery report for the same claim is also refused.
    await api.deliver(RUN, "current-food-1", { organization_id: "demo-food", notes: "" });
    await expectStatus(api.deliver(RUN, "current-food-1", { organization_id: "demo-food", notes: "" }), 409);
  });
});

describe("verify", () => {
  it("received=true resolves the request and records a human_review verification", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    const { request, verification } = await api.verify(RUN, "current-food-1", { received: true, notes: "Household confirmed" });
    expect(request.status).toBe("resolved");
    expect(verification).toMatchObject({ request_id: "current-food-1", received: true, source: "human_review", run_id: RUN, disaster_id: DISASTER });
    expect(await statusOf(api, "current-food-1")).toBe("resolved");
  });

  it("received=false reopens the request and records a human escalation", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    const { request, verification } = await api.verify(RUN, "current-food-1", { received: false, notes: "Nothing arrived" });
    expect(request.status).toBe("reopened");
    expect(verification.received).toBe(false);
    const escalations = eventsOf(await api.board(RUN), "human_escalation", "current-food-1");
    expect(escalations).toHaveLength(1);
    expect(escalations[0]).toMatchObject({ module: "recovery", run_id: RUN, disaster_id: DISASTER, details: { reason: "delivery_not_received" } });
  });

  it("received=null keeps the status as it was and still records the verification", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    const awaiting = await api.verify(RUN, "current-food-1", { received: null, notes: "No answer" });
    expect(awaiting.request.status).toBe("awaiting_verification");
    expect(awaiting.verification.received).toBeNull();
    const reopened = await api.verify(RUN, "current-transport-1", { received: null, notes: "Still unclear" });
    expect(reopened.request.status).toBe("reopened");
    const board = await api.board(RUN);
    expect(eventsOf(board, "human_escalation", "current-food-1")).toHaveLength(0);
  });

  it("is always a human review, never a survivor call, whatever the input", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    const input = { received: true, notes: "x", source: "survivor_call", evidence_ids: ["fake:utterance:1"] };
    const { verification } = await api.verify(RUN, "current-food-1", input);
    expect(verification.source).toBe("human_review");
    expect(verification.evidence_ids).toEqual([]);
  });

  it("returns 409 for requests that are not awaiting verification or reopened", async () => {
    const api = new MockApi();
    const before = (await api.board(RUN)).verifications.length;
    await expectStatus(api.verify(RUN, "current-food-1", { received: true, notes: "" }), 409, /not awaiting verification/);
    await api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED });
    await expectStatus(api.verify(RUN, "current-food-1", { received: true, notes: "" }), 409);
    await api.verify(RUN, "current-supplies-1", { received: true, notes: "" });
    await expectStatus(api.verify(RUN, "current-supplies-1", { received: false, notes: "" }), 409);
    expect(await statusOf(api, "current-supplies-1")).toBe("resolved");
    expect((await api.board(RUN)).verifications).toHaveLength(before + 1);
  });

  it("lets a reopened request be verified as received", async () => {
    const api = new MockApi();
    const { request } = await api.verify(RUN, "current-transport-1", { received: true, notes: "Rode with the volunteer" });
    expect(request.status).toBe("resolved");
  });
});

describe("follow-up calls", () => {
  it("queueFollowUp refuses a survivor who has not confirmed call opt-in", async () => {
    const api = new MockApi();
    const board = await api.board(RUN);
    expect(find(board, "current-transport-1")).toMatchObject({ survivor_id: "current-survivor-3", status: "reopened" });
    expect(board.survivors.find((s) => s.id === "current-survivor-3")?.call_opt_in).toBe(false);

    await expectStatus(api.queueFollowUp(RUN, "current-transport-1"), 400, /opt-in/);
    const after = await api.board(RUN);
    expect(after.calls).toHaveLength(board.calls.length);
    expect(eventsOf(after, "call_saved")).toHaveLength(eventsOf(board, "call_saved").length);
  });

  it("queueFollowUp refuses a request that is not awaiting_verification or reopened", async () => {
    const api = new MockApi();
    await expectStatus(api.queueFollowUp(RUN, "current-food-1"), 409); // open
    await api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED });
    await expectStatus(api.queueFollowUp(RUN, "current-food-1"), 409); // claimed
    await api.verify(RUN, "current-supplies-1", { received: true, notes: "" });
    await expectStatus(api.queueFollowUp(RUN, "current-supplies-1"), 409); // resolved
  });

  it("queues a call for an opted-in survivor without starting it, without contact details", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    const before = await api.board(RUN);
    const call = await api.queueFollowUp(RUN, "current-food-1");
    expect(call).toMatchObject({
      request_id: "current-food-1",
      survivor_id: "current-survivor-1",
      status: "queued",
      outcome: "pending",
      provider_conversation_id: null,
      evidence_ids: [],
      mode: "scripted",
      disclosure: FIXED_DISCLOSURE,
    });
    expect(Object.keys(call).filter((k) => /phone|email|address|callback/i.test(k))).toEqual([]);

    const after = await api.board(RUN);
    expect(find(after, "current-food-1").status).toBe("awaiting_verification");
    expect(after.verifications).toHaveLength(before.verifications.length);
    expect(eventsOf(after, "call_saved", call.id)).toHaveLength(1);
    expect(eventsOf(after, "follow_up_started")).toHaveLength(eventsOf(before, "follow_up_started").length);
  });

  it("keeps the disclosure fixed and free of phone numbers", () => {
    expect(FIXED_DISCLOSURE).toMatch(/^This is an automated call from Relay/);
    expect(FIXED_DISCLOSURE).not.toMatch(/\d{3}[-. ]?\d{3,4}/);
  });

  describe("startCall", () => {
    async function queued(api: MockApi, id = "current-food-1") {
      if (id === "current-food-1") await toAwaiting(api);
      return api.queueFollowUp(RUN, id);
    }

    it("only works on a queued call", async () => {
      const api = new MockApi();
      await expectStatus(api.startCall(RUN, "no-such-call", "yes"), 404);
      await expectStatus(api.startCall(RUN, "current-no-answer-1", "yes"), 409); // seeded, already completed
      const call = await queued(api);
      await expectStatus(api.startCall(HISTORY, call.id, "yes"), 404); // out of scope for another run
      await api.startCall(RUN, call.id, "no_answer");
      await expectStatus(api.startCall(RUN, call.id, "yes"), 409, /not queued/);
    });

    it("a 'no' answer reopens the request with a survivor-call verification and a human escalation", async () => {
      const api = new MockApi();
      const call = await queued(api);
      const res = await api.startCall(RUN, call.id, "no");
      expect(res.call).toMatchObject({ status: "completed", outcome: "not_received", disclosure: FIXED_DISCLOSURE });
      expect(res.call.evidence_ids).toEqual([`${call.id}:utterance:1`]);
      expect(res.request?.status).toBe("reopened");

      const board = await api.board(RUN);
      expect(find(board, "current-food-1").status).toBe("reopened");
      const v = board.verifications.filter((x) => x.request_id === "current-food-1");
      expect(v).toHaveLength(1);
      expect(v[0]).toMatchObject({ received: false, source: "survivor_call", evidence_ids: res.call.evidence_ids });
      expect(eventsOf(board, "human_escalation", "current-food-1")).toHaveLength(1);
    });

    it("a 'yes' answer resolves the request with survivor evidence", async () => {
      const api = new MockApi();
      const call = await queued(api);
      const res = await api.startCall(RUN, call.id, "yes");
      expect(res.call.outcome).toBe("verified_received");
      expect(res.request?.status).toBe("resolved");
      const v = (await api.board(RUN)).verifications.filter((x) => x.request_id === "current-food-1");
      expect(v).toHaveLength(1);
      expect(v[0]).toMatchObject({ received: true, source: "survivor_call" });
      expect(v[0].evidence_ids.length).toBeGreaterThan(0);
    });

    it("a 'no_answer' leaves the request unverified, with no verification and no evidence", async () => {
      const api = new MockApi();
      const call = await queued(api);
      const before = await api.board(RUN);
      const res = await api.startCall(RUN, call.id, "no_answer");
      expect(res.call).toMatchObject({ status: "completed", outcome: "no_answer", evidence_ids: [] });
      expect(res.request?.status).toBe("awaiting_verification");

      const after = await api.board(RUN);
      expect(find(after, "current-food-1").status).toBe("awaiting_verification");
      expect(after.verifications).toHaveLength(before.verifications.length);
      expect(eventsOf(after, "human_escalation", "current-food-1")).toHaveLength(0);
      expect(eventsOf(after, "follow_up_started", "current-food-1")).toHaveLength(1);
      expect(eventsOf(after, "follow_up_finished", "current-food-1")[0].details).toMatchObject({ outcome: "no_answer", received: null });
    });

    // BUG (mock.ts startCall -> applyVerification): verify() and the backend's verify_request both refuse (409) a
    // request that is not awaiting_verification/reopened, but startCall applies its result unconditionally. A call
    // queued earlier and started after a human already resolved the request flips it back to reopened.
    // This test states the expected behavior; it passes once the bug is fixed (then remove `.fails`).
    it("a started call does not change a request a human already resolved", async () => {
      const api = new MockApi();
      const call = await queued(api);
      await api.verify(RUN, "current-food-1", { received: true, notes: "Confirmed in person" });
      await api.startCall(RUN, call.id, "no").catch(() => undefined);
      expect(await statusOf(api, "current-food-1")).toBe("resolved");
    });
  });
});

describe("report intake", () => {
  const phrase = "My father fell down and can't get up";

  it("escalates an emergency to a human first: no request, and the escalation is the only event", async () => {
    const api = new MockApi();
    const before = await api.board(RUN);
    const res = await report(api, phrase);
    expect(res.escalated).toBe(true);
    expect(res.requests).toEqual([]);
    expect(res.message).toMatch(/call 911/);

    const after = await api.board(RUN);
    expect(after.requests).toEqual(before.requests); // nothing created, nothing resolved or changed
    const added = after.system_events.slice(before.system_events.length);
    expect(added).toHaveLength(1);
    expect(added[0]).toMatchObject({ module: "intake", action: "human_escalation", subject_id: "current-survivor-1", run_id: RUN, disaster_id: DISASTER });
    expect(added[0].details).toMatchObject({ reason: "fell down" });
    expect(added.some((e) => e.action === "report_received" || e.action === "request_created")).toBe(false);
  });

  it("escalates even when the same report also asks for help, and never creates a request for it", async () => {
    const api = new MockApi();
    const before = await api.board(RUN);
    const res = await report(api, "We need food, and I can’t breathe!");
    expect(res).toMatchObject({ escalated: true, requests: [] });
    expect((await api.board(RUN)).requests).toHaveLength(before.requests.length);
  });

  it("splits 'We need food and blankets' into a food request and a supplies request", async () => {
    const api = new MockApi();
    const before = await api.board(RUN);
    const res = await report(api, "We need food and blankets");
    expect(res.escalated).toBeUndefined();
    expect(res.requests.map((r) => r.category)).toEqual(["food", "supplies"]);
    expect(new Set(res.requests.map((r) => r.source_report_id)).size).toBe(1);
    for (const r of res.requests) {
      expect(r).toMatchObject({ status: "open", organization_id: null, promised_at: null, survivor_id: "current-survivor-1", run_id: RUN, disaster_id: DISASTER });
    }
    const after = await api.board(RUN);
    expect(after.requests).toHaveLength(before.requests.length + 2);
    const added = after.system_events.slice(before.system_events.length).map((e) => e.action);
    expect(added).toEqual(["report_received", "request_created", "request_created"]);
  });

  it("records access conditions found in the report on the new request", async () => {
    const api = new MockApi();
    const { requests } = await report(api, "We need food; the road is blocked.");
    expect(requests).toHaveLength(1);
    expect(requests[0]).toMatchObject({ category: "food", conditions: ["access_blocked"] });
  });

  it("validates its input and scope", async () => {
    const api = new MockApi();
    await expectStatus(report(api, "   "), 400);
    await expectStatus(api.report(RUN, { disaster_id: HISTORY_DISASTER, survivor_id: "current-survivor-1", text: "food" }), 404);
    await expectStatus(report(api, "We need food", "history-survivor-1"), 404); // a survivor from another run
    await expectStatus(api.report("nope", { disaster_id: DISASTER, survivor_id: "current-survivor-1", text: "food" }), 404);
  });
});

describe("emergency, category and condition parsing", () => {
  it("detects emergencies regardless of case, punctuation and curly apostrophes", () => {
    expect(detectEmergency("My father fell down and can't get up")).toBe("fell down");
    expect(detectEmergency("HELP!! I CAN’T BREATHE.")).toBe("can't breathe");
    expect(detectEmergency("There is a gas leak in the kitchen")).toBe("gas leak");
  });

  it("does not flag ordinary phrases that merely contain a trigger", () => {
    for (const text of ["We need food and blankets", "I fell asleep early", "I fell behind on rent", "The fireplace is cold", ""]) {
      expect(detectEmergency(text), text).toBeNull();
    }
  });

  // BUG (mock.ts detectEmergency): String.replace(string, string) only removes the FIRST "i fell asleep", so a second
  // occurrence still matches the "i fell" trigger. calls/safety.py uses str.replace, which removes all of them.
  // Over-escalation is the safe direction, but the mock is meant to mirror the backend. Remove `.fails` once fixed.
  it("ignores every occurrence of a non-emergency phrase, like calls/safety.py", () => {
    expect(detectEmergency("I fell asleep early, then I fell asleep again at noon")).toBeNull();
  });

  it("categorizes needs and defaults to other", () => {
    expect(categoriesOf("We need food and blankets")).toEqual(["food", "supplies"]);
    expect(categoriesOf("need a ride and roof repair")).toEqual(["transportation", "repairs"]);
    expect(categoriesOf("hello there")).toEqual(["other"]);
  });

  it("derives access_blocked only when the report says so", () => {
    expect(conditionsOf("the road is blocked")).toEqual(["access_blocked"]);
    expect(conditionsOf("We need food")).toEqual([]);
  });
});

describe("board scope and privacy", () => {
  const TABLES = ["survivors", "requests", "calls", "verifications", "evaluations", "system_events"] as const;

  it("demo-current contains no demo-history records, and every row matches the run and disaster", async () => {
    const board = await new MockApi().board(RUN);
    expect(board).toMatchObject({ run_id: RUN, disaster: { id: DISASTER } });
    for (const table of TABLES) {
      for (const row of board[table] as { id: string; run_id: string; disaster_id: string; subject_id?: string }[]) {
        expect(row.run_id, `${table}/${row.id}`).toBe(RUN);
        expect(row.disaster_id, `${table}/${row.id}`).toBe(DISASTER);
        expect(row.id).not.toMatch(/^history-/);
        expect(row.subject_id ?? "").not.toMatch(/^history-/);
      }
    }
    expect(board.survivors.map((s) => s.id)).toEqual(expect.arrayContaining(["current-survivor-1", "current-survivor-2", "current-survivor-3"]));
    expect(board.survivors.every((s) => s.id.startsWith("current-"))).toBe(true);
    expect(board.requests.map((r) => r.id)).toEqual(expect.arrayContaining(["current-food-1", "current-supplies-1", "current-transport-1"]));
    expect(board.requests.every((r) => r.id.startsWith("current-"))).toBe(true);
    expect(board.verifications.map((v) => v.id)).toContain("current-missed-1");
    expect(board.verifications.every((v) => v.id.startsWith("current-"))).toBe(true);
    expect(assertBoardScope(board, RUN)).toBe(board);
  });

  it("demo-history is the mirror image and passes the same scope guard", async () => {
    const board = await new MockApi().board(HISTORY);
    for (const table of TABLES) {
      for (const row of board[table] as { id: string; run_id: string; disaster_id: string }[]) {
        expect(row.run_id).toBe(HISTORY);
        expect(row.disaster_id).toBe(HISTORY_DISASTER);
        expect(row.id).not.toMatch(/^current-/);
      }
    }
    expect(board.requests.map((r) => r.id)).toContain("history-food-1");
    expect(board.requests.every((r) => r.id.startsWith("history-"))).toBe(true);
    expect(assertBoardScope(board, HISTORY)).toBe(board);
  });

  it("mutating one run never changes the other run's board", async () => {
    const api = new MockApi();
    const history = withoutAsOf(await api.board(HISTORY));
    await report(api, "We need food and blankets");
    await toAwaiting(api);
    await api.queueFollowUp(RUN, "current-food-1");
    expect(withoutAsOf(await api.board(HISTORY))).toEqual(history);
  });

  it("survivors carry only the contract fields and no key anywhere looks like contact details", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    await api.queueFollowUp(RUN, "current-food-1");
    for (const run of [RUN, HISTORY]) {
      const board = await api.board(run);
      for (const s of board.survivors) expect(Object.keys(s).sort()).toEqual(SURVIVOR_FIELDS);
      const keys: string[] = [];
      JSON.stringify(board, (key, value) => {
        keys.push(key);
        return value;
      });
      expect(keys.filter((k) => /phone|email|address|callback/i.test(k))).toEqual([]);
    }
  });

  it("returns copies, so a caller cannot edit the mock's data through a board", async () => {
    const api = new MockApi();
    const board = await api.board(RUN);
    find(board, "current-food-1").status = "resolved";
    board.survivors[0].display_name = "Edited";
    const again = await api.board(RUN);
    expect(find(again, "current-food-1").status).toBe("open");
    expect(again.survivors[0].display_name).not.toBe("Edited");
  });
});

describe("lessons", () => {
  const SUMMARY = "A reported delivery failed and a coordinator arranged a confirmed handoff.";
  const draft = (api: MockApi, over: Partial<Parameters<MockApi["draftLesson"]>[1]> = {}, run = HISTORY) =>
    api.draftLesson(run, {
      source_outcome_ids: run === HISTORY ? ["history-received-1"] : ["current-missed-1"],
      summary: SUMMARY,
      conditions: ["food", "access_blocked"],
      recommendation: "Confirm an accessible handoff point before delivery.",
      ...over,
    });
  const lessonIds = async (api: MockApi, run: string) => (await api.board(run)).lessons.map((l) => l.id);

  it("shows another disaster's lessons only once approved", async () => {
    const api = new MockApi();
    const seededApproved = ["lesson-confirm-handoff", "lesson-shelter-checkin", "lesson-medicine-pickup"];
    expect(await lessonIds(api, RUN)).toEqual(seededApproved); // only the seeded, approved lessons
    expect(await lessonIds(api, RUN)).not.toContain("lesson-repairs-access"); // a seeded draft stays in its own run

    const lesson = await draft(api);
    expect(lesson).toMatchObject({ approved: false, approved_at: null, source_run_id: HISTORY, source_disaster_id: HISTORY_DISASTER });
    expect(await lessonIds(api, HISTORY)).toContain(lesson.id); // its own run sees the draft
    expect(await lessonIds(api, RUN)).not.toContain(lesson.id); // another disaster does not

    const approved = await api.approveLesson(HISTORY, lesson.id);
    expect(approved.approved).toBe(true);
    expect(approved.approved_at).toEqual(expect.any(String));
    const board = await api.board(RUN);
    expect(board.lessons.map((l) => l.id)).toContain(lesson.id);
    expect(assertBoardScope(board, RUN)).toBe(board);
  });

  it("keeps the current run's draft away from the history run until it is approved", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    const { verification } = await api.verify(RUN, "current-food-1", { received: true, notes: "Confirmed" });
    const lesson = await draft(api, { source_outcome_ids: [verification.id] }, RUN);
    expect(await lessonIds(api, RUN)).toContain(lesson.id);
    expect(await lessonIds(api, HISTORY)).not.toContain(lesson.id);
    await api.approveLesson(RUN, lesson.id);
    expect(await lessonIds(api, HISTORY)).toContain(lesson.id);
  });

  it("refuses a lesson with no confirmed receipt", async () => {
    const api = new MockApi();
    await expectStatus(draft(api, { source_outcome_ids: [] }), 400);
    // current-missed-1 is a received=false verification, so it cannot support a lesson.
    await expectStatus(draft(api, { source_outcome_ids: ["current-missed-1"] }, RUN), 400, /confirmed receipt/);
    // Outcomes from another run are out of scope.
    await expectStatus(draft(api, { source_outcome_ids: ["history-received-1"] }, RUN), 404);
    await expectStatus(draft(api, { summary: "  " }), 400);
  });

  it("refuses a lesson containing a survivor display name, an email or a phone number", async () => {
    const api = new MockApi();
    const beforeBoard = await api.board(HISTORY);
    const before = beforeBoard.lessons.length;
    await expectStatus(draft(api, { summary: "Fictional household A did not get the delivery." }), 400, /de-identified/);
    await expectStatus(draft(api, { recommendation: "call fictional HOUSEHOLD h first" }), 400, /de-identified/);
    await expectStatus(draft(api, { conditions: ["Fictional household B"] }), 400, /de-identified/);
    await expectStatus(draft(api, { summary: "Email jo@example.com to confirm." }), 400, /de-identified/);
    await expectStatus(draft(api, { recommendation: "Call 555-123-4567 to confirm." }), 400, /de-identified/);
    await expectStatus(draft(api, { recommendation: "Call +1 (555) 123 4567 to confirm." }), 400, /de-identified/);
    const board = await api.board(HISTORY);
    expect(board.lessons).toHaveLength(before);
    expect(eventsOf(board, "lesson_drafted")).toHaveLength(eventsOf(beforeBoard, "lesson_drafted").length);
  });

  it("approveLesson works for the owning run, emits an event, and 404s otherwise", async () => {
    const api = new MockApi();
    const lesson = await draft(api);
    expect(eventsOf(await api.board(HISTORY), "lesson_drafted", lesson.id)).toHaveLength(1);
    await expectStatus(api.approveLesson(RUN, lesson.id), 404); // another run cannot approve it
    await expectStatus(api.approveLesson(HISTORY, "missing"), 404);
    expect((await api.approveLesson(HISTORY, lesson.id)).approved).toBe(true);
    expect(eventsOf(await api.board(HISTORY), "lesson_approved", lesson.id)).toHaveLength(1);
  });
});

describe("recommendations", () => {
  it("suggests the approved lesson for a food request, citing its source outcomes", async () => {
    const api = new MockApi();
    const recs = await api.recommendations(RUN, "current-food-1");
    expect(recs).toHaveLength(1);
    expect(recs![0]).toMatchObject({
      lesson_id: "lesson-confirm-handoff",
      matched_conditions: ["food"],
      source_disaster_id: HISTORY_DISASTER,
    });
    expect(recs![0].source_outcomes.map((o) => [o.id, o.received])).toEqual([
      ["history-missed-1", false],
      ["history-received-1", true],
    ]);
  });

  it("matches the access_blocked condition derived from a report", async () => {
    const api = new MockApi();
    const { requests } = await report(api, "We need food; the road is blocked.");
    const recs = await api.recommendations(RUN, requests[0].id);
    expect(recs?.[0]).toMatchObject({ lesson_id: "lesson-confirm-handoff", matched_conditions: ["food", "access_blocked"] });
    expect(recs?.[0].applicability).toMatch(/food \+ access_blocked/);
  });

  it("returns nothing when no approved lesson applies, and never leaks survivor names", async () => {
    const api = new MockApi();
    expect(await api.recommendations(RUN, "current-supplies-1")).toEqual([]);
    expect(await api.recommendations(HISTORY, "history-food-1")).toEqual([]); // the lesson is this disaster's own
    expect(JSON.stringify(await api.recommendations(RUN, "current-food-1"))).not.toMatch(/Fictional household/);
  });

  it("ignores unapproved lessons until they are approved", async () => {
    const api = new MockApi();
    const lesson = await api.draftLesson(HISTORY, {
      source_outcome_ids: ["history-received-1"],
      summary: "Drop food at the nearest open road.",
      conditions: ["food"],
      recommendation: "Meet at the nearest open road.",
    });
    expect((await api.recommendations(RUN, "current-food-1"))?.map((r) => r.lesson_id)).toEqual(["lesson-confirm-handoff"]);
    await api.approveLesson(HISTORY, lesson.id);
    expect((await api.recommendations(RUN, "current-food-1"))?.map((r) => r.lesson_id)).toEqual(["lesson-confirm-handoff", lesson.id]);
  });

  it("404s for an unknown or out-of-scope request", async () => {
    const api = new MockApi();
    await expectStatus(api.recommendations(RUN, "missing"), 404);
    await expectStatus(api.recommendations(RUN, "history-food-1"), 404);
  });
});

describe("compare", () => {
  it("returns the recorded fixture, labeled synthetic, scoped to the current run", async () => {
    const result = await new MockApi().compare(RUN);
    expect(result.case_count).toBe(3);
    expect(result.cases).toHaveLength(3);
    expect(result.synthetic).toBe(true);
    expect(result.evaluations.map((e) => e.variant).sort()).toEqual(["with_history", "without_history"]);
    for (const e of result.evaluations) {
      expect(e).toMatchObject({ run_id: RUN, disaster_id: DISASTER, case_count: 3 });
      const recorded = compareFixture.evaluations.find((f) => f.variant === e.variant)!;
      expect(e.metrics).toEqual(recorded.metrics); // measured values are replayed, never recomputed
      expect(e.id).not.toBe(recorded.id);
    }
  });

  it("does not duplicate evaluations or events when called twice", async () => {
    const api = new MockApi();
    const first = await api.compare(RUN);
    const second = await api.compare(RUN);
    expect(second.evaluations.map((e) => e.id)).toEqual(first.evaluations.map((e) => e.id));
    const board = await api.board(RUN);
    expect(board.evaluations).toHaveLength(2);
    expect(eventsOf(board, "evaluation_saved")).toHaveLength(1);
    expect(assertBoardScope(board, RUN)).toBe(board);
    expect((await api.board(HISTORY)).evaluations).toEqual([]);
  });

  it("has no cases for the history run", async () => {
    const api = new MockApi();
    await expectStatus(api.compare(HISTORY), 400);
    await expectStatus(api.compare("nope"), 404);
    expect((await api.board(HISTORY)).evaluations).toEqual([]);
  });
});

describe("events and reset", () => {
  it("every mutation emits a system event scoped to the run and disaster", async () => {
    const api = new MockApi();
    let count = (await api.board(RUN)).system_events.length;
    const step = async (name: string, action: () => Promise<unknown>) => {
      await action();
      const events = (await api.board(RUN)).system_events;
      expect(events.length, name).toBeGreaterThan(count);
      for (const e of events.slice(count)) expect(e, name).toMatchObject({ run_id: RUN, disaster_id: DISASTER, id: expect.any(String) });
      count = events.length;
    };

    await step("report", () => report(api, "We need water"));
    await step("claim", () => api.claim(RUN, "current-food-1", { organization_id: "demo-food", promised_at: PROMISED }));
    await step("deliver", () => api.deliver(RUN, "current-food-1", { organization_id: "demo-food", notes: "" }));
    let callId = "";
    await step("queueFollowUp", async () => (callId = (await api.queueFollowUp(RUN, "current-food-1")).id));
    let verificationId = "";
    await step("startCall", async () => {
      await api.startCall(RUN, callId, "yes");
      verificationId = (await api.board(RUN)).verifications.find((v) => v.request_id === "current-food-1")!.id;
    });
    let lessonId = "";
    await step("draftLesson", async () => {
      lessonId = (
        await api.draftLesson(RUN, { source_outcome_ids: [verificationId], summary: "Confirmed handoff works.", conditions: ["food"], recommendation: "Confirm the handoff." })
      ).id;
    });
    await step("approveLesson", () => api.approveLesson(RUN, lessonId));
    await step("compare", () => api.compare(RUN));
    await step("verify", () => api.verify(RUN, "current-transport-1", { received: null, notes: "" }));

    const ids = (await api.board(RUN)).system_events.map((e) => e.id);
    expect(new Set(ids).size).toBe(ids.length);
  });

  it("emits the promise, delivery and verification events in order, keeping delivery separate from verification", async () => {
    const api = new MockApi();
    await toAwaiting(api);
    await api.verify(RUN, "current-food-1", { received: true, notes: "" });
    const actions = (await api.board(RUN)).system_events.filter((e) => e.subject_id === "current-food-1" && e.module === "recovery").map((e) => e.action);
    expect(actions).toEqual(["request_claimed", "delivery_reported", "request_verified"]);
  });

  it("reset() restores the seed on every run", async () => {
    const api = new MockApi();
    const seeded = { current: withoutAsOf(await api.board(RUN)), history: withoutAsOf(await api.board(HISTORY)) };
    await report(api, "We need food and blankets");
    await report(api, "My father fell down and can't get up");
    await toAwaiting(api);
    await api.queueFollowUp(RUN, "current-food-1");
    await api.compare(RUN);
    await api.draftLesson(HISTORY, { source_outcome_ids: ["history-received-1"], summary: "A lesson.", conditions: ["food"], recommendation: "Do it." });
    expect(withoutAsOf(await api.board(RUN))).not.toEqual(seeded.current);

    expect(await api.reset()).toBe(true);
    expect(withoutAsOf(await api.board(RUN))).toEqual(seeded.current);
    expect(withoutAsOf(await api.board(HISTORY))).toEqual(seeded.history);
  });

  it("never lets one instance's changes reach another, or the shared seed", async () => {
    const a = new MockApi();
    await toAwaiting(a);
    await a.compare(RUN);
    const b = new MockApi();
    const board = await b.board(RUN);
    expect(find(board, "current-food-1")).toMatchObject({ status: "open", organization_id: null });
    expect(board.evaluations).toEqual([]);
  });
});
