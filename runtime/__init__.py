"""W1 runtime: the simulated-time orchestration loop.

Persistence (W2), calls (W3) and scoring (W4) live elsewhere and are reached only through the
ports in `runtime.ports`. The model path (`runtime.llm`) is optional and cache-first.
"""

from runtime.clock import SimClock
from runtime.llm import CachedLLM, OpenRouterClient
from runtime.loop import Runtime
from runtime.state import RuntimeState, assert_small_state, new_run_state

__all__ = ["CachedLLM", "OpenRouterClient", "Runtime", "RuntimeState", "SimClock", "assert_small_state",
           "new_run_state"]
