from typing import Literal

import pytest
from pydantic import BaseModel

from app.errors import ParsingError, ProviderError, ValidationError
from providers.gemini_provider import (
    GeminiProvider,
    _find_degenerate_placeholder_string,
    _is_retryable_error,
)


class _Schema(BaseModel):
    value: str


class _MatchLikeItem(BaseModel):
    # Mirrors domain.models.RequirementMatch's shape (a freeform `str`
    # field next to a `Literal` field) — the exact pattern that produced
    # the real, live degenerate-output bug this module now guards against.
    requirement_text: str
    strength: Literal["high", "medium", "low"]


class _MatchLikeResponse(BaseModel):
    matches: list[_MatchLikeItem]


class _FakeResponse:
    def __init__(self, text: str, usage_metadata=None):
        self.text = text
        if usage_metadata is not None:
            self.usage_metadata = usage_metadata


class _FakeUsageMetadata:
    def __init__(self, prompt_token_count, candidates_token_count, total_token_count):
        self.prompt_token_count = prompt_token_count
        self.candidates_token_count = candidates_token_count
        self.total_token_count = total_token_count


def _make_provider(mocker, max_retries=3, retry_base_delay_seconds=0.0):
    provider = GeminiProvider(
        api_key="fake-key",
        model="gemini-2.0-flash",
        max_retries=max_retries,
        retry_base_delay_seconds=retry_base_delay_seconds,
    )
    mocker.patch("time.sleep")  # don't actually wait during tests
    return provider


def test_raises_provider_error_when_api_key_missing():
    with pytest.raises(ProviderError):
        GeminiProvider(api_key="", model="gemini-2.0-flash")


def test_is_retryable_error_matches_503_message():
    assert _is_retryable_error(Exception("503 UNAVAILABLE. High demand.")) is True


def test_is_retryable_error_matches_numeric_code_attribute():
    exc = Exception("boom")
    exc.code = 429
    assert _is_retryable_error(exc) is True


def test_is_retryable_error_rejects_client_errors():
    assert _is_retryable_error(Exception("400 INVALID_ARGUMENT")) is False


def test_succeeds_without_retry_when_first_call_succeeds(mocker):
    provider = _make_provider(mocker)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse('{"value": "ok"}')
    mocker.patch.object(provider, "_get_client", return_value=client)

    result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    assert client.models.generate_content.call_count == 1


def test_logs_token_counts_and_elapsed_time_on_success(mocker, caplog):
    provider = _make_provider(mocker)
    client = mocker.Mock()
    usage = _FakeUsageMetadata(
        prompt_token_count=123, candidates_token_count=45, total_token_count=168
    )
    prompt_text = "a very distinctive raw prompt nobody else would type"
    response_text = '{"value": "a very distinctive response value"}'
    client.models.generate_content.return_value = _FakeResponse(response_text, usage_metadata=usage)
    mocker.patch.object(provider, "_get_client", return_value=client)

    with caplog.at_level("INFO"):
        provider.generate_structured(prompt_text, _Schema)

    [record] = [r for r in caplog.records if "Gemini call succeeded" in r.message]
    assert "model=gemini-2.0-flash" in record.message
    assert "prompt_tokens=123" in record.message
    assert "response_tokens=45" in record.message
    assert "total_tokens=168" in record.message
    assert "attempt=1/4" in record.message
    # Numbers only — the raw prompt/response text is never logged.
    assert prompt_text not in record.message
    assert response_text not in record.message
    assert "distinctive" not in record.message


def test_logs_gracefully_when_usage_metadata_missing(mocker, caplog):
    provider = _make_provider(mocker)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse('{"value": "ok"}')
    mocker.patch.object(provider, "_get_client", return_value=client)

    with caplog.at_level("INFO"):
        result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    [record] = [r for r in caplog.records if "Gemini call succeeded" in r.message]
    assert "prompt_tokens=None" in record.message


def test_retries_on_transient_error_then_succeeds(mocker):
    provider = _make_provider(mocker, max_retries=3)
    client = mocker.Mock()
    transient = Exception("503 UNAVAILABLE. High demand.")
    client.models.generate_content.side_effect = [
        transient,
        transient,
        _FakeResponse('{"value": "ok"}'),
    ]
    mocker.patch.object(provider, "_get_client", return_value=client)

    result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    assert client.models.generate_content.call_count == 3


