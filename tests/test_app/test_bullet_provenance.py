from app.bullet_provenance import build_report
from domain.models import (
    AssembledCV,
    AssembledExperienceEntry,
    Evidence,
    RewriteAction,
    RewritePlan,
    TailoredBullet,
)


def make_cv(bullets: list[TailoredBullet]) -> AssembledCV:
    return AssembledCV(
        name="Ada Lovelace",
        summary="A summary.",
        experience=[
            AssembledExperienceEntry(experience_id="exp-1", position="Lead Engineer", bullets=bullets)
        ],
    )


def test_build_report_joins_evidence_and_plan_action_for_a_rewritten_bullet():
    evidence = [Evidence(id="ev-1", text="Wrote an algorithm for the Analytical Engine.")]
    plan = RewritePlan(
        actions=[
            RewriteAction(
                evidence_id="ev-1",
                action="rewrite",
                reason="Emphasize the algorithm-design angle for this role.",
            )
        ]
    )
    cv = make_cv([TailoredBullet(text="Designed the first published algorithm.", evidence_id="ev-1")])

    report = build_report(evidence, plan, cv)

    assert len(report.bullets) == 1
    provenance = report.bullets[0]
    assert provenance.evidence_id == "ev-1"
    assert provenance.original_text == "Wrote an algorithm for the Analytical Engine."
    assert provenance.rewritten_text == "Designed the first published algorithm."
    assert provenance.action == "rewrite"
    assert provenance.rationale == "Emphasize the algorithm-design angle for this role."
    assert report.unused_evidence == []


def test_build_report_rationale_includes_new_angle_and_target_keywords_when_present():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(
        actions=[
            RewriteAction(
                evidence_id="ev-1",
                action="rewrite",
                reason="Tighten the wording.",
                target_keywords=["systems design"],
                new_angle="Frame as a leadership accomplishment.",
            )
        ]
    )
    cv = make_cv([TailoredBullet(text="Rewritten text.", evidence_id="ev-1")])

    report = build_report(evidence, plan, cv)

    rationale = report.bullets[0].rationale
    assert rationale is not None
    assert rationale.startswith("Tighten the wording.")
    assert "new angle: Frame as a leadership accomplishment." in rationale
    assert "target keywords: systems design" in rationale


def test_build_report_defaults_to_keep_with_no_rationale_when_plan_has_no_action_for_the_bullet():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[])  # no RewriteAction for ev-1 at all
    cv = make_cv([TailoredBullet(text="Original text.", evidence_id="ev-1")])

    report = build_report(evidence, plan, cv)

    assert report.bullets[0].action == "keep"
    assert report.bullets[0].rationale is None


def test_build_report_skips_a_bullet_with_no_evidence_id():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[RewriteAction(evidence_id="ev-1", action="keep", reason="Fine as-is.")])
    cv = make_cv([TailoredBullet(text="Some bullet with no link back.", evidence_id=None)])

    report = build_report(evidence, plan, cv)

    assert report.bullets == []
    # Not "used" either, since it was never actually joined to this Evidence item.
    assert report.unused_evidence == evidence


def test_build_report_skips_a_bullet_whose_evidence_id_is_stale_or_hallucinated():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[])
    cv = make_cv([TailoredBullet(text="Some bullet.", evidence_id="ev-does-not-exist")])

    report = build_report(evidence, plan, cv)

    assert report.bullets == []
    assert report.unused_evidence == evidence


def test_build_report_surfaces_evidence_never_referenced_by_any_bullet():
    # ev-1 made it into the CV; ev-2 was plan-removed (no bullet at all);
    # ev-3 has no experience_id, so it was never even eligible for a bullet.
    evidence = [
        Evidence(id="ev-1", text="Used evidence."),
        Evidence(id="ev-2", text="Removed by the plan."),
        Evidence(id="ev-3", text="Not tied to any role."),
    ]
    plan = RewritePlan(
        actions=[
            RewriteAction(evidence_id="ev-1", action="keep", reason="Solid as-is."),
            RewriteAction(evidence_id="ev-2", action="remove", reason="Not relevant to this vacancy."),
        ]
    )
    cv = make_cv([TailoredBullet(text="Used evidence.", evidence_id="ev-1")])

    report = build_report(evidence, plan, cv)

    assert [p.evidence_id for p in report.bullets] == ["ev-1"]
    assert [item.id for item in report.unused_evidence] == ["ev-2", "ev-3"]


def test_build_report_handles_multiple_experience_entries():
    evidence = [Evidence(id="ev-1", text="Text one."), Evidence(id="ev-2", text="Text two.")]
    plan = RewritePlan(
        actions=[
            RewriteAction(evidence_id="ev-1", action="keep", reason="Reason one."),
            RewriteAction(evidence_id="ev-2", action="enhance", reason="Reason two."),
        ]
    )
    cv = AssembledCV(
        name="Ada Lovelace",
        summary="A summary.",
        experience=[
            AssembledExperienceEntry(
                experience_id="exp-1",
                position="Lead Engineer",
                bullets=[TailoredBullet(text="Text one.", evidence_id="ev-1")],
            ),
            AssembledExperienceEntry(
                experience_id="exp-2",
                position="Fellow",
                bullets=[TailoredBullet(text="Text two, enhanced.", evidence_id="ev-2")],
            ),
        ],
    )

    report = build_report(evidence, plan, cv)

    assert {p.evidence_id: p.action for p in report.bullets} == {"ev-1": "keep", "ev-2": "enhance"}
    assert report.unused_evidence == []


def test_build_report_reports_summary_provenance_when_genuinely_rewritten():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[])
    cv = make_cv([])  # make_cv's summary is always "A summary."

    report = build_report(evidence, plan, cv, candidate_summary="The candidate's own original summary.")

    assert report.summary is not None
    assert report.summary.original_text == "The candidate's own original summary."
    assert report.summary.rewritten_text == "A summary."


def test_build_report_omits_summary_provenance_when_no_candidate_summary_was_given():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[])
    cv = make_cv([])

    report = build_report(evidence, plan, cv, candidate_summary=None)

    assert report.summary is None


def test_build_report_omits_summary_provenance_when_blank_candidate_summary_was_given():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[])
    cv = make_cv([])

    report = build_report(evidence, plan, cv, candidate_summary="   ")

    assert report.summary is None


def test_build_report_omits_summary_provenance_when_tailored_summary_matches_the_original():
    evidence = [Evidence(id="ev-1", text="Original text.")]
    plan = RewritePlan(actions=[])
    cv = make_cv([])  # summary is "A summary."

    report = build_report(evidence, plan, cv, candidate_summary="A summary.")

    assert report.summary is None
