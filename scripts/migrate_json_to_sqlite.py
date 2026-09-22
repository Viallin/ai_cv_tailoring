"""One-time JSON -> SQLite migration (Phase 13, docs/development_plan.md).

Reads existing data/candidates/<id>/candidate.json + evidence.json (via the
unmodified app/storage.py functions — kept in the codebase specifically as
this script's read path) and writes them into the new SQLite backend
(db/models.py) via CandidateService, preserving each profile's existing id
as the SQLite primary key: the desktop UI's active-profile selection
depends on these ids staying stable across the migration.

Idempotent: a candidate id that already has a CandidateRow is skipped
(logged, not an error) unless --overwrite is passed. Each candidate is
migrated in its own transaction (CandidateService.replace() already opens
one) — one malformed profile does not block or roll back any profile
already committed.

Run `alembic upgrade head` first — this script does not create tables.

Usage:
    uv run python -m scripts.migrate_json_to_sqlite
    uv run python -m scripts.migrate_json_to_sqlite --overwrite
    uv run python -m scripts.migrate_json_to_sqlite --data-dir data --database-url sqlite:///data/cvai.db
"""

from __future__ import annotations

import argparse
import logging
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import Engine

from app.candidate_service import CandidateService
from app.config import config as app_config
from app.errors import AppError
from app.storage import list_candidate_ids, load_candidate, load_evidence
from db.engine import get_engine

logger = logging.getLogger(__name__)


@dataclass
class MigrationSummary:
    migrated: list[str] = field(default_factory=list)
    skipped: list[str] = field(default_factory=list)
    failed: list[tuple[str, str]] = field(default_factory=list)  # (candidate_id, error message)

    @property
    def ok(self) -> bool:
        return not self.failed


def migrate(data_dir: Path, engine: Engine, overwrite: bool = False) -> MigrationSummary:
    summary = MigrationSummary()
    candidates_dir = data_dir / "candidates"

    for candidate_id in list_candidate_ids(data_dir):
        service = CandidateService(candidate_id=candidate_id, engine=engine)
        try:
            if service.get() is not None and not overwrite:
                summary.skipped.append(candidate_id)
                logger.info("Skipping %s (already migrated)", candidate_id)
                continue

            profile_dir = candidates_dir / candidate_id
            candidate = load_candidate(profile_dir)
            if candidate is None:
                raise AppError(f"candidate.json missing for {candidate_id!r}")
            evidence = load_evidence(profile_dir)

            service.replace(candidate, evidence=evidence)
            summary.migrated.append(candidate_id)
            logger.info(
                "Migrated %s (%r: %d experience, %d evidence)",
                candidate_id,
                candidate.name,
                len(candidate.experience),
                len(evidence),
            )
        except Exception as exc:  # noqa: BLE001 — one bad profile must not abort the run
            summary.failed.append((candidate_id, str(exc)))
            logger.error("Failed to migrate %s: %s", candidate_id, exc)

    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=app_config.data_dir)
    parser.add_argument("--database-url", type=str, default=app_config.database_url)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Re-migrate profiles that already have a CandidateRow (default: skip them).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)-8s | %(message)s")

    engine = get_engine(args.database_url)
    summary = migrate(args.data_dir, engine, overwrite=args.overwrite)

    print(f"\nMigrated: {len(summary.migrated)} {summary.migrated}")
    print(f"Skipped (already migrated): {len(summary.skipped)} {summary.skipped}")
    if summary.failed:
        print(f"Failed: {len(summary.failed)}")
        for candidate_id, error in summary.failed:
            print(f"  {candidate_id}: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