def test_gives_up_after_max_retries_exhausted(mocker):
    provider = _make_provider(mocker, max_retries=2)
    client = mocker.Mock()
    client.models.generate_content.side_effect = Exception("503 UNAVAILABLE.")
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ProviderError):
        provider.generate_structured("prompt", _Schema)

    # 1 initial attempt + 2 retries = 3 calls total
    assert client.models.generate_content.call_count == 3


def test_does_not_retry_non_transient_error(mocker):
    provider = _make_provider(mocker, max_retries=3)
    client = mocker.Mock()
    client.models.generate_content.side_effect = Exception("400 INVALID_ARGUMENT")
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ProviderError):
        provider.generate_structured("prompt", _Schema)

    assert client.models.generate_content.call_count == 1


def test_retries_and_recovers_from_a_malformed_json_response(mocker):
    provider = _make_provider(mocker, max_retries=3)
    client = mocker.Mock()
    client.models.generate_content.side_effect = [
        _FakeResponse('{"value": "broken"'),  # missing closing brace
        _FakeResponse('{"value": "ok"}'),
    ]
    mocker.patch.object(provider, "_get_client", return_value=client)

    result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    assert client.models.generate_content.call_count == 2


def test_gives_up_after_max_retries_on_persistently_malformed_json(mocker):
    provider = _make_provider(mocker, max_retries=2)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse('{"value": "broken"')
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ParsingError):
        provider.generate_structured("prompt", _Schema)

    # 1 initial attempt + 2 retries = 3 calls total
    assert client.models.generate_content.call_count == 3


def test_parsing_error_message_includes_a_snippet_of_the_malformed_text(mocker):
    provider = _make_provider(mocker, max_retries=0)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse(
        '{"value": "unterminated'
    )
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ParsingError) as exc_info:
        provider.generate_structured("prompt", _Schema)

    assert "unterminated" in str(exc_info.value)


def test_retries_and_recovers_from_a_schema_mismatch(mocker):
    provider = _make_provider(mocker, max_retries=3)
    client = mocker.Mock()
    client.models.generate_content.side_effect = [
        _FakeResponse('{"wrong_field": "oops"}'),
        _FakeResponse('{"value": "ok"}'),
    ]
    mocker.patch.object(provider, "_get_client", return_value=client)

    result = provider.generate_structured("prompt", _Schema)

    assert result == _Schema(value="ok")
    assert client.models.generate_content.call_count == 2


# ----- _find_degenerate_placeholder_string -------------------------------


def test_finds_no_degenerate_string_in_clean_content():
    clean = _MatchLikeResponse(
        matches=[_MatchLikeItem(requirement_text="5+ years Python", strength="high")]
    )

    assert _find_degenerate_placeholder_string(clean) is None


def test_finds_degenerate_placeholder_in_a_nested_list():
    # The exact live failure: every freeform string field across a list of
    # same-shaped objects came back as the literal two-character string
    # '", "', while the sibling Literal field was genuine.
    degenerate = _MatchLikeResponse(
        matches=[
            _MatchLikeItem(requirement_text='", "', strength="high"),
            _MatchLikeItem(requirement_text='", "', strength="medium"),
        ]
    )

    found = _find_degenerate_placeholder_string(degenerate)

    assert found is not None
    assert '", "' in found


def test_does_not_flag_a_short_but_real_word():
    # A short, legitimate, even-repeated value (a project name, a
    # three-letter keyword) must never trip this check — only a value with
    # zero letters/digits at all should.
    real = _MatchLikeResponse(
        matches=[
            _MatchLikeItem(requirement_text="MVP", strength="high"),
            _MatchLikeItem(requirement_text="MVP", strength="medium"),
        ]
    )

    assert _find_degenerate_placeholder_string(real) is None


def test_does_not_flag_literal_enum_values_repeating():
    # `strength` legitimately repeats the same handful of values across a
    # whole list — that's normal, not a symptom, and isn't even reachable
    # by the string-content check since it's a `Literal`, not freeform.
    many = _MatchLikeResponse(
        matches=[_MatchLikeItem(requirement_text=f"Requirement {i}", strength="high") for i in range(5)]
    )

    assert _find_degenerate_placeholder_string(many) is None


def test_retries_and_recovers_from_degenerate_placeholder_content(mocker):
    provider = _make_provider(mocker, max_retries=3)
    client = mocker.Mock()
    client.models.generate_content.side_effect = [
        _FakeResponse('{"matches": [{"requirement_text": "\\", \\"", "strength": "high"}]}'),
        _FakeResponse('{"matches": [{"requirement_text": "Python", "strength": "high"}]}'),
    ]
    mocker.patch.object(provider, "_get_client", return_value=client)

    result = provider.generate_structured("prompt", _MatchLikeResponse)

    assert result == _MatchLikeResponse(
        matches=[_MatchLikeItem(requirement_text="Python", strength="high")]
    )
    assert client.models.generate_content.call_count == 2


