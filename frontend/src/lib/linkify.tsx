import type { ReactNode } from "react";

// Shared visible styling for every inline <a> this module (and the
// hand-built company/project links in ExperienceSection.tsx/
// ExperienceForm.tsx/ExperienceEvidencePanel.tsx, which mirror this exact
// convention rather than each inventing their own) produces — found live:
// a bare <a> with no classes is visually indistinguishable from
// surrounding text once Tailwind's Preflight reset strips the browser's
// own default blue/underline, so a real, working link looked like it
// wasn't one at all. Same blue app/cv_pdf.py's own PDF/DOCX link color
// already uses (`.cv-a4-page a` in index.css) — one consistent "this is a
// link" color across the print preview and every editable list.
export const LINK_CLASSNAME = "text-[#0563c1] underline underline-offset-2";

// Auto-detects email addresses and http(s)/www URLs within a plain-text
// string and turns just those substrings into real, clickable <a>
// elements — everything else stays untouched text. Used wherever the app
// shows read-only contact/portfolio/project text (a Contact's "Email:
// foo@bar.com" or "LinkedIn: linkedin.com/in/..." row, a Portfolio Link,
// a Project's `(url)`) so a user can actually click through instead of
// hand-copying a plain string. Deliberately NOT applied inside editable
// <Textarea>/<Input> fields — a form field's value has to stay a plain
// string for editing to work at all; only read-only surfaces (Profile
// Explorer's list rows, the CV preview header, the print/export preview)
// use this.
//
// Mirrors (but is intentionally a little more permissive than)
// app/markdown_inline.py's `_URL_RE`/`_split_urls` — that one only needs
// to catch bare `https://` URLs inside already-rendered Markdown text for
// DOCX/PDF export; this one also catches bare emails and `www.`-prefixed
// URLs, since a resume's Contacts section is exactly where those show up
// on screen.
const _EMAIL_RE = "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}";
const _URL_RE = "(?:https?://|www\\.)\\S+";
const _LINK_RE = new RegExp(`(${_EMAIL_RE})|(${_URL_RE})`, "g");

// Trailing characters that are almost always sentence/list punctuation
// rather than part of the link itself (e.g. "(www.site.com)",
// "www.site.com," or "www.site.com | Phone: ..."). Same set as
// markdown_inline.py's _URL_TRAILING_PUNCTUATION.
const _TRAILING_PUNCTUATION = ".,;:!?'\")]}»|";

function trimTrailingPunctuation(url: string): string {
  let end = url.length;
  while (end > 0 && _TRAILING_PUNCTUATION.includes(url[end - 1])) {
    end -= 1;
  }
  return url.slice(0, end);
}

/** Splits `text` into an array of plain strings and `<a>` elements — safe
 * to drop directly into JSX children (e.g. `<p>{linkifyText(text)}</p>`). */
export function linkifyText(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  let pos = 0;
  let key = 0;

  for (const match of text.matchAll(_LINK_RE)) {
    const [, email, url] = match;
    const start = match.index ?? 0;
    const raw = email ?? url ?? "";
    const matched = email ? raw : trimTrailingPunctuation(raw);
    if (!matched) {
      continue;
    }
    if (start > pos) {
      nodes.push(text.slice(pos, start));
    }
    const href = email ? `mailto:${matched}` : matched.startsWith("www.") ? `https://${matched}` : matched;
    nodes.push(
      <a key={key++} href={href} target="_blank" rel="noopener noreferrer" className={LINK_CLASSNAME}>
        {matched}
      </a>,
    );
    pos = start + matched.length;
  }
  if (pos < text.length) {
    nodes.push(text.slice(pos));
  }
  return nodes;
}

/** Component form of `linkifyText`, for call sites that read more clearly
 * as a component than a raw `{linkifyText(...)}` expression. */
export function Linkify({ text }: { text: string }): ReactNode {
  return <>{linkifyText(text)}</>;
}

// A resume's Contacts commonly write a LinkedIn/portfolio/GitHub value as
// a bare domain with no `http(s)://`/`www.` prefix at all — e.g.
// "linkedin.com/in/anton-guzeev" or "aguzeev.artstation.com" (confirmed
// directly, from a real ingested resume). `linkifyText`'s general
// http(s)/www-only detection misses those entirely, but a *general*
// bare-domain regex is too dangerous to run over arbitrary text — it
// would misfire on real technology names like "ASP.NET" or "Node.js"
// (".net"/".io" etc. are legitimate TLDs). A Contact's `value` is
// different: it's never a sentence, just one token, so it's safe to
// check the ENTIRE trimmed value against a whitelisted-TLD domain
// pattern (anchored start-to-end) rather than scanning for a substring —
// `contactValueHref` is only ever called with a whole Contact.value, and
// is what makes this precise enough to use safely.
const _COMMON_TLDS = [
  "com", "org", "net", "io", "dev", "co", "me", "app", "ai", "edu", "gov",
  "info", "biz", "tv", "xyz", "site", "online", "tech", "design", "art",
  "gg", "so", "cc", "us", "uk", "ca", "de", "fr", "es", "it", "nl", "se",
  "no", "dk", "fi", "pl", "ru", "jp", "cn", "in", "au", "nz", "br", "mx",
  "ch", "at", "be", "ie", "pt", "gr", "tr", "kr",
]; // prettier-ignore
const _BARE_DOMAIN_WHOLE_RE = new RegExp(
  `^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\\.)+(?:${_COMMON_TLDS.join("|")})(?:/\\S*)?$`,
  "i",
);
const _EMAIL_WHOLE_RE = new RegExp(`^${_EMAIL_RE}$`);

function contactValueHref(value: string): string | null {
  const trimmed = value.trim();
  if (!trimmed) {
    return null;
  }
  if (_EMAIL_WHOLE_RE.test(trimmed)) {
    return `mailto:${trimmed}`;
  }
  if (/^https?:\/\//i.test(trimmed)) {
    return trimmed;
  }
  if (/^www\./i.test(trimmed)) {
    return `https://${trimmed}`;
  }
  if (_BARE_DOMAIN_WHOLE_RE.test(trimmed)) {
    return `https://${trimmed}`;
  }
  return null;
}

/** Renders one Contact as `"Label: "` (plain) + `value` (a real <a> when
 * it's link-shaped, plain text otherwise — e.g. "Phone"/"Location"/"Work
 * Authorization" values never are). Used instead of `linkifyText` for
 * Contacts specifically, since it can safely check a whole `value` for a
 * bare domain — see the comment above `contactValueHref`. */
export function linkifyContactLine(label: string, value: string): ReactNode {
  const href = contactValueHref(value);
  if (href == null) {
    return `${label}: ${value}`;
  }
  return (
    <>
      {label}:{" "}
      <a href={href} target="_blank" rel="noopener noreferrer" className={LINK_CLASSNAME}>
        {value}
      </a>
    </>
  );
}
