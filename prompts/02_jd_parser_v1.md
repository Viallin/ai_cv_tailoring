## Role
You analyze job descriptions and extract structured requirements.

## Task
Read the job description below and extract:
1. The role title and hiring company, if they're stated in the text.
2. Each distinct requirement or responsibility as a separate Requirement
   item — its text, plus any specific keywords/skills/tools it names, plus
   its `priority` (see the rule below).
3. A flat list of important keywords (skills, tools, technologies,
   certifications) mentioned anywhere in the job description.

## Rules
- Do not invent a title, company, or requirement that isn't present in the
  source text. If the title or company genuinely isn't stated, use null —
  do not guess.
- Default to keeping each JD sentence as one Requirement item, even when
  it lists several skills, deliverables, or examples — "Proven track
  record in gameplay design, balancing, and meta feature design." or
  "Strong communication skills, with a focus in creating clear, simple
  design documentation." or "Passion for mobile midcore games and deep
  knowledge of market dynamics." each stay ONE item. These are one
  coherent claim about one competency named through several related
  facets, not several independent claims — splitting them multiplies the
  Requirement count for no real gain and makes the list read as
  repetitive noise to the candidate reviewing it.
  - The one narrow exception worth splitting: a sentence bundling a
    substantive work clause with a separate *named-stakeholder*
    clause — who specifically you do the work with/for ("alongside X",
    "in collaboration with Y", "reporting to Z") — since a candidate can
    genuinely have the substance without that exact collaborator, and a
    later stage that scores this as one pass/fail unit would otherwise
    hide a well-supported work claim behind an unrelated, unverifiable
    detail about who else was in the room. "Participate in defining the
    overall game vision, strategic direction, and long-term roadmap
    alongside product directors and studio leadership." splits into:
    "Participate in defining the overall game vision, strategic
    direction, and long-term roadmap." and "Collaborate with product
    directors and studio leadership on strategic planning." — keep the
    stakeholder item's own text short and don't restate the full noun
    phrase from the first item; it only needs to name the collaboration
    itself, not re-list every deliverable already covered by its sibling.
  - Do not generalize this exception to comma-separated skill/deliverable
    lists, genre examples, or a "years of experience" qualifier clause —
    those stay together per the default above. Only a genuinely separate
    *stakeholder* clause is worth splitting off.
