"""Fallback across providers — Phase 9.

Distinct from GeminiProvider's own transient-error retry (same provider,
tries again): this tries the *next* provider in an ordered list once the
current one raises ProviderError. Malformed-output failures
(ParsingError/ValidationError) are not fallback triggers — those are
already retried against the same provider inside generate_structured, and
aren't evidence that the provider itself is unavailable. See
providers/gemini_provider.py's module docstring for that distinction.
"""

from __future__ import annotations

from app.errors import ConfigurationError, ProviderError
from app.logging_setup import get_logger
from providers.base import ILLMProvider, TSchema

logger = get_logger(__name__)


class FallbackProvider(ILLMProvider):
    def __init__(self, providers: list[ILLMProvider]):
        if not providers:
            raise ConfigurationError("FallbackProvider requires at least one provider.")
        self._providers = providers

    def generate_structured(
        self,
        prompt: str,
        response_schema: type[TSchema],
        thinking_budget: int | None = None,
    ) -> TSchema:
        last_exc: ProviderError | None = None
        for index, provider in enumerate(self._providers):
            try:
                return provider.generate_structured(prompt, response_schema, thinking_budget)
            except ProviderError as exc:
                last_exc = exc
                attempts_left = len(self._providers) - index - 1
                logger.warning(
                    "Provider %d/%d (%s) failed, %s: %s",
                    index + 1,
                    len(self._providers),
                    type(provider).__name__,
                    f"falling back to the next of {attempts_left} remaining"
                    if attempts_left
                    else "no providers left, giving up",
                    exc,
                )

        raise last_exc
