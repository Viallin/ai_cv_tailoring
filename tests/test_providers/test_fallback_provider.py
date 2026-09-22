import pytest
from pydantic import BaseModel

from app.errors import ConfigurationError, ProviderError, ValidationError
from providers.fallback_provider import FallbackProvider


class _Schema(BaseModel):
    value: str


class _StubProvider:
    def __init__(self, result=None, error=None):
        self._result = result
        self._error = error
        self.calls = 0
        self.last_thinking_budget = None

    def generate_structured(self, prompt, response_schema, thinking_budget=None):
        self.calls += 1
        self.last_thinking_budget = thinking_budget
        if self._error is not None:
            raise self._error
        return self._result


def test_raises_configuration_error_when_given_no_providers():
    with pytest.raises(ConfigurationError):
        FallbackProvider([])


def test_uses_first_provider_when_it_succeeds():
    first = _StubProvider(result=_Schema(value="ok"))
    second = _StubProvider(result=_Schema(value="unused"))
    provider = FallbackProvider([first, second])

    result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    assert second.calls == 0


def test_falls_back_to_next_provider_on_provider_error():
    first = _StubProvider(error=ProviderError("first is down"))
    second = _StubProvider(result=_Schema(value="ok"))
    provider = FallbackProvider([first, second])

    result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    assert first.calls == 1
    assert second.calls == 1


def test_raises_last_provider_error_when_all_providers_fail():
    first = _StubProvider(error=ProviderError("first is down"))
    second = _StubProvider(error=ProviderError("second is down too"))
    provider = FallbackProvider([first, second])

    with pytest.raises(ProviderError, match="second is down too"):
        provider.generate_structured("prompt", _Schema)


def test_does_not_fall_back_on_non_provider_errors():
    first = _StubProvider(error=ValidationError("malformed output"))
    second = _StubProvider(result=_Schema(value="unused"))
    provider = FallbackProvider([first, second])

    with pytest.raises(ValidationError):
        provider.generate_structured("prompt", _Schema)

    assert second.calls == 0


def test_forwards_thinking_budget_to_the_underlying_provider():
    stub = _StubProvider(result=_Schema(value="ok"))
    provider = FallbackProvider([stub])

    provider.generate_structured("prompt", _Schema, thinking_budget=0)

    assert stub.last_thinking_budget == 0
