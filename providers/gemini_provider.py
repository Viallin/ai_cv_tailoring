"""Gemini implementation of ILLMProvider.

Only provider wired up for the Phase 0-6 prototype. Additional providers
(OpenAI, Ollama, Claude) are added in Phase 9 behind the same interface —
nothing above this layer should need to change when they're added.

This module owns two distinct kinds of retry:
* *Transient* failures against Gemini itself (503 overloaded, 429 rate
  limit, network timeouts) — see `_is_retryable_error` and
  `_generate_content_with_retry`. Deliberately different from *fallback* to
  a different provider, which needs the Provider Registry and is Phase 9's
  job (docs/development_plan.md).
* *Malformed-output* failures — Gemini returns a 200 OK but the response
  body isn't valid JSON, doesn't match `response_schema`, or (see
  `_find_degenerate_placeholder_string`) matches the schema perfectly but
  is semantically empty — a freeform text field came back as pure
  punctuation with no letters or digits in it, caught live on the
  Matching stage. None of these are network errors, so the retry above
  never sees them; a fresh generation is usually enough to fix a one-off
  glitch (more likely on longer responses, e.g. the Bullet Rewriting
  stage's full per-role bullet list, or the Matching stage's full
  requirement-by-requirement match/gap list), so `generate_structured`
  retries the whole call (not just re-parsing the same bad text) up to
  `max_retries` times before giving up.

Retrying the same provider a few times either way is cheap, safe, and
doesn't require any Provider Registry infrastructure.

Phase 19: `generate_structured()` also logs one INFO line per successful
call with model/elapsed-time/token counts — numbers only, never prompt or
response text (see app/logging_setup.py's module docstring on why). This is
the data `docs/PROJECT_CONTEXT.md`'s deferred fuzzy bullet-variant-matching
decision needs before it can be made from real numbers instead of a guess.

`response_schema` is now also passed straight through to the Gemini API
call (`config.response_schema`, alongside the existing
`response_mime_type: application/json`) instead of relying solely on each
prompt's own "Output format" prose — `google-genai` converts a Pydantic
model class into Gemini's constrained-decoding schema directly. This
doesn't remove the local `json.loads`/`model_validate` step below (schema
enforcement isn't guaranteed 100% airtight, and validating locally is
cheap insurance either way), but it should reduce how often a call needs
the malformed-output retry described above in the first place — each of
those retries is a full extra round-trip, and per docs/architecture.md's
Logging section ("operation name" should be in every log line, which
wasn't true before this), every log line here now also names which prompt
schema (`stage`) it was for, and the final success line reports how many
regenerate-the-whole-call retries (`regenerations`, malformed JSON/schema
mismatch) and transient-error retries (`transient_retries`, 503/429/
timeout) the call needed — added specifically so the JD parser/matcher/
planner/bullet-rewriter/quality-recheck retry ratio can be read back out of
logs instead of guessed at (see app/logging_setup.py for where these now
land durably).

That same retry-ratio logging also surfaced a bigger latency source than
retries ever were: `thoughts_token_count` (added to the success log line
alongside prompt/response token counts) showed every one of the app's six
calls spending more tokens on hidden "thinking" than on the actual visible
response — up to 6x, on gemini-2.5-flash's default unbounded/AUTOMATIC
thinking budget. `generate_structured()` now takes an optional
`thinking_budget` (see ILLMProvider's docstring) that callers can use to
cap or disable this per call. app/use_cases.py disables it outright (`0`)
for the two mechanical stages (JD Parsing, Quality Recheck) and caps it at
a real but reduced budget for the two reasoning-heavy ones (Rewrite
Planning, Bullet Rewriting) — see that module's own comment for the real
grammar/fabrication regressions a too-low Bullet Rewriting budget produced
on a real generation, and docs/development_plan.md's "Post-4.10 fixes,
round 2" for the full story. Matching stays on the model's default —
its own known content-quality risk (see `_find_degenerate_placeholder_
string` below) already has a generic retry guard, and it hasn't yet had
the same real-generation-comparison scrutiny the other three stages got.
"""

