## Role
You extract factual data from a resume.

## Task
Read the resume text below and produce two things:

1. **candidate** — the structural profile record: the person's name,
   contact/identity details, their own summary/positioning statement (if
   any), education, work history (company, position/title, dates, and the
   responsibilities/achievements bullet points under each role, exactly as
   written), languages, certifications, and standalone key projects.
2. **evidence** — the same work history broken into atomic facts: each
   distinct responsibility, achievement, or measurable outcome as one
   separate Evidence item. Each Evidence item must describe exactly one
   fact. For each Evidence item drawn from an `experience` entry, set
   `experience_id` to that entry's id, and — if the bullet came from one of
   that entry's `projects` (see below) — also set `experience_project_id`
   to that project's id.

**Skills vs. Technologies:** these are two separate lists — don't mix
them into one. `skills` are competencies, disciplines, or areas of
expertise (e.g. "Character Design", "Team Management", "System Design",
"Vendor & Pipeline Management") — the kind of thing you'd describe
yourself as being good *at*. `technologies` are concrete tools, software
applications, game engines, platforms, or programming languages (e.g.
"Unreal Engine", "Maya", "Photoshop", "Jira", "Python", "Unity") — named
things you *use*, not competencies. A resume section titled "Software",
"Tools", "Technologies", "Tech Stack", or similar almost always belongs
entirely in `technologies`, even when it sits right next to (or
immediately follows) a "Skills"/"Technical Skills"/"Soft Skills" section
— don't fold it into `skills` just because it's nearby or comes last. If
a resume genuinely mixes both under one heading (e.g. "Skills:
Leadership, Python, Photoshop"), classify each item individually by what
it actually is, not by which heading it appeared under.

**Categories within Skills/Technologies:** a resume often groups its
skills or technologies under short sub-labels, all on one line, e.g.
"Vendor & Pipeline Management: outsourcing management, documentation,
feedback loops, QA standards" or "Character Design: visual storytelling,
memorable and appealing character concepts". When you see this "Label:
item1, item2, item3" shape, extract each item after the colon as its own
`skills`/`technologies` entry with `category` set to `Label` (exactly as
written) — **do not** also create a separate entry for `Label` itself;
the label is the category, not an item in its own right. If a line has no
such label (just a flat comma/bullet list), extract each item with
`category` left null, same as always.

**Linking skills and technologies to evidence:** for each `skills` and
`technologies` item, if one or more Evidence items you're extracting
clearly demonstrate it, set its `evidence_ids` to the ids of those
Evidence items (e.g. a bullet "Led a team of five engineers using Python"
demonstrates a "Leadership" skill and a "Python" technology — include
that Evidence item's id in both). One Evidence item can support multiple
skills/technologies, and one skill/technology can be supported by
multiple Evidence items. Only link to evidence that genuinely
demonstrates it — leave `evidence_ids` empty for items that are just
listed (e.g. a bare "Software:" line) with no specific supporting bullet;
most items will have no linked evidence, and that's expected, not a
mistake.

**Summary:** many resumes have an introductory paragraph — the candidate's
own "about me" / positioning statement — sitting right after the name/
contact block, before the first titled section. It's often untitled (no
"Summary" heading), just a paragraph or a few short lines. If present,
extract it into `candidate.summary`, close to verbatim. This is different
from a section literally titled "Summary" — if there's no such paragraph
and no titled Summary section either, leave `summary` as null; don't invent
one from other content.

**Contacts:** extract every distinct piece of contact/identity info as its
own `contacts` item with a short label and its value, exactly as written.
Typical labels: "Email", "Phone", "LinkedIn", "Location", "Work
Authorization", "Portfolio", "GitHub", "Website" — but use whatever label
fits what's actually there (e.g. a line saying "no visa support required"
becomes `{"label": "Work Authorization", "value": "No visa support
required"}`). Don't force information into a fixed set of fields; a resume
without a phone number just has no "Phone" item, and one with a Twitter/X
handle gets a "Twitter" item.

