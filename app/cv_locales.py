"""Section-title localization (Version 4, Phase 4.3).

Mirrors the codebase's existing dual-implementation convention rather
than introducing new codegen infrastructure for a ~13-key, two-locale
table: `frontend/src/lib/sections.ts` hand-mirrors this file exactly,
the same way it already hand-mirrored the old single-locale
`app.cv_markdown.SECTION_TITLES` (see that file's own comment, kept in
sync by hand since there's no schema for a plain constant the way there
is for a request/response shape openapi-typescript picks up).

`section_titles_for()` falls back to English for any language it doesn't
recognize — deliberately not a hard error: `domain.models.Candidate.language`
is a plain, open `str` (the LLM can detect/a user can type any ISO code),
while this table only needs to cover whatever languages the product
actually supports headers for so far. An unsupported language still gets
a fully-rendered CV, just with English headers, rather than failing to
export at all.
"""

from __future__ import annotations

# Order matters here: this is both the section order for the full document
# and the canonical list of valid section keys — see
# app/cv_markdown.py:SECTION_TITLES's own docstring for why "contacts" is
# first. Keep this key set and order identical across every locale below;
# a locale dict missing a key would KeyError wherever a renderer looks it
# up for that language.
SECTION_TITLES_EN: dict[str, str] = {
    "contacts": "Contacts",
    "summary": "Summary",
    "projects": "Key Projects",
    "portfolio_links": "Portfolio",
    "publications": "Publications & Talks",
    "experience": "Experience",
    "volunteer_experience": "Volunteer Experience",
    "education": "Education",
    "skills": "Skills",
    "technologies": "Tools & Technologies",
    "languages": "Languages",
    "certifications": "Certifications",
    "awards": "Awards & Honors",
}

# First target language (Version 4, Phase 4.2/4.3) — author reviews/
# iterates on these after testing personally, per the labels following
# native-Russian-CV convention rather than a literal word-for-word
# translation (e.g. "О себе" for Summary, not a literal "Резюме").
SECTION_TITLES_RU: dict[str, str] = {
    "contacts": "Контакты",
    "summary": "О себе",
    "projects": "Ключевые проекты",
    "portfolio_links": "Портфолио",
    "publications": "Публикации и выступления",
    "experience": "Опыт работы",
    "volunteer_experience": "Волонтёрский опыт",
    "education": "Образование",
    "skills": "Навыки",
    "technologies": "Инструменты и технологии",
    "languages": "Языки",
    "certifications": "Сертификаты",
    "awards": "Награды",
}

SECTION_TITLES_BY_LOCALE: dict[str, dict[str, str]] = {
    "en": SECTION_TITLES_EN,
    "ru": SECTION_TITLES_RU,
}


def section_titles_for(language: str) -> dict[str, str]:
    return SECTION_TITLES_BY_LOCALE.get(language, SECTION_TITLES_EN)
