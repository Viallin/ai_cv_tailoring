# Archived prompt drafts

Files here are **not used by any code** — `app/prompt_loader.py` is only ever
pointed at files directly under `prompts/`, and `app/use_cases.py` only
references the versioned files (`01_cv_parser_v1.md`, `02_jd_parser_v1.md`,
`03_cv_jd_matcher_v1.md`, `04_rewrite_planner_v1.md`, `05_rewrite_bullets_v1.md`).

They're kept for reference/history, not as a second "real" prompt:

* `02_jd_parser.md` — an early draft of the job-description parser, from
  before the schema settled. Its output shape (`role`, `seniority_signals`,
  `required_skills`, `nice_to_have`, `keywords_for_ats`, `product_domains`,
  `success_metrics`) does **not** match `contracts.schemas.
  AnalyzeVacancyResponse` and never has — do not wire it up as-is.
  Superseded by `prompts/02_jd_parser_v1.md`.
* `03_cv_jd_matcher.md` — an early sketch of the Phase 8 Matching stage
  (`{"matches": [...], "missing_keywords": [...], "strongest_aligned_experiences":
  [...], "weak_areas": [...]}`). Doesn't match `contracts.schemas.
  MatchResponse`/`domain.models.MatchResult` — do not wire it up as-is.
  Superseded by `prompts/03_cv_jd_matcher_v1.md`.
* `03_cv_builder_v1.md` — Phase 5-7's single collapsed tailoring call
  (Candidate + Evidence + Requirements -> `CVProjection` in one LLM call,
  with no visible matching/gap step). Retired once Phase 8 replaced it with
  three real stages: `03_cv_jd_matcher_v1.md` (Matching) ->
  `04_rewrite_planner_v1.md` (Rewrite Planning) ->
  `05_rewrite_bullets_v1.md` (Bullet Rewriting, which now produces the
  `CVProjection`). Its contract (`contracts.schemas.BuildCVRequest`/
  `BuildCVResponse`) no longer exists in the codebase — do not wire it up
  as-is.
* `04_rewrite_planner.md` / `05_rewrite_bullets.md` — early sketches of the
  two stages above. Their output shapes (`rewrite_actions` with a `"merge"`
  action; `rewritten_bullet`/`keywords_included`/`change_summary` per call)
  don't match `contracts.schemas.RewritePlanResponse`/
  `RewriteBulletsResponse` — do not wire them up as-is. Superseded by
  `prompts/04_rewrite_planner_v1.md`/`prompts/05_rewrite_bullets_v1.md`.

If a file here turns out to still be useful, promote it back into
`prompts/` under the `NN_name_vX.md` convention (see
`docs/architecture.md` §6) and update `app/use_cases.py` to point at it —
don't leave two same-numbered files with different schemas live at once.