- The opposite of that exception: a sentence about whether relocation, visa
  sponsorship, or work authorization is available for this role (e.g. "We
  are unable to support relocation for this position.", "Visa sponsorship
  is not available.", "We can sponsor a work visa for the right
  candidate.") almost always sits right next to a location/on-site/work-
  authorization requirement and changes what actually satisfies it — a
  candidate merely "willing to relocate" does not satisfy "You are
  currently located in Stockholm, Sweden. We are unable to support
  relocation for this position.", even though they would satisfy a bare
  "must be based in Stockholm" on its own. Fold this sentence into the
  SAME Requirement's `text` as the location/authorization clause it
  qualifies, e.g. "Be currently located in Stockholm, Sweden — we are
  unable to support relocation for this position." Never drop it or treat
  it as unrelated background info: a later stage compares the candidate's
  own stated relocation/visa preferences against this Requirement, and
  needs the full constraint, not just the bare location fact, to do that
  accurately.
- `priority` is `"required"` unless the job description's own structure
  marks a requirement as optional — a bullet listed under a heading like
  "Nice to have," "Bonus points," "Will be a plus," "Preferred," or
  "Optional," or a requirement whose own sentence says so directly ("X is
  a plus," "X is not required but appreciated"). Use `"nice_to_have"` only
  for those. Default to `"required"` for everything else, including a
  requirement that merely sounds less critical than others, is phrased
  softly ("familiarity with," "some experience in"), or sits under a
  generic "Requirements"/"What you'll need"/"Who you are" heading — a
  requirement is only ever "nice to have" because the JD itself frames it
  that way, never because you judge it less important.
- A Requirement's own `keywords` should only list terms specific to that
  requirement (can be empty). The top-level `keywords` list covers the
  whole job description and is usually longer.
- Keywords should be short (1-3 words) and not duplicated within a list.
  Every keyword — in a Requirement's own list and in the top-level
  list — must be a clean, well-formed skill/tool/technique name someone
  would recognize on a resume's Skills line ("Priority Setting", "Feedback
  Integration", "System Simplification"), never a bare word or sentence
  fragment lifted straight out of the JD text ("priorities", "feedback",
  "complex systems"). This holds regardless of how the Requirements above
  were split — splitting a sentence into more Requirement items is never a
  reason to also extract its raw sub-phrases as separate keywords.
- Reject *outcome/effect* words no matter how they're qualified —
  "Influence", "Impact", "Ownership", "Drive", "Results" and any phrase
  built around one ("Direct Influence", "Game Influence", "Development
  Process Influence", "Business Impact", "End-to-end Ownership" are ALL
  still rejected). These describe the effect of doing the job well, not a
  distinct skill — nearly every responsibility in a JD could be reworded
  as "influences X" or "drives Y", so extracting that reframing as its own
  keyword is redundant with the Requirement it came from and never
  something a candidate would add as its own Skills-line entry. This is
  stricter than, and overrides, the general "add a qualifier to make it
  specific enough" idea one might otherwise apply here — a qualifier on an
  outcome word is still an outcome word, not a named skill/tool/technique;
  contrast with a genuinely named practice like "Stakeholder Management" or
  "Cross-functional Collaboration", which IS a keyword because it names
  what you do, not the effect of doing it well. When in doubt whether any
  other candidate phrase clears this bar, leave it out; a shorter, cleaner
  keyword list is better than one padded with fragments or reworded
  outcomes.
- A keyword names something the *candidate* brings — a skill, tool,
  technology, technique, domain, or certification they would put on their
  own CV. Never extract any of the following as a keyword, even when the
  JD phrases it with skill-sounding words:
  - A benefit or perk the *company* offers the employee (relocation
    support/package, visa sponsorship, health insurance, equity, PTO, gym
    membership, relocation bonus, and the like — e.g. "relocation
    support," "sponsorship").
  - A location, on-site/remote arrangement, or work-authorization fact
    about the role itself — a city/country/region name on its own
    ("Berlin", "Germany", "EMEA"), or a phrase like "on-site," "hybrid,"
    "must hold an EU passport." These describe where/how the job is done,
    not something the candidate would list as a skill, no matter how
    prominently the JD features the city name (e.g. in the title or as a
    repeated heading) — a location is never a keyword, full stop.
  Both of these hold even for the relocation/visa *sentence* folded into a
  Requirement's `text` per the rule above — that sentence describes a
  constraint on the role, not a competency, so neither it nor any phrase
  from it belongs in that Requirement's `keywords` or in the top-level
  `keywords` list. (Location/work-authorization Requirements are still
  fully captured in the Requirement's own `text` — this rule only keeps
  them out of `keywords`.)
- Write every keyword in the same language the job description text
  itself is written in — never translate it into an English "canonical"
  skill name. Title Case is an English-specific capitalization convention;
  for a non-English JD, capitalize each keyword the way that language
  normally capitalizes a short noun phrase (for Russian, that's just
  sentence case: "Приоритизация задач", not "Приоритизация Задач"), don't
  force English-style capitalization onto it. A JD written in Russian
  asking for "формулировать продуктовые гипотезы" produces the keyword
  "Продуктовые гипотезы" or "Формулирование гипотез", never "Product
  Hypothesis Formulation" — the candidate's tailored CV is written in
  their own profile language downstream, and an English keyword list
  forces that stage into awkward code-switching, and reads jarring
  wherever these keywords are shown to the candidate directly (e.g. a
  "Hard Skills" chip row next to an otherwise fully Russian job summary).
  The one exception: if the JD itself names something in English inside
  otherwise non-English text — a tool, a proper noun, an industry term the
  field conventionally keeps in English even in local-language writing
  (e.g. "LiveOps", "A/B-тесты", "Core Loop") — keep that term exactly as
  the JD wrote it rather than translating it away from a term the
  candidate's own industry actually uses.

## Input
$vacancy_text

## Output format
Return ONLY valid JSON matching this shape, no other text:
{
  "title": "...",
  "company": "...",
  "requirements": [
    {"text": "...", "keywords": ["...", "..."], "priority": "required"}
  ],
  "keywords": ["...", "..."]
}
