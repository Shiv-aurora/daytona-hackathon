"use client";

import { Mic } from "lucide-react";
import { useEffect, useRef } from "react";
import { Card, SectionTitle } from "./ui";

const AGENT_ID = "agent_9901m52xtp8aenjb85rmkdxcyacr";
const SCRIPT_SRC = "https://unpkg.com/@elevenlabs/convai-widget-embed";

export type VoiceVars = {
  household_label: string;
  request_category: string;
  request_summary: string;
  org_name: string;
  promised_when: string;
};

/** ElevenLabs widget for the "Relay AI Helper" agent. The element is created imperatively: it is a third-party custom element. */
export function VoiceHelper({ vars }: { vars: VoiceVars }) {
  const host = useRef<HTMLDivElement>(null);
  const encoded = JSON.stringify(vars);

  useEffect(() => {
    if (!document.querySelector(`script[src="${SCRIPT_SRC}"]`)) {
      const s = document.createElement("script");
      s.src = SCRIPT_SRC;
      s.async = true;
      document.head.appendChild(s);
    }
    const el = document.createElement("elevenlabs-convai");
    el.setAttribute("agent-id", AGENT_ID);
    el.setAttribute("dynamic-variables", encoded);
    const node = host.current;
    node?.appendChild(el);
    return () => {
      el.remove();
    };
  }, [encoded]);

  return (
    <Card className="space-y-2 rounded-lg p-4">
      <SectionTitle icon={Mic}>Talk to Relay AI Helper</SectionTitle>
      <p className="text-sm text-muted-foreground">
        Try it: say &ldquo;it never came&rdquo;, or describe an emergency. Automated assistant, not a person.
      </p>
      <div ref={host} className="h-0" />
    </Card>
  );
}
