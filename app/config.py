"""Application configuration.

Loads settings from environment variables (and a local .env file if present).
This is the only place in the codebase that should read os.environ directly —
every other layer receives config values through this object.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Config:
    llm_provider: str
    llm_fallback_providers: tuple[str, ...]
    llm_model: str
    gemini_api_key: str
    llm_max_retries: int
    llm_retry_base_delay_seconds: float
    prompts_dir: Path
    data_dir: Path
    log_level: str
    database_url: str

    @staticmethod
    def load() -> "Config":
        fallback_providers = tuple(
            name.strip()
            for name in os.getenv("LLM_FALLBACK_PROVIDERS", "").split(",")
            if name.strip()
        )
        data_dir = Path(os.getenv("DATA_DIR", "data"))
        return Config(
            llm_provider=os.getenv("LLM_PROVIDER", "gemini"),
            llm_fallback_providers=fallback_providers,
            llm_model=os.getenv("LLM_MODEL", "gemini-3.6-flash"),
            gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
            # Retries for transient provider errors (503/429/timeouts) against
            # the *same* provider — see providers/registry.py and
            # providers/fallback_provider.py (Phase 9) for falling back to a
            # different provider via llm_fallback_providers.
            llm_max_retries=int(os.getenv("LLM_MAX_RETRIES", "3")),
            llm_retry_base_delay_seconds=float(os.getenv("LLM_RETRY_BASE_DELAY_SECONDS", "1.0")),
            prompts_dir=Path(os.getenv("PROMPTS_DIR", "prompts")),
            data_dir=data_dir,
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            # SQLite by default (Phase 13, docs/development_plan.md Version 2) —
            # single-user/local, no Postgres/server needed. Defaults to a file
            # under data_dir rather than a fixed literal so DATA_DIR overrides
            # still keep the DB next to the (legacy) JSON profiles it replaces.
            database_url=os.getenv("DATABASE_URL", f"sqlite:///{data_dir / 'cvai.db'}"),
        )


config = Config.load()
