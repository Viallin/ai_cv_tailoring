"""AppError subclass -> HTTP status code mapping (api/errors.py), plus
FastAPI's own RequestValidationError getting the same response envelope.

Tested against a minimal throwaway app rather than the full api.main app —
this is purely about the error-handling wiring itself, not any real
business route (api/routes/*.py's ValidationError -> 422 behavior is
already exercised end-to-end by tests/test_api/test_entity_crud.py etc.).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel

import app.errors as app_errors
from api.errors import register_exception_handlers


def _make_app() -> FastAPI:
    error_app = FastAPI()
    register_exception_handlers(error_app)

    @error_app.get("/boom/{category}")
    def boom(category: str):
        raise getattr(app_errors, category)(f"simulated {category}")

    class Body(BaseModel):
        name: str

    @error_app.post("/validate")
    def validate(body: Body):
        return body

    return error_app


@pytest.fixture
def error_client():
    return TestClient(_make_app())


@pytest.mark.parametrize(
    "category,expected_status",
    [
        ("ConfigurationError", 500),
        ("PromptError", 500),
        ("ProviderError", 502),
        ("ParsingError", 502),
        ("ValidationError", 422),
        ("StorageError", 500),
        ("ExportError", 500),
        ("UnexpectedError", 500),
    ],
)
def test_app_error_subclass_maps_to_expected_status(error_client, category, expected_status):
    r = error_client.get(f"/boom/{category}")
    assert r.status_code == expected_status
    body = r.json()
    assert body["error"]["category"] == category
    assert f"simulated {category}" in body["error"]["message"]


def test_request_validation_error_gets_same_envelope_shape(error_client):
    r = error_client.post("/validate", json={})  # missing required "name"
    assert r.status_code == 422
    body = r.json()
    assert body["error"]["category"] == "RequestValidationError"
