"""What the bot says on the issue. Fixed templates: the visitor's title and body are never quoted back.

The only visitor value used is the login, which GitHub validated and events.py re-checked
(letters, digits and single hyphens), so a reply cannot be made to carry markup or links.
"""

from __future__ import annotations

from ..timeutil import duration_words, human_utc
from .engine import ACCEPTED, COOLDOWN, NOT_A_PERSON, STALE, UNKNOWN_TOY, Decision
from .rules import ToyRules

BUSY = "busy"


def reply_for(decision: Decision | None, rules: ToyRules, login: str, site_url: str, outcome: str | None = None) -> str | None:
    """The comment body, or None when nothing should be said (duplicates, ignored issues)."""
    outcome = outcome or (decision.outcome if decision else None)
    examples = ", ".join(f"`{rules.title_prefix} {k}`" for k in rules.kinds)
    if outcome == ACCEPTED and decision and decision.gift and decision.shelved_at_once:
        kind = rules.kinds[decision.gift.toy]
        return (
            f"Thanks, @{login}! Your {kind.label.lower()} arrived, but the toy box was full of newer toys, so it went "
            "straight onto the shelf. It still counts in the gifts given so far."
        )
    if outcome == ACCEPTED and decision and decision.gift:
        kind = rules.kinds[decision.gift.toy]
        lines = [
            f"{kind.arrival}",
            "",
            f"It stays in the toy box until **{human_utc(decision.gift.expires_at)}** ({duration_words(kind.lifetime)}). "
            f"Watch the cat play with it at {site_url}/#cat once the page refreshes, usually within a few minutes.",
        ]
        if decision.displaced:
            lines += ["", f"The box holds {rules.max_visible} toys at a time, so the oldest one went back on the shelf to make room."]
        lines += ["", f"Thanks, @{login}!"]
        return "\n".join(lines)
    if outcome == COOLDOWN and decision and decision.retry_after:
        return (
            f"Thanks, @{login}! Hien's cat already has a toy from you. The toy box takes one gift per GitHub account "
            f"every {duration_words(rules.cooldown)}, so you can give another one after **{human_utc(decision.retry_after)}**."
        )
    if outcome == UNKNOWN_TOY:
        return (
            f"Hien's cat sniffed this one and didn't recognise the toy. Open an issue titled {examples} "
            "(or use the buttons on the profile) and it will be checked straight away."
        )
    if outcome == NOT_A_PERSON:
        return "Toys come from people, so this request from an automated account was skipped."
    if outcome == STALE:
        return (
            f"This request is older than the toy box remembers ({rules.history.days} days), so it was skipped. "
            "Open a new issue to give a toy."
        )
    if outcome == BUSY:
        return "The toy box was too busy to take this gift, so nothing was saved. Please open the issue again in a few minutes."
    return None


def close_reason(outcome: str) -> str | None:
    """How the issue is closed: accepted gifts are 'completed', refusals 'not planned', the rest left alone."""
    if outcome == ACCEPTED:
        return "completed"
    if outcome in (COOLDOWN, UNKNOWN_TOY, NOT_A_PERSON, STALE, BUSY):
        return "not_planned"
    return None


def commit_message(outcome: str, issue: int | None, toy: str | None, login: str | None) -> str:
    if outcome == ACCEPTED and toy and login:
        return f"chore(toys): {toy} from @{login} (#{issue})"
    if issue:
        return f"chore(toys): record #{issue} ({outcome})"
    return "chore(toys): update the toy box"
