// Scripted sample transcripts (data only, fictional and synthetic). Not wired into any component yet.
// Follow-up calls open with the fixed, code-owned disclosure; intake transcripts never contain contact details.

export interface TranscriptLine {
  speaker: "caller" | "agent";
  text: string;
}

export interface SampleTranscript {
  id: string;
  kind: "intake" | "follow_up";
  title: string;
  /** Follow-up calls only: the call outcome the script ends in. */
  outcome?: "verified_received" | "not_received" | "no_answer" | "unverified";
  /** Intake only: true when the script ends in the immediate human escalation. */
  emergency?: boolean;
  lines: TranscriptLine[];
}

const DISCLOSURE =
  "This is an automated call from Relay for the recovery team. To confirm this call is real, call us back at [demo callback number].";

export const INTAKE_SAMPLES: SampleTranscript[] = [
  {
    id: "intake-food-supplies",
    kind: "intake",
    title: "Food and blankets after a power outage",
    lines: [
      { speaker: "agent", text: "Relay recovery line. Tell me what you need and I will pass it to the recovery team." },
      { speaker: "caller", text: "We have no power and need food and blankets for three people." },
      { speaker: "agent", text: "I have two requests: food and supplies. Is there anything blocking a delivery to your area?" },
      { speaker: "caller", text: "No, the street is clear." },
      { speaker: "agent", text: "Both requests are on the board. An organization will claim them and I will ask you to confirm when things arrive." },
    ],
  },
  {
    id: "intake-access-blocked",
    kind: "intake",
    title: "Food request with a blocked road",
    lines: [
      { speaker: "agent", text: "Relay recovery line. What do you need today?" },
      { speaker: "caller", text: "We need food. The road is blocked by a fallen tree, so nobody can reach us." },
      { speaker: "agent", text: "I noted food and that access is blocked. A coordinator will agree a handoff point with you before anything is sent." },
      { speaker: "caller", text: "The corner by the community hall is open." },
      { speaker: "agent", text: "Thank you. I recorded that handoff point on the request." },
    ],
  },
  {
    id: "intake-emergency",
    kind: "intake",
    emergency: true,
    title: "Emergency phrase during intake",
    lines: [
      { speaker: "agent", text: "Relay recovery line. What do you need today?" },
      { speaker: "caller", text: "My father fell down and can't get up." },
      { speaker: "agent", text: "Please hang up and call 911 now. I'm alerting a person on the recovery team." },
    ],
  },
];

export const FOLLOW_UP_SAMPLES: SampleTranscript[] = [
  {
    id: "follow-up-received",
    kind: "follow_up",
    title: "Follow-up: assistance received",
    outcome: "verified_received",
    lines: [
      { speaker: "agent", text: DISCLOSURE },
      { speaker: "agent", text: "A volunteer reported delivering blankets today. Did everything arrive?" },
      { speaker: "caller", text: "Yes, we received all of it, thank you." },
      { speaker: "agent", text: "Thank you. I recorded that you confirmed receipt." },
    ],
  },
  {
    id: "follow-up-not-received",
    kind: "follow_up",
    title: "Follow-up: assistance not received",
    outcome: "not_received",
    lines: [
      { speaker: "agent", text: DISCLOSURE },
      { speaker: "agent", text: "An organization reported delivering your refill pickup today. Did it arrive?" },
      { speaker: "caller", text: "No, nothing has arrived." },
      { speaker: "agent", text: "I am sorry. I recorded that it did not arrive and a person on the recovery team will follow up." },
    ],
  },
  {
    id: "follow-up-no-answer",
    kind: "follow_up",
    title: "Follow-up: no answer",
    outcome: "no_answer",
    lines: [
      { speaker: "agent", text: DISCLOSURE },
      { speaker: "agent", text: "(No one answered. The request stays unverified and a person is notified.)" },
    ],
  },
  {
    id: "follow-up-unclear",
    kind: "follow_up",
    title: "Follow-up: unclear answer",
    outcome: "unverified",
    lines: [
      { speaker: "agent", text: DISCLOSURE },
      { speaker: "agent", text: "A crew reported finishing a repair today. Did it get done?" },
      { speaker: "caller", text: "Maybe, somebody came by but I could not tell what they did." },
      { speaker: "agent", text: "Thank you. I could not confirm receipt, so I left the request unverified for a person to check." },
    ],
  },
];

export const SAMPLE_TRANSCRIPTS: SampleTranscript[] = [...INTAKE_SAMPLES, ...FOLLOW_UP_SAMPLES];
