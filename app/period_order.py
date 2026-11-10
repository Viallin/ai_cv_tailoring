"""Best-effort recency ordering for free-text Experience `period` strings.

`Experience.period` is free text ("Dec 2008 - Mar 2015", "2019–present",
"03/2020 - 06/2021"), so there is no date column to sort on. This module
extracts a (end, start) key so a newly added Experience can be inserted at
its reverse-chronological position instead of the end of the list.
Unparseable periods return None and callers fall back to appending.
"""

from __future__ import annotations

import re

_MONTHS = {
    m: i
    for i, names in enumerate(
        ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1
    )
    for m in [names]
}
_PRESENT = re.compile(r"present|current|now|ongoing|today", re.IGNORECASE)
_DATE = re.compile(
    r"(?:(?P<mname>[A-Za-z]{3,9})\.?[\s,/-]*|(?P<mnum>\d{1,2})[./-])?(?P<year>(?:19|20)\d{2})"
)

_FAR_FUTURE = (9999, 12)


def _month(match: re.Match[str]) -> int:
    if match.group("mname"):
        return _MONTHS.get(match.group("mname")[:3].lower(), 1)
    if match.group("mnum"):
        value = int(match.group("mnum"))
        return value if 1 <= value <= 12 else 1
    return 1


def recency_key(period: str | None) -> tuple[tuple[int, int], tuple[int, int]] | None:
    """Return (end, start) as (year, month) pairs, or None if unparseable."""
    if not period:
        return None
    dates = [(int(m.group("year")), _month(m)) for m in _DATE.finditer(period)]
    present = bool(_PRESENT.search(period))
    if not dates:
        return None
    start = dates[0]
    if present:
        end = _FAR_FUTURE
    elif len(dates) > 1:
        end = dates[1]
    else:
        end = start
    return end, start


def insertion_index(existing_periods: list[str | None], new_period: str | None) -> int:
    """Index at which to insert a new entry into a newest-first list.

    Goes before the first entry that is strictly older than the new one;
    stops (appends) at the end if none is. Entries with unparseable periods
    are skipped over. A new entry with no parseable period is appended.
    """
    new_key = recency_key(new_period)
    if new_key is None:
        return len(existing_periods)
    for index, period in enumerate(existing_periods):
        key = recency_key(period)
        if key is not None and key < new_key:
            return index
    return len(existing_periods)
