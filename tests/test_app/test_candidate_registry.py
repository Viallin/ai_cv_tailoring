from sqlmodel import SQLModel

from app.candidate_registry import CandidateProfileSummary, CandidateRegistry
from app.candidate_service import CandidateService
from db.engine import get_engine
from domain.models import Experience


def make_registry(tmp_path) -> CandidateRegistry:
    engine = get_engine(f"sqlite:///{tmp_path / 'test.db'}")
    SQLModel.metadata.create_all(engine)
    return CandidateRegistry(engine=engine)


def test_list_profiles_returns_empty_list_when_none_exist(tmp_path):
    registry = make_registry(tmp_path)

    assert registry.list_profiles() == []


def test_service_for_returns_a_working_candidate_service(tmp_path):
    registry = make_registry(tmp_path)

    service = registry.service_for("ada")
    service.create(name="Ada Lovelace")

    assert isinstance(service, CandidateService)
    assert service.get().name == "Ada Lovelace"


def test_service_for_scopes_each_id_to_its_own_storage(tmp_path):
    registry = make_registry(tmp_path)

    registry.service_for("ada").create(name="Ada Lovelace")
    registry.service_for("charles").create(name="Charles Babbage")

    assert registry.service_for("ada").get().name == "Ada Lovelace"
    assert registry.service_for("charles").get().name == "Charles Babbage"


def test_list_profiles_reflects_saved_candidates(tmp_path):
    registry = make_registry(tmp_path)
    registry.service_for("ada").create(name="Ada Lovelace")
    registry.service_for("charles").create(name="Charles Babbage")

    profiles = registry.list_profiles()

    assert {p.id for p in profiles} == {"ada", "charles"}
    assert {p.name for p in profiles} == {"Ada Lovelace", "Charles Babbage"}


def test_list_profiles_reports_experience_count(tmp_path):
    registry = make_registry(tmp_path)
    service = registry.service_for("ada")
    service.create(name="Ada Lovelace")
    service.replace(
        service.get().model_copy(
            update={
                "experience": [
                    Experience(id="exp-1", company="Acme", position="Engineer"),
                    Experience(id="exp-2", company="Globex", position="Lead"),
                ]
            }
        )
    )

    profiles = registry.list_profiles()

    assert profiles[0] == CandidateProfileSummary(
        id="ada", name="Ada Lovelace", experience_count=2
    )


def test_list_profiles_reports_headline_and_language(tmp_path):
    registry = make_registry(tmp_path)
    registry.service_for("ada").create(name="Ada Lovelace", headline="Analytical Engineer", language="en")
    registry.service_for("olga").create(name="Ольга Иванова", headline="Инженер", language="ru")

    profiles = {p.id: p for p in registry.list_profiles()}

    assert profiles["ada"].headline == "Analytical Engineer"
    assert profiles["ada"].language == "en"
    assert profiles["olga"].headline == "Инженер"
    assert profiles["olga"].language == "ru"


def test_list_profiles_defaults_headline_none_and_language_en(tmp_path):
    registry = make_registry(tmp_path)
    registry.service_for("ada").create(name="Ada Lovelace")

    profile = registry.list_profiles()[0]

    assert profile.headline is None
    assert profile.language == "en"


def test_new_profile_id_returns_distinct_ids(tmp_path):
    registry = make_registry(tmp_path)

    ids = {registry.new_profile_id() for _ in range(20)}

    assert len(ids) == 20
