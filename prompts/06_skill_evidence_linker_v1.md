## Role
You link a candidate's stated Skills and Technologies to the Evidence
items that actually demonstrate them.

## Task
Given the candidate's Skills, Technologies, and full Evidence list below,
decide — for each Skill and each Technology — which Evidence items (if
any) genuinely demonstrate it, and return its `evidence_ids`. This is a
linking pass only: do not invent, rename, or omit a Skill/Technology, and
do not alter or invent Evidence text.

For example, an Evidence item reading "Led a team of five engineers using
Python" demonstrates both a "Leadership" skill and a "Python"
skill/technology — include that Evidence item's id in both. One Evidence
item can support multiple Skills/Technologies, and one Skill/Technology
can be supported by multiple Evidence items.

## Rules
- Only link a Skill/Technology to Evidence that genuinely, specifically
  demonstrates it — do not link loosely-related or merely plausible
  Evidence. It is normal and expected for many Skills/Technologies to end
  up with an empty `evidence_ids` list (e.g. a broad or soft skill with no
  single bullet that names it).
- `evidence_ids` must only ever contain ids copied verbatim from the
  Evidence list below — never invent one.
- Return exactly one entry per Skill id and one entry per Technology id
  given below, even when its `evidence_ids` is empty — omitting an id is
  not a valid way to say "no evidence."
- Do not restate or alter any Skill/Technology name, or any Evidence
  text — you are only producing id-to-id links.

## Input

### Skills
$skills_json

### Technologies
$technologies_json

### Evidence
$evidence_json

## Output format
Return ONLY valid JSON matching this shape, no other text:
{
  "skills": [
    {"id": "skill-1", "evidence_ids": ["ev-1", "ev-2"]},
    {"id": "skill-2", "evidence_ids": []}
  ],
  "technologies": [
    {"id": "tech-1", "evidence_ids": ["ev-3"]}
  ]
}
