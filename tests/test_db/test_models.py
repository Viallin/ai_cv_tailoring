"""CandidateRow/EvidenceRow round-trip against a real (file-based) SQLite
engine — not the storage-agnostic behavior CandidateService already covers
in tests/test_app/test_candidate_service.py, just that the table
definitions themselves (JSON column, composite Evidence PK, cascade
delete) behave as db/models.py's docstrings claim.
"""

from __future__ import annotations

from sqlmodel import Session, SQLModel, select

from db.engine import get_engine
from db.models import CandidateRow, EvidenceRow


def make_engine(tmp_path):
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return engine


def test_candidate_row_json_column_round_trips(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        session.add(
            CandidateRow(id="cand-1", data={"name": "Ada Lovelace", "experience": []})
        )
        session.commit()

    with Session(engine) as session:
        row = session.get(CandidateRow, "cand-1")
        assert row.data == {"name": "Ada Lovelace", "experience": []}


def test_evidence_row_composite_pk_allows_same_id_across_candidates(tmp_path):
    """Evidence.id (e.g. "ev-1") is only unique within one candidate's own
    list — two different candidates legitimately reuse the same id. A
    single-column PK on `id` alone breaks this (caught during migration
    script testing); the composite (candidate_id, id) PK must not."""
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        session.add(CandidateRow(id="cand-1", data={"name": "Ada"}))
        session.add(CandidateRow(id="cand-2", data={"name": "Bob"}))
        session.add(EvidenceRow(id="ev-1", candidate_id="cand-1", position=0, text="Did a thing."))
        session.add(EvidenceRow(id="ev-1", candidate_id="cand-2", position=0, text="Did another thing."))
        session.commit()

    with Session(engine) as session:
        rows = session.exec(select(EvidenceRow).order_by(EvidenceRow.candidate_id)).all()
        assert [(r.candidate_id, r.id, r.text) for r in rows] == [
            ("cand-1", "ev-1", "Did a thing."),
            ("cand-2", "ev-1", "Did another thing."),
        ]


def test_deleting_candidate_row_cascades_to_its_evidence(tmp_path):
    engine = make_engine(tmp_path)
    with Session(engine) as session:
        session.add(CandidateRow(id="cand-1", data={"name": "Ada"}))
        session.add(EvidenceRow(id="ev-1", candidate_id="cand-1", position=0, text="Did a thing."))
        session.commit()

    with Session(engine) as session:
        session.delete(session.get(CandidateRow, "cand-1"))
        session.commit()

    with Session(engine) as session:
        remaining = session.exec(select(EvidenceRow)).all()
        assert remaining == []
