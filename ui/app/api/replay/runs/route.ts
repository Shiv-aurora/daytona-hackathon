import { listRuns } from "@/lib/replay/snapshot";
import { replayConfigured, replayDb } from "@/lib/replay/server";

export const dynamic = "force-dynamic";

/** GET /api/replay/runs -> { runs } (Relay run API v0, read-only, from recorded snapshots). */
export async function GET() {
  if (!replayConfigured()) return Response.json({ error: "Replay is not configured on this deployment" }, { status: 503 });
  try {
    return Response.json({ runs: await listRuns(await replayDb()) });
  } catch (e) {
    console.error("replay runs", e);
    return Response.json({ error: "Could not reach the replay database" }, { status: 502 });
  }
}
