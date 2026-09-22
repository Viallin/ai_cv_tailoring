"""Application error categories.

Mirrors the Error Categories table in docs/architecture.md. Every layer should
raise one of these instead of leaking provider/library-specific exceptions.
"""

from __future__ import annotations


class AppError(Exception):
    """Base class for all application-level errors."""


class ConfigurationError(AppError):
    """Missing or invalid application configuration."""


class PromptError(AppError):
    """Missing prompt template, invalid placeholders, or rendering failure."""


class ProviderError(AppError):
    """Failure while communicating with an LLM provider."""


class ValidationError(AppError):
    """AI response does not match the expected contract."""


class ParsingError(AppError):
    """Unable to deserialize or interpret the provider response."""


class StorageError(AppError):
    """Failure while reading or writing local data."""


class ExportError(AppError):
    """Failure during document export."""


class UnexpectedError(AppError):
    """Any unhandled internal application error."""
