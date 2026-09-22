"""Builds a BulletProvenanceReport (Phase 17) from data the pipeline already
has by the time run_cv_generation finishes — no new LLM call.

`original_text` (Evidence.text, looked up by id) and `rationale` (the
Rewrite Planning stage's own RewriteAction.reason/target_keywords/new_angle,
keyed by the same evidence_id) are both already known once a bullet's
evidence_id is known; only TailoredBullet.evidence_id itself is new LLM
output (see domain.models.TailoredBullet's docstring). This mirrors
app/cv_assembler.py's "compute deterministically from existing data rather
than ask the LLM to restate it" precedent.
"""

from __future__ import annotations

from domain.models import (
    AssembledCV,
    BulletProvenance,
    BulletProvenanceReport,
    Evidence,
    RewriteAction,
    RewritePlan,
    SummaryProvenance,
)


def _build_rationale(action: RewriteAction) -> str:
    # Mirrors app/pipeline.py's _format_certification convention: join
    # present optional details onto the primary text with ", ".
    details = []
    if action.new_angle:
        details.append(f"new angle: {action.new_angle}")
    if action.target_keywords:
        details.append(f"target keywords: {', '.join(action.target_keywords)}")
    return action.reason + (f" ({'; '.join(details)})" if details else "")


def build_report(
    evidence: list[Evidence], plan: RewritePlan, cv: AssembledCV, candidate_summary: str | None = None
) -> BulletProvenanceReport:
    """Join `evidence`/`plan.actions` against every bullet already in `cv`
    (the just-assembled AssembledCV) to produce one BulletProvenance per
    bullet, plus the Evidence items no bullet ever referenced.

    A bullet with no `evidence_id` (the LLM omitted it despite the prompt
    rule) or one that doesn't match any known Evidence id (stale/
    hallucinated) is simply skipped, not raised on — same "ignore, harmless"
    precedent as cv_assembler.py's _rank_by_category for an unrecognized
    name. Evidence with no RewriteAction in the plan falls back to
    `action="keep"` with no rationale, rather than failing the whole report
    — normally shouldn't happen (every Evidence item gets a plan action),
    except for a locked item (Phase 19), which is *always* missing one by
    design: app/bullet_locking.py excludes locked Evidence from Rewrite
    Planning entirely, and `BulletProvenance.locked=True` (set below from
    `source.locked`) is what tells the two cases apart.

    `candidate_summary` is `Candidate.summary` as it stood
    before this generation — passed in separately, unlike a bullet's
    `original_text`, because it isn't looked up from `evidence`/`plan` by
    an id already present on the tailored output. Reported as
    `SummaryProvenance` only when there's a genuine edit to show:
    `None`/blank means the candidate had nothing to compare against (the
    Rewrite Bullets stage wrote the summary from scratch either way, per
    05_rewrite_bullets_v1.md, so that's not itself unusual), and an
    unchanged result means there's nothing to revert to that isn't already
    showing.
    """
    evidence_by_id = {item.id: item for item in evidence}
    actions_by_id = {action.evidence_id: action for action in plan.actions}

    provenance: list[BulletProvenance] = []
    used_ids: set[str] = set()
    for entry in cv.experience:
        for bullet in entry.bullets:
            if bullet.evidence_id is None:
                continue
            source = evidence_by_id.get(bullet.evidence_id)
            if source is None:
                continue
            used_ids.add(bullet.evidence_id)
            action = actions_by_id.get(bullet.evidence_id)
            provenance.append(
                BulletProvenance(
                    evidence_id=bullet.evidence_id,
                    original_text=source.text,
                    rewritten_text=bullet.text,
                    action=action.action if action else "keep",
                    rationale=_build_rationale(action) if action else None,
                    locked=source.locked,
                )
            )

    unused_evidence = [item for item in evidence if item.id not in used_ids]

    summary_provenance = None
    if candidate_summary and candidate_summary.strip() and candidate_summary.strip() != cv.summary.strip():
        summary_provenance = SummaryProvenance(original_text=candidate_summary, rewritten_text=cv.summary)

    return BulletProvenanceReport(bullets=provenance, unused_evidence=unused_evidence, summary=summary_provenance)
