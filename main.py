"""Entry point.

Wires config -> logging -> services (app/services.py) -> UI (ui/main_window.py)
together. As of Phase 6 this launches the real PySide6 window.
"""

from __future__ import annotations

from app.config import config
from app.logging_setup import get_logger, setup_logging
from app.services import build_services


def main() -> None:
    setup_logging()
    logger = get_logger(__name__)
    logger.info("Starting AI CV Builder (prototype)")

    services = build_services(config)
    logger.info("Services wired successfully. Launching UI.")

    # Imported lazily so main.py stays importable (e.g. for tests) even in
    # environments without PySide6 installed.
    from ui.main_window import run

    run(services)


if __name__ == "__main__":
    main()
