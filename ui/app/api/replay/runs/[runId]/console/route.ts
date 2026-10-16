import { readConsole } from "@/lib/replay/snapshot";
import { replayConfigured, replayDb } from "@/lib/replay/server";

export const dynamic = "force-dynamic";

/** GET /api/replay/runs/{run_id}/console -> ConsoleSnapshot for that run only (read-only, from recorded snapshots). */
export async function GET(_req: Request, ctx: RouteContext<"/api/replay/runs/[runId]/console">) {
  const { runId } = await ctx.params;
  if (!replayConfigured()) return Response.json({ error: "Replay is not configured on this deployment" }, { status: 503 });
  try {
    const snap = await readConsole(await replayDb(), runId);
    if (!snap) return Response.json({ error: `No run ${runId}` }, { status: 404 });
    return Response.json(snap, { headers: { "Cache-Control": "public, max-age=15" } });
  } catch (e) {
    console.error("replay console", runId, e);
    return Response.json({ error: "Could not read this run from the replay database" }, { status: 502 });
  }
}
