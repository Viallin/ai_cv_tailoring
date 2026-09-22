"""AppError -> HTTP status mapping, registered once against the AppError
base class (Starlette resolves exception handlers by walking
type(exc).__mro__, so one handler catches every subclass).

Always `import app.errors as app_errors` here, never
`from app.errors import ValidationError` — app.errors.ValidationError is a
different class from pydantic.ValidationError and FastAPI's own
RequestValidationError, and a bare import would invite exactly that
confusion in this module more than anywhere else in the codebase.

Known accepted gap: CandidateService._find()'s "entity id not found" raises
the same app_errors.ValidationError as a genuine input-validation failure,
so it maps to 422 here rather than a more semantically correct 404. Not
fixed in Phase 13 (would need a new app/errors.py exception type) — see
docs/development_plan.md's Phase 13 plan.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

import app.errors as app_errors

_STATUS_MAP: dict[type[app_errors.AppError], int] = {
    app_errors.ConfigurationError: 500,
    app_errors.PromptError: 500,
    app_errors.ProviderError: 502,
    app_errors.ParsingError: 502,
    app_errors.ValidationError: 422,
    app_errors.StorageError: 500,
    app_errors.ExportError: 500,
    app_errors.UnexpectedError: 500,
}


def _error_body(category: str, message: str) -> dict:
    return {"error": {"category": category, "message": message}}


async def _handle_app_error(_request: Request, exc: app_errors.AppError) -> JSONResponse:
    status_code = _STATUS_MAP.get(type(exc), 500)
    return JSONResponse(status_code=status_code, content=_error_body(type(exc).__name__, str(exc)))


async def _handle_request_validation_error(_request: Request, exc: RequestValidationError) -> JSONResponse:
    # Same envelope shape as AppError responses, so the frontend has exactly
    # one error shape to parse regardless of which layer rejected a request.
    return JSONResponse(status_code=422, content=_error_body("RequestValidationError", str(exc)))


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(app_errors.AppError, _handle_app_error)
    app.add_exception_handler(RequestValidationError, _handle_request_validation_error)
