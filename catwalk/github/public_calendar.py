"""Read the contribution calendar exactly as a stranger sees it: github.com/users/<login>/contributions.

This is the privacy guard. The API calendar is only published if it matches this anonymous page day by day,
so the profile and the website can never show a number that GitHub itself does not show the public.

The page is HTML, not an API, so the parser is deliberately narrow: it pairs each day cell
(<td id="contribution-day-component-W-D" data-date="YYYY-MM-DD">) with its tooltip
(<tool-tip for="contribution-day-component-W-D">12 contributions on November 3rd.</tool-tip>).
If GitHub changes the markup, parsing finds too few days and the refresh keeps the last good data.
"""

from __future__ import annotations

import re
from html import unescape

_CELL = re.compile(r"<td\b[^>]*>", re.IGNORECASE)
_CELL_ID = re.compile(r'id="(contribution-day-component-\d+-\d+)"')
_CELL_DATE = re.compile(r'data-date="(\d{4}-\d{2}-\d{2})"')
_TOOLTIP = re.compile(r'for="(contribution-day-component-\d+-\d+)"[^>]*>([^<]*)<')
# Only the LEADING number is the count: "36 contributions on September 6th" is 36, not 366.
_LEADING_COUNT = re.compile(r"^([\d,.]+)\s+contributions?\b", re.IGNORECASE)
_NONE = re.compile(r"^No contributions\b", re.IGNORECASE)


def parse_public_calendar(html: str) -> dict[str, int | None]:
    """Map 'YYYY-MM-DD' -> count. A day whose tooltip cannot be read maps to None (never guessed)."""
    flat = re.sub(r"\s+", " ", html)
    cell_dates: dict[str, str] = {}
    for match in _CELL.finditer(flat):
        tag = match.group(0)
        cell_id, cell_date = _CELL_ID.search(tag), _CELL_DATE.search(tag)
        if cell_id and cell_date:
            cell_dates[cell_id.group(1)] = cell_date.group(1)

    counts: dict[str, int | None] = {}
    for match in _TOOLTIP.finditer(flat):
        day = cell_dates.get(match.group(1))
        if day is None:
            continue
        text = unescape(match.group(2)).strip()
        if _NONE.match(text):
            counts[day] = 0
            continue
        lead = _LEADING_COUNT.match(text)
        counts[day] = int(re.sub(r"[,.]", "", lead.group(1))) if lead else None
    return counts
