"""Provider abstraction.

Per docs/architecture.md section 7: the application depends only on this
interface. Concrete providers (Gemini, OpenAI, Ollama, Claude) implement the
same contract so they're interchangeable execution backends with no domain
knowledge of their own.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TypeVar

from pydantic import BaseModel

TSchema = TypeVar("TSchema", bound=BaseModel)


class ILLMProvider(ABC):
    @abstractmethod
    def generate_structured(
        self,
        prompt: str,
        response_schema: type[TSchema],
        thinking_budget: int | None = None,
    ) -> TSchema:
        """Send a prompt to the LLM and return output validated against response_schema.

        Implementations are responsible for:
        - calling the underlying API
        - requesting/parsing JSON output matching response_schema
        - raising providers.errors-mapped exceptions on failure

        Implementations must NOT:
        - interpret the meaning of the response
        - apply business logic

        `thinking_budget` (added when logging in providers/gemini_provider.py
        showed every one of the app's six LLM calls spending more tokens on
        hidden "thinking" than on the visible response — up to 6x, on a
        model whose default thinking budget is unbounded/automatic) is an
        optional, best-effort perf knob: `None` (the default) means "use
        whatever this provider/model defaults to," a non-negative int caps
        it in tokens (0 disables thinking outright), matching
        `google.genai.types.ThinkingConfig.thinking_budget`'s own
        convention. A provider with no concept of "thinking" (or that
        doesn't expose a budget knob) is free to ignore this rather than
        error — it's a latency lever the caller may suggest, never a
        contract the call depends on for correctness. See
        app/use_cases.py for which stages set it and why.

        Convention (Phase 19, see providers/gemini_provider.py): log one
        INFO line per successful call with model/elapsed-time/token counts
        — numbers only, never prompt or response text. Not enforced by this
        interface (same as retry-with-backoff isn't), but every provider
        added in Phase 9 onward should follow it so cost/latency data stays
        comparable across providers.
        """
        raise NotImplementedError