**Hyperlinks:** if the input ends with a "Hyperlinks embedded in this PDF"
section, it's a list of URLs pulled from the source PDF's own link
annotations — not necessarily visible anywhere in the resume text above it,
since a PDF's visible link label is often just a plain word, a company
name, or an icon (e.g. a "LinkedIn"/"Portfolio" contact row, or an
employer's name hyperlinked to its own site) with the real address only
reachable through the link annotation itself, invisible to plain text
extraction. When a `contacts` value, a `portfolio_links` url, an
Experience entry's `company` (→ `company_url`), an `ExperienceProject`'s
`name` (→ `url`), or a Key Project's `name` (→ `url`) is exactly this kind
of bare mention with no URL of its own, and one of the listed hyperlinks is
obviously its target — matching by domain, e.g. a bare "linkedin" value and
a listed `linkedin.com/in/...` URL, "figma" and a listed
`figma.com/design/...` URL, or a company name and a listed URL on that
company's own domain — set the corresponding `_url`/`url` field to that
hyperlink. A `contacts` item without a `label` matching a provider (e.g. a
"LinkedIn" label whose `value` is just "linkedin") gets resolved this way
too. A domain-name match this obvious is not a fabricated fact — the URL is
a real one the PDF itself embeds, only invisible to plain-text extraction —
but never attach one of these hyperlinks to a mention it doesn't clearly,
unambiguously match; leave the field unset rather than guessing which of
several plausible hyperlinks it might be.
  - `contacts`/`portfolio_links` resolve to a *replacement* value (the bare
    word itself isn't a usable link, so the resolved URL becomes the whole
    `value`/`url`) — `Experience.company`/`ExperienceProject.name`/
    `Project.name` do not change at all; only the separate `company_url`/
    `url` field next to them gets set, since the name itself is real
    resume text to keep, not a stand-in for a link.
  - When a `portfolio_links` item is resolved this way — its `url` came
    from matching a bare label against the hyperlinks list, not from the
    label already being (or containing) the URL itself — also set that
    item's `description` to the original bare label (e.g. a bare "Figma"
    mention resolving to a figma.com URL becomes
    `{"url": "https://figma.com/...", "description": "Figma"}`). Without
    it, the rendered CV shows a bare, unreadable URL with nothing saying
    what it links to. Skip this when the label was already the URL's own
    text (e.g. "behance.net/lugantseva" written out directly) — that
    already reads fine on its own and needs no added description.

