"""Provider Registry — Phase 9.

Per docs/architecture.md 3.4.3: maintains the set of available LLM
providers and builds the one(s) `app/services.py:build_services()` asks
for, so that call site doesn't need to know how to construct each concrete
provider. Adding a new provider (OpenAI/Ollama/Claude) later means adding
one factory to DEFAULT_REGISTRY here — nothing above this layer changes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Callable

from app.errors import ConfigurationError
from providers.base import ILLMProvider
from providers.gemini_provider import GeminiProvider

if TYPE_CHECKING:
    from app.config import Config

ProviderFactory = Callable[["Config"], ILLMProvider]


class ProviderRegistry:
    def __init__(self, factories: dict[str, ProviderFactory]):
        self._factories = dict(factories)

    def build(self, name: str, config: "Config") -> ILLMProvider:
        factory = self._factories.get(name)
        if factory is None:
            registered = ", ".join(sorted(self._factories)) or "(none)"
            raise ConfigurationError(
                f"Unknown LLM provider: {name!r}. Registered providers: {registered}."
            )
        return factory(config)


def _build_gemini(config: "Config") -> ILLMProvider:
    return GeminiProvider(
        api_key=config.gemini_api_key,
        model=config.llm_model,
        max_retries=config.llm_max_retries,
        retry_base_delay_seconds=config.llm_retry_base_delay_seconds,
    )


DEFAULT_REGISTRY = ProviderRegistry({"gemini": _build_gemini})
