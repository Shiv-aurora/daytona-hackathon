// @vitest-environment jsdom
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";
import { MockAdapter } from "@/lib/adapter";
import { LiveAdapter } from "@/lib/live/client";
import { FakeRelay, relabel } from "@/lib/live/fake-relay";
import { mockSnapshot } from "@/lib/mock";
import { CallView } from "./CallView";

afterEach(cleanup);

describe("Call View on the mock run", () => {
  it("shows the full red emergency banner, the fixed disclosure, and memory used", async () => {
    render(<CallView callId="call-s1_h_013-1" adapter={new MockAdapter()} />);
    expect((await screen.findByRole("alert")).textContent).toContain("EMERGENCY PHRASE DETECTED — LLM bypassed — escalating to human");
    expect(screen.getByText(/Relay · fixed disclosure/)).toBeTruthy();
    expect(screen.getByText(/This is an automated call from Relay/)).toBeTruthy();
    expect(screen.getByRole("heading", { name: /Memory used \(1\)/ })).toBeTruthy();
    expect(screen.getByText(/Emergency handed to a person/)).toBeTruthy();
  });

  it("keeps human escalation reachable and records it", async () => {
    render(<CallView callId="call-s1_h_004-1" adapter={new MockAdapter()} />);
    await screen.findByText(/Emergency detector listening/);
    fireEvent.click(screen.getByRole("button", { name: /Escalate to a human now/ }));
    await waitFor(() => expect(screen.getByRole("status").textContent).toContain("urgent proposal"));
    expect(screen.getByText(/Human follow-up requested · pending/)).toBeTruthy();
  });

  it("shows an unanswered call without a transcript", async () => {
    render(<CallView callId="call-s1_h_001-1" adapter={new MockAdapter()} />);
    expect(await screen.findByText(/No one answered/)).toBeTruthy();
    expect(screen.getByText(/Disclosure not played/)).toBeTruthy();
  });

  it("shows only the selected run's transcript, language, and motivating promise", async () => {
    const relay = new FakeRelay({ "run-a": relabel(mockSnapshot, "run-a", "RUN-A"), "run-b": relabel(mockSnapshot, "run-b", "RUN-B") });
    render(<CallView callId="call-s1_h_004-1" runId="run-b" adapter={new LiveAdapter("http://relay.test", relay.fetch)} />);
    await screen.findByText(/Emergency detector listening/);
    const body = document.body.textContent ?? "";
    expect(body).toContain("RUN-B"); // relabel marks every event text (incl. the transcript) with its run
    expect(body).not.toContain("RUN-A");
    expect(body).toContain("prefers Korean");
    expect(body).toContain("Answered");
    expect(relay.requests.every((r) => r.url.includes("/runs/run-b/"))).toBe(true);
  });
});
