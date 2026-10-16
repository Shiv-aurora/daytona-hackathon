"""What Relay says after each (already safety-checked) resident turn.

`ScriptedResponder` is deterministic: it asks the memory-derived questions in order, then closes.
CI, simulated calls and the demo fallback use it. `ModelResponder` phrases the same questions with
W1's LLM client, sees only the whitelisted context, and falls back to the script on any model error.
Neither can produce the disclosure or the emergency line: those are spoken by `CallSession`.
"""

from __future__ import annotations

import json

from calls.agent import Reply
from runtime.llm import MODEL_ERRORS, LLMClient

# Fixed lines per language (reviewed translations, never model output). English is the fallback.
OPENINGS = {"en": "Thank you for taking our call.", "zh": "谢谢您接听我们的电话。"}
CLOSINGS = {"en": ("Thank you. I've noted everything for the recovery team, and a person will follow up if "
                   "anything needs attention. Goodbye."),
            "zh": "谢谢您。我已经把情况都记录下来转告恢复团队，如有需要，工作人员会跟进。再见。"}
NO_QUESTIONS_LINES = {"en": "We're checking in after the storm. Is there anything you need from the recovery team?",
                      "zh": "我们在风暴过后回访您。您需要恢复团队提供什么帮助吗？"}
OPENING, CLOSING, NO_QUESTIONS = OPENINGS["en"], CLOSINGS["en"], NO_QUESTIONS_LINES["en"]


def line_for(lines: dict[str, str], language: str | None) -> str:
    return lines.get(language or "en", lines["en"])
END_MARKER = "<END_CALL>"
MAX_TOKENS = 120

SYSTEM_PROMPT = f"""You are Relay, an automated follow-up caller for a storm recovery team, on a phone call
with a resident. The disclosure has already been spoken: never repeat it, and do not introduce yourself again.
Talk like a warm, patient person: one or two short sentences per reply, in plain language.
Always reply in the resident's language from CONTEXT.language (en = English, zh = Mandarin Chinese in
simplified characters), even if the questions or facts in CONTEXT are written in another language.
Ask the first listed question right away, then the others in order, and really listen to the answers.
Acknowledge what the resident tells you. If they ask something, answer only from the facts in CONTEXT
(for example the outage or recovery status); if CONTEXT does not say, tell them you don't know yet and
that you will pass the question to the recovery team. If they need something, say you will pass it on.
Never give medical, legal or financial advice. Never rank or compare households.
Only when every question has been answered AND you have asked whether they need anything else AND they
say no, thank them in one sentence and end with {END_MARKER}."""


def _asked(questions: list[str], transcript: list[dict]) -> int:
    relay_lines = [turn["text"] for turn in transcript if turn["speaker"] == "relay"]
    return sum(1 for question in questions if any(question in line for line in relay_lines))


class ScriptedResponder:
    def reply(self, context: dict, transcript: list[dict]) -> Reply:
        language = context.get("language")
        questions = list(context.get("questions") or [])
        asked = _asked(questions, transcript)
        if asked < len(questions):
            gap = "" if language == "zh" else " "  # Chinese sentences are not separated by spaces
            prefix = f"{line_for(OPENINGS, language)}{gap}" if asked == 0 else ""
            return Reply(f"{prefix}{questions[asked]}")
        no_questions = line_for(NO_QUESTIONS_LINES, language)
        if not questions and not any(turn["text"] == no_questions for turn in transcript):
            return Reply(no_questions)
        return Reply(line_for(CLOSINGS, language), end=True)


class ModelResponder:
    def __init__(self, llm: LLMClient, fallback: ScriptedResponder | None = None):
        self.llm, self.fallback = llm, fallback or ScriptedResponder()

    def reply(self, context: dict, transcript: list[dict]) -> Reply:
        messages = [{"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "system", "content": "CONTEXT: " + json.dumps(context, sort_keys=True)}]
        for turn in transcript[1:]:  # transcript[0] is the code-owned disclosure
            role = "assistant" if turn["speaker"] == "relay" else "user"
            messages.append({"role": role, "content": turn["text"]})
        try:
            text = self.llm.complete(messages, MAX_TOKENS).text
        except MODEL_ERRORS:
            return self.fallback.reply(context, transcript)
        # Never hang up on the resident's first reply, whatever the model says.
        resident_turns = sum(1 for turn in transcript if turn["speaker"] == "resident")
        end = END_MARKER in text and resident_turns >= 2
        text = text.replace(END_MARKER, "").strip()
        if not text:
            return self.fallback.reply(context, transcript)
        return Reply(text, end=end)
