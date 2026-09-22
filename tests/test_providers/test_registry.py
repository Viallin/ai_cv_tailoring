from dataclasses import dataclass

import pytest

from app.errors import ConfigurationError
from providers.gemini_provider import GeminiProvider
from providers.registry import DEFAULT_REGISTRY, ProviderRegistry


class _StubProvider:
    pass


@dataclass
class _FakeConfig:
    gemini_api_key: str = "fake-key"
    llm_model: str = "gemini-2.0-flash"
    llm_max_retries: int = 3
    llm_retry_base_delay_seconds: float = 1.0


def test_build_calls_the_registered_factory_with_config():
    registry = ProviderRegistry({"stub": lambda config: _StubProvider()})

    provider = registry.build("stub", config=_FakeConfig())

    assert isinstance(provider, _StubProvider)


def test_build_raises_configuration_error_for_unknown_provider():
    registry = ProviderRegistry({"stub": lambda config: _StubProvider()})

    with pytest.raises(ConfigurationError, match="stub"):
        registry.build("nonexistent", config=_FakeConfig())


def test_default_registry_builds_a_gemini_provider():
    provider = DEFAULT_REGISTRY.build("gemini", config=_FakeConfig())

    assert isinstance(provider, GeminiProvider)