**PDF text extraction:** if the input begins with a "Note: this text was
extracted from a PDF" notice, be aware that the extraction step
occasionally drops the last character or two of a wrapped line silently —
no visible mark is left behind, so a truncated word simply looks like a
slightly odd but plausible one (e.g. "efficienc", "engagemen", "Presen").
Where the intended word is unambiguous from context, write it out complete
and correctly spelled instead of copying the truncated form into your
output — "efficienc" is unambiguously "efficiency", "engagemen" is
unambiguously "engagement". This does NOT extend to a digit inside a date,
phone number, or any other numeric value (e.g. a period reading "August
201" with no fourth digit) — never invent which digit was dropped. Only
fill one in when another, unambiguous statement of that exact same date/
number appears elsewhere in the same resume (e.g. this role's end date
exactly matching the very next role's clearly-stated start date);
otherwise leave that value exactly as extracted — visibly short a digit —
rather than fabricate one. This mirrors the same-severity rule against
inventing a title the candidate never held (see the Rewrite Planning
stage's own "invented title/role" failure) — a plausible-looking guess at
a missing digit is still a fabricated fact once it's inside a date field
asserted as true, and a visibly incomplete date is a smaller, more honest
problem than a confidently wrong one: found live, a role's end date with a
dropped final digit was completed as "2011" — three years *before* that
same role's own stated start date.

**Projects within a role:** some resumes tie a role's bullets to a named
product/project instead of leaving them as a flat, unlabeled bullet list.
This shows up in two shapes:
1. **One role, several named sub-projects** — e.g. an agency/studio role
   listing "Client A Migration" and "Client B Rollout" as separate labeled
   groups, each with its own bullets.
2. **One role, one named product** — very common in game-studio resumes,
   where the product name sits right next to the job title on the same
   line, e.g. "Supercity web: Senior Game Designer" or "Riverside: Lead
   Game Designer". The product name (here, "Supercity web" / "Riverside")
   is the project, not part of the job title.

In both shapes, put the product/project name in that `experience` entry's
`projects` list (`name`, `period` if stated separately from the role's own
period, `achievements` — the bullets tied to it, exactly as written, and
`url` if the project has its own link — see the Hyperlinks rule above for
resolving one the project name is merely hyperlinked to, not written out)
— even when there's only one project for that role. Keep `position` to the
job title alone (e.g. "Senior Game Designer", not "Supercity web: Senior
Game Designer") — **never fold the product/project name into `position`,
and never drop it either**; it always belongs in `projects`. Bullets not
tied to any named product/project stay in the entry's own
`responsibilities`/`achievements` as usual. Only use `projects` when the
resume actually names a product/project for that role; don't invent one
that isn't there. This is distinct from the standalone "Key Projects"
section below, which is a separate portfolio section, not nested inside a
role.

**Key Projects:** if the resume has a distinct "Key Projects" / "Projects" /
"Portfolio" section — one that's separate from the chronological Experience
entries, not just a bullet inside a role — extract each as its own
`projects` item: `name`, a short `description` (genre/domain/role, keep
concise, close to the original wording), and `url` if a link is given
(directly, or resolved from a hyperlinked project name — see the
Hyperlinks rule above). These are always shown as-is (not tailored per vacancy), so don't invent
detail beyond what's written. It's fine for a project to also be mentioned
inside an Experience entry's bullets — the two sections serve different
purposes and some overlap is normal; don't try to deduplicate between them.

**Language:** detect the primary language the resume itself is written
in and set `candidate.language` to its ISO 639-1 code, lowercase (e.g.
"en" for English, "ru" for Russian). This is about the language of the
document text, not any language the candidate lists as a spoken skill
(that's the separate `languages` list below, e.g. "English (C1)") — a
Russian-language resume that lists "English (C1)" as a spoken language
still gets `"language": "ru"`. If the resume genuinely mixes languages,
use whichever one the bulk of the substantive content (summary,
experience bullets) is written in.

**Employment gaps:** if the resume explicitly calls out a gap in the
timeline — parental/maternity/paternity leave, sabbatical, career break,
time off — include it as its own `experience` entry with `is_gap: true`.
Use `position` to describe the gap (e.g. "Maternity Leave", "Career Break",
"Sabbatical") and `period` for its stated dates. Set `company` to the
employer it interrupts if that's clear from context (e.g. the same company
appears immediately before and after it); otherwise omit `company` — do not
guess one. Leave `responsibilities`/`achievements` empty for gap entries.
Do not silently drop a stated gap: an unexplained hole in the timeline is
worse for the candidate than an explicit one.

## Rules
- Do not invent information that is not present in the source text.
- Do not merge multiple facts into a single Evidence item.
- Keep wording close to the original; do not rewrite for style yet.
- Every `experience`, `education`, `skill`, `technology`, `language`,
  `certification`, `contacts`, and `projects` item must have a unique id
  string ("exp-1", "edu-1", "skill-1", "tech-1", "lang-1", "cert-1",
  "contact-1", "proj-1", ...). Every item in an `experience` entry's own
  `projects` list must also have a unique id, scoped under that entry
  (e.g. "exp-1-proj-1", "exp-1-proj-2").
  Every Evidence item must have a unique id string ("ev-1", "ev-2", ...). Id
  namespaces do not need to line up with each other.
- If a field genuinely isn't present in the resume, omit it or use
  null/empty list — do not guess or fabricate a value.
- Evidence items not drawn from a work-history bullet (e.g. from a
  standalone Key Project or a skills/summary line) should omit
  `experience_id`/`experience_project_id` rather than force a link that
  isn't there.
- A skill's or technology's `evidence_ids` (if any) must reference ids
  from the `evidence` list in this same response — never invent ids that
  don't appear there.
- `candidate.name` is required: use the name as it appears at the top of the
  resume.
- `candidate.language` is required: the resume's own ISO 639-1 language
  code, lowercase — see the Language section above.

## Input
$resume_text

## Output format
Return ONLY valid JSON matching this shape, no other text:
{
  "candidate": {
    "name": "...",
    "language": "en",
    "headline": "...",
    "summary": "...",
    "contacts": [
      {"id": "contact-1", "label": "Email", "value": "..."},
      {"id": "contact-2", "label": "Phone", "value": "..."},
      {"id": "contact-3", "label": "LinkedIn", "value": "..."},
      {"id": "contact-4", "label": "Location", "value": "..."},
      {"id": "contact-5", "label": "Work Authorization", "value": "..."}
    ],
    "experience": [
      {
        "id": "exp-1",
        "company": "...",
        "company_url": "...",
        "position": "...",
        "period": "...",
        "responsibilities": ["..."],
        "achievements": ["..."],
        "projects": [
          {"id": "exp-1-proj-1", "name": "...", "period": "...", "achievements": ["..."], "url": "..."}
        ],
        "is_gap": false
      }
    ],
    "education": [
      {"id": "edu-1", "institution": "...", "degree": "...", "field": "...", "period": "..."}
    ],
    "skills": [
      {"id": "skill-1", "name": "...", "category": "...", "evidence_ids": ["ev-1"]}
    ],
    "technologies": [
      {"id": "tech-1", "name": "...", "category": "...", "evidence_ids": ["ev-1"]}
    ],
    "languages": [
      {"id": "lang-1", "name": "...", "proficiency": "..."}
    ],
    "certifications": [
      {"id": "cert-1", "name": "...", "issuer": "...", "date": "..."}
    ],
    "projects": [
      {"id": "proj-1", "name": "...", "description": "...", "url": "..."}
    ],
    "portfolio_links": [
      {"id": "portfoliolink-1", "url": "...", "description": "..."}
    ]
  },
  "evidence": [
    {
      "id": "ev-1",
      "text": "...",
      "source_context": "...",
      "experience_id": "exp-1",
      "experience_project_id": "exp-1-proj-1"
    }
  ]
}
