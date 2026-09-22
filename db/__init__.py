"""SQLite persistence layer (Phase 13, docs/development_plan.md Version 2).

Storage-only concern, kept separate from domain/ (business entities) and
app/ (orchestration) — see docs/architecture.md's Version 2 Project
Structure note. Nothing outside this package should import sqlalchemy or
sqlmodel directly.
"""
