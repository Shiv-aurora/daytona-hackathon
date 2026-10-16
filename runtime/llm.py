"""Model access for the runtime: OpenRouter over plain HTTPS, a response cache, and token accounting.

Nothing here touches the network in CI. Tests inject a scripted client or a fake HTTP opener, and a
cache-only `CachedLLM` (no client) replays stored responses deterministically. The client is built
only when `OPENROUTER_API_KEY` is set; the key is never logged or stored.
"""

from __future__ import annotations

import json
import os
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Protocol

from runtime.ports import LLMCachePort
from runtime.promises import stable_id

OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "anthropic/claude-sonnet-5"


class LLMUnavailable(RuntimeError):
    """No cached answer and no live model: the caller falls back to the deterministic path."""


# What a model call can raise: no model, transport/HTTP errors and timeouts (OSError), a payload
# that is not JSON (ValueError) or not shaped like a completion (KeyError/IndexError).
MODEL_ERRORS = (LLMUnavailable, OSError, ValueError, KeyError, IndexError)


@dataclass(frozen=True)
class LLMResponse:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0  # OpenRouter usage accounting; feeds Score.cost_per_simulated_day
    cached: bool = False


class LLMClient(Protocol):
    model: str

    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse: ...


class OpenRouterClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL, timeout: float = 60.0,
                 opener: Callable = urllib.request.urlopen):
        if not api_key:
            raise ValueError("an OpenRouter API key is required")
        self.model, self._api_key, self._timeout, self._open = model, api_key, timeout, opener

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> OpenRouterClient | None:
        env = os.environ if env is None else env
        api_key = env.get("OPENROUTER_API_KEY")
        return cls(api_key, env.get("OPENROUTER_MODEL") or DEFAULT_MODEL) if api_key else None

    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse:
        body = json.dumps({"model": self.model, "messages": messages, "max_tokens": max_tokens,
                           "temperature": 0, "usage": {"include": True}}).encode()
        request = urllib.request.Request(OPENROUTER_URL, data=body, method="POST", headers={
            "Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json", "X-Title": "Relay"})
        with self._open(request, timeout=self._timeout) as response:
            payload = json.load(response)
        usage = payload.get("usage") or {}
        return LLMResponse(text=payload["choices"][0]["message"]["content"] or "",
                           model=payload.get("model") or self.model,
                           prompt_tokens=int(usage.get("prompt_tokens") or 0),
                           completion_tokens=int(usage.get("completion_tokens") or 0),
                           cost_usd=float(usage.get("cost") or 0.0))


class CachedLLM:
    """Cache-first completions keyed by model and prompt: a replay, or CI, sees identical answers."""

    def __init__(self, cache: LLMCachePort, client: LLMClient | None = None, model: str | None = None):
        if client is None and model is None:
            raise ValueError("a cache-only CachedLLM needs the model its cache was filled with")
        self.cache, self.client = cache, client
        self.model = model or client.model

    def complete(self, messages: list[dict], max_tokens: int) -> LLMResponse:
        key = stable_id("llm", self.model, max_tokens, json.dumps(messages, sort_keys=True))
        if (hit := self.cache.llm_cache_get(key)) is not None:
            return LLMResponse(**{**hit, "cached": True})
        if self.client is None:
            raise LLMUnavailable(f"no cached response for {key} and no live model")
        response = self.client.complete(messages, max_tokens)
        self.cache.llm_cache_put(key, asdict(response))
        return response


@dataclass
class TokenLedger:
    """Model usage within one tick. Cached answers cost nothing and are counted separately."""

    calls: int = 0
    cached_calls: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0

    def add(self, response: LLMResponse) -> None:
        if response.cached:
            self.cached_calls += 1
            return
        self.calls += 1
        self.prompt_tokens += response.prompt_tokens
        self.completion_tokens += response.completion_tokens
        self.cost_usd += response.cost_usd

    def as_metrics(self) -> dict[str, float]:
        return {f"llm_{name}": float(value) for name, value in asdict(self).items()}
