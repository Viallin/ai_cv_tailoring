from app.bullet_locking import partition_locked_evidence, splice_locked_bullets
from domain.models import (
    Candidate,
    CVProjection,
    Evidence,
    Experience,
    ExperienceProject,
    TailoredBullet,
    TailoredExperience,
)


# ----- partition_locked_evidence --------------------------------------------


def test_partition_separates_locked_from_unlocked():
    unlocked_item = Evidence(id="ev-1", text="Not locked.")
    locked_item = Evidence(id="ev-2", text="Locked.", experience_id="exp-1", locked=True)

    unlocked, locked = partition_locked_evidence([unlocked_item, locked_item])

    assert unlocked == [unlocked_item]
    assert locked == [locked_item]


def test_partition_treats_a_locked_item_with_no_experience_id_as_unlocked():
    # An Evidence item not tied to any role can't back a bullet at all --
    # same "no experience_id -> not eligible" precedent as
    # app/bullet_provenance.py.
    item = Evidence(id="ev-1", text="Locked but unlinked.", locked=True)

    unlocked, locked = partition_locked_evidence([item])

    assert unlocked == [item]
    assert locked == []


def test_partition_with_no_locked_items_returns_everything_unlocked():
    items = [Evidence(id="ev-1", text="A"), Evidence(id="ev-2", text="B")]

    unlocked, locked = partition_locked_evidence(items)

    assert unlocked == items
    assert locked == []


# ----- splice_locked_bullets -------------------------------------------------


def test_splice_appends_a_locked_bullet_into_an_existing_tailored_experience():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    projection = CVProjection(
        summary="...",
        experience=[
            TailoredExperience(
                experience_id="exp-1", bullets=[TailoredBullet(text="AI bullet.", evidence_id="ev-1")]
            )
        ],
    )
    locked_item = Evidence(
        id="ev-2", text="Original.", experience_id="exp-1", locked=True, locked_text="Approved wording."
    )

    result = splice_locked_bullets(projection, candidate, [locked_item])

    [entry] = result.experience
    assert [b.text for b in entry.bullets] == ["AI bullet.", "Approved wording."]
    assert entry.bullets[1].evidence_id == "ev-2"


def test_splice_falls_back_to_raw_evidence_text_when_locked_text_is_unset():
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    projection = CVProjection(summary="...", experience=[])
    locked_item = Evidence(id="ev-1", text="Raw evidence text.", experience_id="exp-1", locked=True)

    result = splice_locked_bullets(projection, candidate, [locked_item])

    [entry] = result.experience
    assert entry.bullets[0].text == "Raw evidence text."


def test_splice_creates_a_tailored_experience_when_the_role_has_none():
    # The real bug this function exists to prevent: if a role's *entire*
    # evidence set is locked, Bullet Rewriting never saw any evidence for
    # it and produced no TailoredExperience -- app/cv_assembler.py would
    # then silently drop that role from the assembled CV.
    candidate = Candidate(
        name="Ada", experience=[Experience(id="exp-1", company="Acme", position="Engineer")]
    )
    projection = CVProjection(summary="...", experience=[])
    locked_item = Evidence(
        id="ev-1", text="Original.", experience_id="exp-1", locked=True, locked_text="Locked wording."
    )

    result = splice_locked_bullets(projection, candidate, [locked_item])

    assert len(result.experience) == 1
    assert result.experience[0].experience_id == "exp-1"
    assert result.experience[0].bullets[0].text == "Locked wording."


def test_splice_resolves_the_display_name_of_a_nested_project():
    candidate = Candidate(
        name="Ada",
        experience=[
            Experience(
                id="exp-1",
                company="Acme",
                position="Engineer",
                projects=[ExperienceProject(id="proj-1", name="Internal Tools")],
            )
        ],
    )
    projection = CVProjection(summary="...", experience=[])
    locked_item = Evidence(
        id="ev-1",
        text="Original.",
        experience_id="exp-1",
        experience_project_id="proj-1",
        locked=True,
        locked_text="Locked project bullet.",
    )

    result = splice_locked_bullets(projection, candidate, [locked_item])

    assert result.experience[0].bullets[0].project == "Internal Tools"


def test_splice_with_no_locked_evidence_is_a_no_op():
    candidate = Candidate(name="Ada")
    projection = CVProjection(summary="...", experience=[])

    result = splice_locked_bullets(projection, candidate, [])

    assert result.experience == []
