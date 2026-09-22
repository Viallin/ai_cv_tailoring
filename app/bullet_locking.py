"""Phase 19: locked Evidence bypasses the LLM entirely and reuses its
verbatim text for every vacancy — the direct, cheap answer to the cost/
latency question behind bullet-variant reuse (falls out of Phase 17's
provenance data, no embeddings/similarity infrastructure needed).

Two pure functions, no LLM call — same shape as app/bullet_provenance.py:
`partition_locked_evidence` (called by app/pipeline.py before the Rewrite
Planning/Bullet Rewriting calls, to shrink what's actually sent to the LLM)
and `splice_locked_bullets` (called after Bullet Rewriting, to put each
locked item's bullet back into the CVProjection the LLM never saw it in).
"""

from __future__ import annotations

from domain.models import Candidate, CVProjection, Evidence, TailoredBullet, TailoredExperience


def partition_locked_evidence(evidence: list[Evidence]) -> tuple[list[Evidence], list[Evidence]]:
    """Splits `evidence` into (unlocked, locked). An Evidence item with
    `locked=True` but no `experience_id` can't back a bullet at all (no
    role to attach it to) — treated as unlocked here so it still goes
    through Matching/Planning/Rewriting normally, same "no experience_id ->
    not eligible for a bullet in the first place" precedent
    app/bullet_provenance.py already established.
    """
    unlocked: list[Evidence] = []
    locked: list[Evidence] = []
    for item in evidence:
        if item.locked and item.experience_id is not None:
            locked.append(item)
        else:
            unlocked.append(item)
    return unlocked, locked


def _project_name(candidate: Candidate, experience_id: str, experience_project_id: str | None) -> str | None:
    if experience_project_id is None:
        return None
    experience = next((e for e in candidate.experience if e.id == experience_id), None)
    if experience is None:
        return None
    project = next((p for p in experience.projects if p.id == experience_project_id), None)
    return project.name if project else None


def splice_locked_bullets(
    projection: CVProjection,
    candidate: Candidate,
    locked_evidence: list[Evidence],
    priority_order: list[str] | None = None,
) -> CVProjection:
    """Appends one TailoredBullet per locked item into the matching
    TailoredExperience — creating one if the Bullet Rewriting call (which
    never saw this evidence, see partition_locked_evidence) didn't produce
    one for that role at all. Without this, a role whose *entire* evidence
    set is locked would come back from that call with no TailoredExperience
    for it, and app/cv_assembler.py:assemble_cv's `if tailored is None:
    continue` would silently drop it from the assembled CV — the one real
    bug this function exists to prevent, found by reading that assembler,
    not observed in production.

    `priority_order` (RewritePlan.priority_order — "Evidence ids, most
    important first") re-sorts each entry's *whole* bullet list, locked and
    LLM-produced together, after splicing — otherwise a locked bullet would
    always land dead last regardless of how important it actually is,
    which is backwards: locking is something a person does specifically to
    a wording they've already approved, i.e. usually their strongest
    content, not their weakest. Only meaningful because
    RewritePlanRequest.evidence gets the *full*, unpartitioned evidence
    list (app/pipeline.py::run_cv_generation) even though
    RewriteBulletsRequest doesn't — Planning is cheap enough that seeing
    locked evidence costs little, and it's the only stage that ever
    produces a priority ranking at all. A stable sort, so items missing
    from `priority_order` (shouldn't normally happen — every Evidence item
    gets ranked) keep their prior relative order rather than being
    reshuffled arbitrarily; this also preserves 05_rewrite_bullets_v1.md's
    own project-name interleaving (frontend/src/lib/structuredDocument.ts's
    buildExperienceBullets groups by project regardless of raw list
    position, so re-sorting the flat list here never breaks that grouping).
    """
    rank = {evidence_id: index for index, evidence_id in enumerate(priority_order or [])}
    unranked = len(rank)

    by_experience_id = {entry.experience_id: entry for entry in projection.experience}
    touched_experience_ids: set[str] = set()

    for item in locked_evidence:
        bullet = TailoredBullet(
            text=item.locked_text or item.text,
            project=_project_name(candidate, item.experience_id, item.experience_project_id),
            evidence_id=item.id,
        )
        entry = by_experience_id.get(item.experience_id)
        if entry is None:
            entry = TailoredExperience(experience_id=item.experience_id, bullets=[])
            by_experience_id[item.experience_id] = entry
            projection.experience.append(entry)
        entry.bullets.append(bullet)
        touched_experience_ids.add(item.experience_id)

    for experience_id in touched_experience_ids:
        entry = by_experience_id[experience_id]
        entry.bullets.sort(key=lambda b: rank.get(b.evidence_id, unranked))

    return projection