from __future__ import annotations

import json
import time

from pydantic import BaseModel, ValidationError as PydanticValidationError

from app.errors import ParsingError, ProviderError, ValidationError
from app.logging_setup import get_logger
from providers.base import ILLMProvider, TSchema

logger = get_logger(__name__)

# Status codes worth retrying: rate limiting and transient server-side
# unavailability. Anything else (4xx auth/bad-request, schema mismatches)
# won't fix itself on retry, so those are NOT in this set.
_RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# The google-genai SDK doesn't consistently expose a numeric status code on
# every exception it can raise, so we also fall back to matching known
# transient-failure markers in the exception's string representation.
_RETRYABLE_MARKERS = (
    "429",
    "500",
    "502",
    "503",
    "504",
    "UNAVAILABLE",
    "RESOURCE_EXHAUSTED",
    "DEADLINE_EXCEEDED",
    "OVERLOADED",
    "TIMEOUT",
    "CONNECTION",
)


def _is_retryable_error(exc: Exception) -> bool:
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code in _RETRYABLE_STATUS_CODES:
        return True
    message = str(exc).upper()
    return any(marker in message for marker in _RETRYABLE_MARKERS)


def _is_thinking_config_rejection(exc: Exception) -> bool:
    """A bare 400 INVALID_ARGUMENT with no field-level detail — the shape
    Gemini 3.x models return when sent `thinking_config.thinking_budget`
    (an integer), which those models don't accept; they use `thinking_level`
    (an enum) instead. Deliberately narrow (400 + INVALID_ARGUMENT only) so
    an unrelated bad-request error (malformed schema, bad prompt) doesn't
    silently get retried without thinking_config and instead surfaces as
    the real error it is.
    """
    code = getattr(exc, "code", None)
    if isinstance(code, int) and code != 400:
        return False
    return "INVALID_ARGUMENT" in str(exc).upper()


def _find_degenerate_placeholder_string(value: object) -> str | None:
    """Detects a known Gemini structured-output failure mode: a response
    that parses as JSON and matches `response_schema` (so
    `model_validate()` below sees nothing wrong with it) but is
    semantically empty — a freeform text field comes back as pure
    punctuation/whitespace with no letters or digits in it at all.

    Caught live: a Matching-stage response had every single
    `requirement_text`/`description`/`suggested_action`/`keyword` across
    17 matches, 7 gaps, and 18 skills-to-add come back as the literal
    two-character string `", "`, while the `strength`/`severity`/
    `evidence_ids` fields right next to them were all genuine — a short
    non-empty string is a perfectly valid `str`, so nothing about the
    schema itself was violated, and this went completely unnoticed until
    a person actually read the output.

    Deliberately generic — recurses through whatever pydantic models/
    lists/dicts the response happens to contain, keyed on nothing but "is
    this string non-empty and made up entirely of non-alphanumeric
    characters," never a field name or response schema. A real sentence
    in any of this app's supported languages always has at least one
    letter or digit in it; a degenerate placeholder like this one never
    does — that's a property of the failure's *shape*, not a rule about
    what a CV or vacancy means, so it belongs at this generic provider
    layer rather than as CV-domain business logic. Applied to every
    `generate_structured()` call (not just the Matching stage that first
    surfaced it) since the check is this cheap and this unlikely to ever
    false-positive on real content — the cost of a false trigger is one
    extra regeneration via the same retry loop already used for malformed
    JSON/schema mismatches below, not a hard failure.

    Returns a short description of the first offending value found (for
    the retry loop's warning/error log lines), or None if nothing looks
    wrong.
    """
    if isinstance(value, BaseModel):
        for name in type(value).model_fields:
            found = _find_degenerate_placeholder_string(getattr(value, name))
            if found:
                return found
        return None
    if isinstance(value, (list, tuple)):
        for item in value:
            found = _find_degenerate_placeholder_string(item)
            if found:
                return found
        return None
    if isinstance(value, dict):
        for item in value.values():
            found = _find_degenerate_placeholder_string(item)
            if found:
                return found
        return None
    if isinstance(value, str):
        stripped = value.strip()
        if stripped and not any(ch.isalnum() for ch in stripped):
            return f"a text field came back as {value!r} (no letters/digits at all)"
    return None


