"""Logging configuration.

Per docs/architecture.md > Error Handling > Logging:
logs should include timestamp, operation name, provider/model when applicable,
error category, and stack trace in debug mode only. Sensitive information
(API keys, personal data, prompts, generated resume content) must never be logged.

Logs to stdout *and* a rotating file under `config.data_dir` (the same
durable-storage location the SQLite DB already lives in — see
app/config.py). Stdout alone was never captured anywhere in the packaged
desktop app (packaging/run_backend.py just launches uvicorn with no output
redirection), so e.g. providers/gemini_provider.py's per-call retry-stats
log lines — added specifically to answer "what's our retry ratio" instead
of guessing — were unrecoverable outside a dev session watching the
console. 5 x 1MB rotated files is plenty for INFO-level lines that are
deliberately numbers-only (never prompt/response text), so this stays
small even over many generations.
"""

from __future__ import annotations

import logging
import logging.handlers
import sys

from app.config import config

_LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"


def setup_logging() -> None:
    level = getattr(logging, config.log_level.upper(), logging.INFO)
    handlers: list[logging.Handler] = [logging.StreamHandler(sys.stdout)]

    try:
        log_dir = config.data_dir / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        handlers.append(
            logging.handlers.RotatingFileHandler(
                log_dir / "app.log",
                maxBytes=1_000_000,
                backupCount=5,
                encoding="utf-8",
            )
        )
    except OSError:
        # Falls back to stdout-only rather than crashing app startup over a
        # log file the OS won't let us create/open (e.g. a read-only or
        # already-locked data_dir) — logging is diagnostic, not essential.
        logging.basicConfig(level=level, format=_LOG_FORMAT, handlers=handlers)
        logging.getLogger(__name__).warning(
            "Could not open a log file under %s; logging to stdout only.", log_dir
        )
        return

    logging.basicConfig(level=level, format=_LOG_FORMAT, handlers=handlers)


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
