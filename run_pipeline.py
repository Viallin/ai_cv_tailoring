"""Manual end-to-end pipeline runner.

Lets you exercise the full prototype loop from the command line — useful for
debugging without the GUI (ui/main_window.py, Phase 6/8 in
docs/development_plan.md):

    resume text -> Candidate profile (saved) + Evidence[] (saved)
                -> JD text -> Requirements[]
                -> MatchResult (Matching stage: matches + Gaps, Phase 8)
                -> RewritePlan (Rewrite Planning stage, Phase 8)
                -> CVProjection (Bullet Rewriting stage, AI-tailored content only)
                -> CVProjection (Quality Recheck stage, trims self-explaining tails)
                -> AssembledCV (Candidate facts + CVProjection, merged in code)

The extracted Candidate profile is persisted via CandidateService so it's
available for manual editing afterwards (see app/candidate_service.py).
Since Phase 8.1, Candidate Profiles are no longer singular — this script
always uses one fixed profile id ("cli") via CandidateRegistry, separate
from whatever profiles exist from GUI use, so repeated runs of this script
update the same profile instead of piling up new ones.

The final AssembledCV merge (app/cv_assembler.py) never involves the LLM:
identity, contacts, education, dates, languages, and certifications come
straight from the Candidate Profile, not a generated response. See
docs/development_plan.md Phase 5 notes for why.

This script is a debugging/validation tool, not part of the application's
public interface. It intentionally duplicates the wiring in
app/services.py's build_services() (used by main.py and the GUI) rather
than importing from it, so it can be deleted later without touching
production code paths. It does share app/cv_markdown.py's rendering with
the GUI, though — Markdown formatting isn't "wiring," and having two
renderers drift apart would be a real bug risk.

Usage
-----
Place your resume in resume.txt (or resume.pdf) and the job description in
vacancy.txt (both in the project root, next to this script), then run:

    uv run python run_pipeline.py

Or point it at different files (.txt/.md/.pdf all work for --resume):

    uv run python run_pipeline.py --resume my_resume.pdf --vacancy job.txt

Or paste text interactively (no files needed):

    uv run python run_pipeline.py --interactive
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.candidate_registry import CandidateRegistry
from app.config import config
from app.cv_assembler import assemble_cv
from app.cv_markdown import render_full_markdown
from app.errors import AppError
from app.logging_setup import get_logger, setup_logging
from app.prompt_loader import PromptLoader
from app.resume_reader import read_resume_text
from app.use_cases import (
    BulletRewriteService,
    MatchingService,
    QualityRecheckService,
    ResumeIngestionService,
    RewritePlannerService,
    VacancyAnalysisService,
)
from contracts.schemas import (
    MatchRequest,
    QualityRecheckRequest,
    RewriteBulletsRequest,
    RewritePlanRequest,
)
from db.engine import get_engine
from providers.gemini_provider import GeminiProvider


def read_text_file(path: Path) -> str:
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)
    return path.read_text(encoding="utf-8")


def read_interactive(label: str) -> str:
    print(f"\nPaste your {label} below. Press Ctrl+Z then Enter (Windows) "
          f"or Ctrl+D (Mac/Linux) when done:\n")
    return sys.stdin.read()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the AI CV Builder pipeline end to end.")
    parser.add_argument("--resume", type=Path, default=Path("resume.txt"),
                         help="Path to the resume: .txt/.md (read as-is) or .pdf "
                              "(simple text extraction, no OCR).")
    parser.add_argument("--vacancy", type=Path, default=Path("vacancy.txt"),
                         help="Path to a text file with the job description.")
    parser.add_argument("--interactive", action="store_true",
                         help="Paste resume and vacancy text directly instead of using files.")
    parser.add_argument("--out", type=Path, default=Path("cv_output.md"),
                         help="Where to save the generated CV as Markdown.")
    args = parser.parse_args()

    setup_logging()
    logger = get_logger(__name__)

    if args.interactive:
        resume_text = read_interactive("resume")
        vacancy_text = read_interactive("job description")
    else:
        if not args.resume.exists():
            print(f"Error: file not found: {args.resume}", file=sys.stderr)
            sys.exit(1)
        try:
            resume_text = read_resume_text(args.resume)
        except AppError as exc:
            print(f"Error reading resume: {exc}", file=sys.stderr)
            sys.exit(1)
        vacancy_text = read_text_file(args.vacancy)

    provider = GeminiProvider(
        api_key=config.gemini_api_key,
        model=config.llm_model,
        max_retries=config.llm_max_retries,
        retry_base_delay_seconds=config.llm_retry_base_delay_seconds,
    )
    prompt_loader = PromptLoader(prompts_dir=config.prompts_dir)

    resume_service = ResumeIngestionService(provider, prompt_loader)
    vacancy_service = VacancyAnalysisService(provider, prompt_loader)
    matching_service = MatchingService(provider, prompt_loader)
    rewrite_planner_service = RewritePlannerService(provider, prompt_loader)
    bullet_rewrite_service = BulletRewriteService(provider, prompt_loader)
    quality_recheck_service = QualityRecheckService(provider, prompt_loader)
    engine = get_engine(config.database_url)
    candidate_service = CandidateRegistry(engine=engine).service_for("cli")

    try:
        print("\n[1/6] Parsing resume (candidate profile + Evidence)...")
        ingest_response = resume_service.ingest(resume_text)
        print(f"  -> Candidate: {ingest_response.candidate.name} "
              f"({len(ingest_response.candidate.contacts)} contacts, "
              f"{len(ingest_response.candidate.experience)} experience, "
              f"{len(ingest_response.candidate.education)} education, "
              f"{len(ingest_response.candidate.skills)} skills, "
              f"{len(ingest_response.candidate.languages)} languages, "
              f"{len(ingest_response.candidate.certifications)} certifications, "
              f"{len(ingest_response.candidate.projects)} projects, "
              f"summary: {'yes' if ingest_response.candidate.summary else 'no'})")
        print(f"  -> Found {len(ingest_response.evidence)} Evidence items.")
        for ev in ingest_response.evidence:
            print(f"     - [{ev.id}] {ev.text}")

        existed_before = candidate_service.get() is not None
        candidate_service.replace(ingest_response.candidate, evidence=ingest_response.evidence)
        action = "Updated" if existed_before else "Saved"
        print(f"  -> {action} candidate profile + Evidence in {config.data_dir}/")

        print("\n[2/6] Analyzing job description...")
        vacancy = vacancy_service.analyze(vacancy_text)
        if vacancy.title or vacancy.company:
            print(f"  -> Role: {vacancy.title or '(title not found)'} "
                  f"@ {vacancy.company or '(company not found)'}")
        print(f"  -> Found {len(vacancy.requirements)} requirements, "
              f"{len(vacancy.keywords)} keywords.")
        for req in vacancy.requirements:
            tags = f" [{', '.join(req.keywords)}]" if req.keywords else ""
            print(f"     - {req.text}{tags}")
        print(f"     Keywords: {', '.join(vacancy.keywords)}")

        print("\n[3/6] Matching resume against job requirements...")
        match_response = matching_service.match(
            MatchRequest(
                experience=ingest_response.candidate.experience,
                evidence=ingest_response.evidence,
                requirements=vacancy.requirements,
            )
        )
        match_result = match_response.match_result
        print(f"  -> {len(match_result.matches)} requirement(s) matched, "
              f"{len(match_result.gaps)} gap(s) found.")
        for gap in match_result.gaps:
            print(f"     - GAP: {gap.description} (for: {gap.requirement_text})")
        if match_result.missing_keywords:
            print(f"     Missing keywords: {', '.join(match_result.missing_keywords)}")

        print("\n[4/6] Planning bullet rewrites...")
        plan_response = rewrite_planner_service.plan(
            RewritePlanRequest(
                experience=ingest_response.candidate.experience,
                evidence=ingest_response.evidence,
                requirements=vacancy.requirements,
                match_result=match_result,
            )
        )
        plan = plan_response.plan
        by_action: dict[str, int] = {}
        for act in plan.actions:
            by_action[act.action] = by_action.get(act.action, 0) + 1
        print(f"  -> {len(plan.actions)} action(s) planned: "
              + ", ".join(f"{count} {name}" for name, count in by_action.items()))

        print("\n[5/7] Rewriting bullets...")
        rewrite_response = bullet_rewrite_service.rewrite(
            RewriteBulletsRequest(
                experience=ingest_response.candidate.experience,
                evidence=ingest_response.evidence,
                requirements=vacancy.requirements,
                plan=plan,
                candidate_summary=ingest_response.candidate.summary,
                candidate_headline=ingest_response.candidate.headline,
                vacancy_title=vacancy.title,
            )
        )

        print("\n[6/7] Quality recheck (trimming self-explaining tails)...")
        recheck_response = quality_recheck_service.recheck(
            QualityRecheckRequest(cv=rewrite_response.cv, requirements=vacancy.requirements)
        )
        # 07_bullet_quality_recheck_v1.md doesn't know about `headline` (see
        # app/pipeline.py's own recheck_cv comment) — re-attach it here too.
        recheck_cv = recheck_response.cv.model_copy(update={"headline": rewrite_response.cv.headline})
        assembled_cv = assemble_cv(ingest_response.candidate, recheck_cv)
    except AppError as exc:
        logger.error("Pipeline failed: %s", exc)
        print(f"\nPipeline failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print("\n[7/7] Writing CV to file...")
    markdown = render_full_markdown(assembled_cv)
    args.out.write_text(markdown, encoding="utf-8")

    print("\n--- Generated CV ---\n")
    print(markdown)
    print(f"\nSaved to {args.out.resolve()}")


if __name__ == "__main__":
    main()
