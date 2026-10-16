import { CallView } from "@/components/call/CallView";
import { pickSource } from "@/lib/source";

export default async function CallPage({ params, searchParams }: PageProps<"/call/[callId]">) {
  const { callId } = await params;
  const { run, mode } = await searchParams;
  const { kind, relay } = pickSource(mode);
  return <CallView callId={callId} runId={typeof run === "string" ? run : undefined} relay={relay} replay={kind === "replay"} />;
}
