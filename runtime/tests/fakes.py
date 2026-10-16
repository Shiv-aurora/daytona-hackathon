"""Test doubles: the reference store (`runtime.local.LocalStore`), a call stub, a scripted model and a
phrase-list safety check. No database, no network."""

from __future__ import annotations

from runtime.llm import LLMResponse
from runtime.local import LocalStore as InMemoryMemory

__all__ = ["InMemoryMemory", "ScriptedLLM", "StubCalls", "phrase_safety"]


class StubCalls:
    """Call-scheduling stub: records requests insert-once by `_id`."""

    def __init__(self):
        self.requests: dict[str, dict] = {}

    def schedule_call(self, request):
        if request["_id"] in self.requests:
            return False
        self.requests[request["_id"]] = dict(request)
        return True


class ScriptedLLM:
    """Stands in for OpenRouter: answers from a script and records every prompt it was shown."""

    model = "test/scripted"

    def __init__(self, respond, prompt_tokens=120, completion_tokens=30):
        self.respond, self.prompts = respond, []
        self.prompt_tokens, self.completion_tokens = prompt_tokens, completion_tokens

    def complete(self, messages, max_tokens):
        self.prompts.append(messages[-1]["content"])
        return LLMResponse(self.respond(messages[-1]["content"]), self.model, self.prompt_tokens,
                           self.completion_tokens)


def phrase_safety(text):
    """A tiny stand-in for W3's phrase-list `safety_check`, in the shared SafetyVerdict shape."""
    for phrase in ("fell", "can't breathe", "chest pain", "gas leak"):
        if phrase in text.lower():
            return {"emergency": True, "reason": phrase}
    return {"emergency": False}
