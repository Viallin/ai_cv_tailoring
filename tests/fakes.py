"""Shared test fakes.

_QueuedFakeProvider originated in tests/test_integration/test_full_pipeline.py
(Phase 12.2) — hoisted here in Phase 13 so tests/test_api/ can reuse the same
fake-only-the-provider-boundary pattern instead of reimplementing it, per
docs/architecture.md's Integration Testing philosophy: fake the one
genuinely external, non-deterministic, costly dependency (the LLM call),
run everything else for real.
"""

from __future__ import annotations

from providers.base import ILLMProvider


class QueuedFakeProvider(ILLMProvider):
    """Returns pre-built response objects in call order, asserting the
    requested response_schema matches what was queued (catches a
    wrong-schema-for-this-stage wiring bug)."""

    def __init__(self, responses=()):
        self._responses = list(responses)
        self.calls: list[type] = []
        self.thinking_budgets: list[int | None] = []
        # The exact rendered prompt text of the most recent call — lets a
        # test assert on what actually reached the LLM (e.g. that a
        # document-level override made it into the prompt) without needing
        # its own bespoke fake.
        self.last_prompt: str | None = None

    def queue(self, response) -> None:
        self._responses.append(response)

    def generate_structured(self, prompt, response_schema, thinking_budget=None):
        assert self._responses, "no more queued responses"
        response = self._responses.pop(0)
        assert isinstance(response, response_schema), (
            f"expected {response_schema.__name__}, queued {type(response).__name__}"
        )
        self.calls.append(response_schema)
        self.thinking_budgets.append(thinking_budget)
        self.last_prompt = prompt
        return response
