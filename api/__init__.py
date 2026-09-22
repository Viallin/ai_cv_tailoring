"""FastAPI HTTP layer (Phase 13, docs/development_plan.md Version 2).

Routes only — no business logic. Wraps app/services.py, app/pipeline.py,
and app/candidate_service.py, which stay the actual implementation (and
keep driving the still-unmodified desktop UI, ui/main_window.py, through
this phase). See docs/architecture.md's Version 2 note.
"""
