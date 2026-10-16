// Fixed on-screen data label (PM decision on PR #6: this exact wording everywhere in the UI).
export const DATA_LABEL =
  "Background 311 requests are real NYC Open Data from Ida (2021). Households, calls, and outcomes are simulated.";

export const QUEUE_LABEL: Record<string, string> = {
  welfare_check: "Welfare check",
  priority_power: "Priority power",
  supplies: "Supplies",
  caseworker_followup: "Caseworker follow-up",
};

export const SOURCE_LABEL: Record<string, string> = {
  "311": "311",
  visit_note: "Visit note",
  utility: "Utility",
  crew: "Crew",
  call: "Call",
  call_result: "Call result",
};

export const DISMISS_REASONS = [
  "Already handled by another team",
  "Duplicate of another proposal",
  "Wrong household match",
  "Household declined help",
  "Cited facts are out of date",
] as const;
