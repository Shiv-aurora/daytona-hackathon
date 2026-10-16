import { Console } from "@/components/console/Console";
import { pickSource } from "@/lib/source";

// Live when this deployment has a Relay run API; Replay when it reads completed runs from recorded snapshots;
// otherwise the built-in mock run, which needs no backend. See lib/source.ts.
export default async function ConsolePage({ searchParams }: PageProps<"/console">) {
  const { run, mode } = await searchParams;
  const { kind, relay } = pickSource(mode);
  return <Console key={kind} relay={relay} replay={kind === "replay"} initialRun={typeof run === "string" && kind !== "mock" ? run : undefined} />;
}