def test_gives_up_after_max_retries_on_persistently_degenerate_content(mocker):
    provider = _make_provider(mocker, max_retries=1)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse(
        '{"matches": [{"requirement_text": "\\", \\"", "strength": "high"}]}'
    )
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ValidationError, match="degenerate"):
        provider.generate_structured("prompt", _MatchLikeResponse)

    # 1 initial attempt + 1 retry = 2 calls total
    assert client.models.generate_content.call_count == 2


def test_omits_thinking_config_by_default(mocker):
    # No thinking_budget passed -> config shouldn't carry a thinking_config
    # key at all, so the model's own default (AUTOMATIC/unbounded for
    # gemini-2.5-flash) applies unchanged, same as before thinking_budget
    # existed as a parameter.
    provider = _make_provider(mocker)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse('{"value": "ok"}')
    mocker.patch.object(provider, "_get_client", return_value=client)

    provider.generate_structured("prompt", _Schema)

    sent_config = client.models.generate_content.call_args.kwargs["config"]
    assert "thinking_config" not in sent_config


def test_passes_thinking_budget_through_to_the_api_call(mocker):
    provider = _make_provider(mocker)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse('{"value": "ok"}')
    mocker.patch.object(provider, "_get_client", return_value=client)

    provider.generate_structured("prompt", _Schema, thinking_budget=0)

    sent_config = client.models.generate_content.call_args.kwargs["config"]
    assert sent_config["thinking_config"] == {"thinking_budget": 0}


def test_falls_back_to_no_thinking_config_on_gemini_3x_rejection(mocker):
    # Gemini 3.x models reject thinking_config.thinking_budget outright
    # (they use thinking_level instead) with a bare 400 INVALID_ARGUMENT.
    # The provider should retry the same call once without thinking_config
    # rather than surfacing that as a failure.
    provider = _make_provider(mocker)
    client = mocker.Mock()
    rejection = Exception("400 INVALID_ARGUMENT. {'error': {'code': 400, 'status': 'INVALID_ARGUMENT'}}")
    rejection.code = 400
    client.models.generate_content.side_effect = [rejection, _FakeResponse('{"value": "ok"}')]
    mocker.patch.object(provider, "_get_client", return_value=client)

    result = provider.generate_structured("prompt", _Schema, thinking_budget=4096)

    assert result == _Schema(value="ok")
    assert client.models.generate_content.call_count == 2
    second_call_config = client.models.generate_content.call_args_list[1].kwargs["config"]
    assert "thinking_config" not in second_call_config


def test_thinking_config_fallback_still_raises_if_second_attempt_also_fails(mocker):
    provider = _make_provider(mocker)
    client = mocker.Mock()
    rejection = Exception("400 INVALID_ARGUMENT")
    rejection.code = 400
    other_failure = Exception("400 INVALID_ARGUMENT - bad prompt")
    other_failure.code = 400
    client.models.generate_content.side_effect = [rejection, other_failure]
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ProviderError):
        provider.generate_structured("prompt", _Schema, thinking_budget=4096)

    assert client.models.generate_content.call_count == 2


def test_400_without_thinking_budget_raises_immediately_without_fallback(mocker):
    # No thinking_config in the request at all -> nothing to drop, so a
    # 400 here is a real error and shouldn't trigger a second attempt.
    provider = _make_provider(mocker)
    client = mocker.Mock()
    failure = Exception("400 INVALID_ARGUMENT")
    failure.code = 400
    client.models.generate_content.side_effect = [failure]
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ProviderError):
        provider.generate_structured("prompt", _Schema)

    assert client.models.generate_content.call_count == 1


def test_gives_up_after_max_retries_on_persistent_schema_mismatch(mocker):
    provider = _make_provider(mocker, max_retries=1)
    client = mocker.Mock()
    client.models.generate_content.return_value = _FakeResponse('{"wrong_field": "oops"}')
    mocker.patch.object(provider, "_get_client", return_value=client)

    with pytest.raises(ValidationError):
        provider.generate_structured("prompt", _Schema)

    # 1 initial attempt + 1 retry = 2 calls total
    assert client.models.generate_content.call_count == 2