def _describe_json_parse_failure(exc: json.JSONDecodeError, raw_text: str) -> str:
    """Builds a ParsingError message that includes a snippet of the actual
    malformed text, not just json's line/column position — the position
    alone ("line 260 column 153") isn't enough to see what went wrong
    without the text itself, and this is the only place that ever sees
    `raw_text` (see the module docstring: it's never written to logs, only
    surfaced transiently to whoever catches/displays the resulting
    exception — the UI's error dialog, in ui/main_window.py).
    """
    start = max(0, exc.pos - 60)
    end = min(len(raw_text), exc.pos + 60)
    snippet = raw_text[start:end].replace("\n", "\\n")
    return f"Could not parse Gemini response as JSON: {exc}. Near: ...{snippet}..."


class GeminiProvider(ILLMProvider):
    def __init__(
        self,
        api_key: str,
        model: str,
        max_retries: int = 3,
        retry_base_delay_seconds: float = 1.0,
    ):
        if not api_key:
            raise ProviderError("Gemini API key is not configured.")
        self._model = model
        self._api_key = api_key
        self._max_retries = max_retries
        self._retry_base_delay_seconds = retry_base_delay_seconds
        self._client = None  # lazily initialized to keep import cost low

    def _get_client(self):
        if self._client is None:
            from google import genai  # imported lazily, see note above

            self._client = genai.Client(api_key=self._api_key)
        return self._client

    def _generate_content_with_retry(
        self,
        client,
        prompt: str,
        response_schema: type[TSchema],
        stage: str,
        thinking_budget: int | None,
    ) -> tuple[object, int]:
        """Call the Gemini API, retrying transient failures with backoff.

        Total attempts = 1 + max_retries. Delay doubles each retry
        (retry_base_delay_seconds, then *2, *4, ...). Non-retryable errors and
        the final retryable failure are both translated to ProviderError and
        raised immediately. Returns `(response, transient_retries)` —
        `transient_retries` is how many of *this* call's attempts failed
        with a retryable error before it succeeded, so the caller can fold
        it into the per-call retry stats it logs (see module docstring).

        `response_schema`/`stage` are passed through only for the API call
        itself (constrained decoding) and the retry/failure log lines
        (`stage` names which prompt's schema this is, per
        docs/architecture.md's "operation name" logging requirement) — this
        method still returns the raw SDK response; parsing/validating it
        against `response_schema` stays generate_structured()'s job.

        `thinking_budget`, when not None, is passed through as
        `config.thinking_config.thinking_budget` — see
        ILLMProvider.generate_structured's docstring for what it means.
        Left out of `config` entirely when None so a call that doesn't ask
        for a specific budget keeps the model's own default (AUTOMATIC/
        unbounded for gemini-2.5-flash), unchanged from before this
        parameter existed.
        """
        last_exc: Exception | None = None
        for attempt in range(1, self._max_retries + 2):  # +1 initial, +1 for range()
            try:
                request_config = {
                    "response_mime_type": "application/json",
                    "response_schema": response_schema,
                }
                if thinking_budget is not None:
                    request_config["thinking_config"] = {"thinking_budget": thinking_budget}
                try:
                    response = client.models.generate_content(
                        model=self._model,
                        contents=prompt,
                        config=request_config,
                    )
                except Exception as exc:  # noqa: BLE001 - inspected below, re-raised if not this case
                    # Gemini 3.x models dropped the integer `thinking_budget`
                    # knob in favor of a `thinking_level` enum (minimal/low/
                    # medium/high) — sending thinking_config.thinking_budget
                    # to one of these models is rejected outright with a bare
                    # 400 INVALID_ARGUMENT (no field-level detail in the
                    # message). Rather than guess a budget->level mapping for
                    # every caller (app/use_cases.py's specific budget values
                    # were tuned against gemini-2.5-flash via real-generation
                    # comparisons — see that module's own comment — and
                    # re-tuning for `thinking_level` needs the same rigor,
                    # not a one-line guess), fall back to the model's own
                    # default reasoning level by dropping thinking_config
                    # entirely and retrying this same attempt once. Only
                    # takes this path when thinking_config was actually in
                    # the request and the failure looks like this specific
                    # rejection, so a genuine invalid-argument error (bad
                    # schema, bad prompt) still surfaces normally below.
                    if "thinking_config" in request_config and _is_thinking_config_rejection(exc):
                        logger.warning(
                            "Gemini API call failed | stage=%s | attempt=%d/%d "
                            "| model=%s doesn't accept thinking_config.thinking_budget=%s "
                            "(likely a Gemini 3.x model using thinking_level instead) "
                            "— retrying without it, model's own default reasoning level applies: %s",
                            stage,
                            attempt,
                            self._max_retries + 1,
                            self._model,
                            thinking_budget,
                            exc,
                        )
                        fallback_config = {
                            key: value for key, value in request_config.items() if key != "thinking_config"
                        }
                        response = client.models.generate_content(
                            model=self._model,
                            contents=prompt,
                            config=fallback_config,
                        )
                    else:
                        raise
                return response, attempt - 1
            except Exception as exc:  # noqa: BLE001 - translate any SDK error
                last_exc = exc
                retryable = _is_retryable_error(exc)
                attempts_left = self._max_retries + 1 - attempt
                if not retryable or attempts_left <= 0:
                    logger.error(
                        "Gemini API call failed | stage=%s | attempt=%d/%d "
                        "(retryable=%s), giving up: %s",
                        stage,
                        attempt,
                        self._max_retries + 1,
                        retryable,
                        exc,
                    )
                    raise ProviderError(f"Gemini API call failed: {exc}") from exc

                delay = self._retry_base_delay_seconds * (2 ** (attempt - 1))
                logger.warning(
                    "Gemini API call failed | stage=%s | attempt=%d/%d "
                    "(retryable), retrying in %.1fs: %s",
                    stage,
                    attempt,
                    self._max_retries + 1,
                    delay,
                    exc,
                )
                time.sleep(delay)

        # Unreachable in practice (the loop always returns or raises), but
        # keeps type checkers and readers honest about the fallthrough case.
        raise ProviderError(f"Gemini API call failed: {last_exc}") from last_exc

    def _log_call_stats(
        self,
        response,
        stage: str,
        attempt: int,
        transient_retries: int,
        elapsed_seconds: float,
        thinking_budget: int | None,
    ) -> None:
        """Logs one INFO line per successful `generate_structured()` call —
        stage, model, elapsed time, attempt/retry counts, token counts.
        Deliberately numbers only, per app/logging_setup.py's "prompts,
        generated resume content must never be logged" rule; never touches
        `response.text`.

        `attempt` is how many *whole-call* regenerations
        (`generate_structured`'s own retry loop — malformed JSON or a
        schema mismatch) this call needed, 1 meaning none;
        `regenerations` below is that minus 1 so it reads as a retry count,
        not a 1-based attempt number, matching `transient_retries`'
        already-zero-based convention. `transient_retries` is the total
        count of retryable-error attempts (503/429/timeout,
        `_generate_content_with_retry`) absorbed across all of those
        whole-call attempts combined. Both are 0 on the (expected-common)
        case where nothing needed retrying at all — this is exactly the
        data needed to compute a real retry ratio across calls instead of
        guessing at one (see module docstring).

        `usage_metadata` isn't guaranteed present on every SDK response
        (and the tests' `_FakeResponse` doesn't set it at all), so every
        field is read defensively rather than assumed.
        """
        usage = getattr(response, "usage_metadata", None)
        logger.info(
            "Gemini call succeeded | stage=%s | model=%s | elapsed=%.2fs | "
            "attempt=%d/%d | regenerations=%d | transient_retries=%d | "
            "thinking_budget=%s | prompt_tokens=%s | response_tokens=%s | "
            "thoughts_tokens=%s | total_tokens=%s",
            stage,
            self._model,
            elapsed_seconds,
            attempt,
            self._max_retries + 1,
            attempt - 1,
            transient_retries,
            "auto" if thinking_budget is None else thinking_budget,
            getattr(usage, "prompt_token_count", None),
            getattr(usage, "candidates_token_count", None),
            getattr(usage, "thoughts_token_count", None),
            getattr(usage, "total_token_count", None),
        )

    def generate_structured(
        self,
        prompt: str,
        response_schema: type[TSchema],
        thinking_budget: int | None = None,
    ) -> TSchema:
        """Generate content and validate it against `response_schema`.

        Retries the *whole call* (not just re-parsing the same bad text) up
        to `max_retries` times if Gemini's response body is malformed JSON
        or doesn't match the schema — see the module docstring for why
        that's distinct from `_generate_content_with_retry`'s transient-
        network-error retry, and `_describe_json_parse_failure` for why the
        final ParsingError includes a snippet of the actual malformed text.

        `thinking_budget` — see ILLMProvider.generate_structured's
        docstring; forwarded to every attempt (including regenerations) so
        a call that consistently blows the budget doesn't quietly fall back
        to unbounded thinking on retry.
        """
        client = self._get_client()
        start = time.perf_counter()
        stage = getattr(response_schema, "__name__", "unknown")
        transient_retries_total = 0

        last_exc: ParsingError | ValidationError | None = None
        for attempt in range(1, self._max_retries + 2):  # +1 initial, +1 for range()
            response, transient_retries = self._generate_content_with_retry(
                client, prompt, response_schema, stage, thinking_budget
            )
            transient_retries_total += transient_retries
            raw_text = response.text

            try:
                data = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                last_exc = ParsingError(_describe_json_parse_failure(exc, raw_text))
            else:
                try:
                    validated = response_schema.model_validate(data)
                except PydanticValidationError as exc:
                    last_exc = ValidationError(
                        f"Gemini response did not match {response_schema.__name__}: {exc}"
                    )
                else:
                    degenerate = _find_degenerate_placeholder_string(validated)
                    if degenerate is not None:
                        last_exc = ValidationError(
                            f"Gemini response for {response_schema.__name__} looks "
                            f"degenerate: {degenerate}"
                        )
                    else:
                        self._log_call_stats(
                            response, stage, attempt, transient_retries_total,
                            time.perf_counter() - start, thinking_budget,
                        )
                        return validated

            attempts_left = self._max_retries + 1 - attempt
            if attempts_left <= 0:
                logger.error(
                    "Gemini response failed to parse/validate | stage=%s | "
                    "attempt=%d/%d, giving up: %s",
                    stage,
                    attempt,
                    self._max_retries + 1,
                    last_exc,
                )
                raise last_exc

            delay = self._retry_base_delay_seconds * (2 ** (attempt - 1))
            logger.warning(
                "Gemini response failed to parse/validate | stage=%s | "
                "attempt=%d/%d, regenerating in %.1fs: %s",
                stage,
                attempt,
                self._max_retries + 1,
                delay,
                last_exc,
            )
            time.sleep(delay)

        # Unreachable in practice (the loop always returns or raises), but
        # keeps type checkers and readers honest about the fallthrough case.
        raise last_exc
