"""FastAPI dependency providers.

get_services() reads the process-lifetime Services container that
api/main.py's lifespan handler stashes on app.state at startup. Tests
override this dependency directly
(app.dependency_overrides[get_services] = lambda: fake_services) rather
than touching app.state, so a fake-provider-backed Services + tmp engine
never has to fight the real one built from live config/API keys.
"""

from __future__ import annotations

from fastapi import Depends, Request

from app.candidate_service import CandidateService
from app.services import Services


def get_services(request: Request) -> Services:
    return request.app.state.services


def get_candidate_service(
    candidate_id: str, services: Services = Depends(get_services)
) -> CandidateService:
    return services.candidate_registry.service_for(candidate_id)
