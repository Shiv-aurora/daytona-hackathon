// Presentation mode from NEXT_PUBLIC_MODE: "mock" (default), "replay" or "live". Replay and live
// presentations hide mock scaffolding: the "Mock data" badge and "mock-" run id prefixes.
// (Which adapter serves the data is decided separately, by NEXT_PUBLIC_RELAY_API_URL.)
export const presentMode = () => process.env.NEXT_PUBLIC_MODE?.trim().toLowerCase() || "mock";
export const hideMock = () => ["replay", "live"].includes(presentMode());
export const runLabel = (runId: string) => (hideMock() ? runId.replace(/^mock-/, "") : runId);
