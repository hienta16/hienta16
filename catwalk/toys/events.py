"""Turn a GitHub `issues` event into a gift request, trusting only what GitHub itself vouches for.

Trusted (set by GitHub, not by the visitor): the issue number, when it was opened, and who opened it
(login, numeric id, account type). Visitor-controlled: the title. The title is matched against a strict
allow-list and is never executed, echoed into a shell, or stored. The issue body is ignored entirely.

Outcomes:
* GiftRequest  a toy request to decide on (it may still be refused: unknown toy, bot, cooldown…)
* Ignored      not for the toy box at all (another kind of issue, a pull request, an edit…): no reply, no change
* EventError   the payload itself is broken: the workflow fails loudly and nothing is written
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime

from ..config import LOGIN_RE
from ..timeutil import parse_ts
from .rules import ToyRules

MAX_TITLE = 120


class EventError(ValueError):
    pass


@dataclass(frozen=True)
class GiftRequest:
    issue: int
    login: str
    user_id: int
    user_type: str
    created_at: datetime
    toy: str | None  # None: the title starts with the prefix but names no toy we know


@dataclass(frozen=True)
class Ignored:
    reason: str


def parse_toy_title(title: str, rules: ToyRules) -> tuple[bool, str | None]:
    """(is a toy request, toy key or None). Accepts '[cat-toy] yarn', '[CAT-TOY]  Yarn ball', '[cat-toy] give a box'."""
    if not isinstance(title, str):
        return False, None
    text = " ".join(title.split())
    if not text.lower().startswith(rules.title_prefix.lower()):
        return False, None
    rest = text[len(rules.title_prefix) :].strip().lower()
    if len(text) > MAX_TITLE:
        return True, None
    keys = "|".join(sorted(map(re.escape, rules.kinds), key=len, reverse=True))
    match = re.fullmatch(rf"(?:give\s+(?:a\s+|an\s+)?)?({keys})(?:\s+(?:ball|toy))?\s*[.!]*", rest)
    return True, (match.group(1) if match else None)


def parse_issue_event(payload: object, rules: ToyRules, expected_repo: str) -> GiftRequest | Ignored:
    if not isinstance(payload, dict):
        raise EventError("the event payload is not an object")
    if payload.get("action") != "opened":
        return Ignored(f"action is {payload.get('action')!r}, only newly opened issues are read")
    repo = (payload.get("repository") or {}).get("full_name")
    if not isinstance(repo, str) or repo.lower() != expected_repo.lower():
        return Ignored("the event is from another repository (a fork or a copy)")
    issue = payload.get("issue")
    if not isinstance(issue, dict):
        raise EventError("the event has no issue")
    if issue.get("pull_request"):
        return Ignored("pull requests are not toy requests")

    is_toy, toy = parse_toy_title(issue.get("title", ""), rules)
    if not is_toy:
        return Ignored("the title does not start with the toy prefix")

    user = issue.get("user")
    if not isinstance(user, dict):
        raise EventError("the issue has no author")
    login, user_id, user_type = user.get("login"), user.get("id"), user.get("type")
    number = issue.get("number")
    if not isinstance(login, str) or not (LOGIN_RE.fullmatch(login) or _is_bot_login(login)):
        raise EventError("the issue author has no valid login")
    if not isinstance(user_id, int) or isinstance(user_id, bool) or user_id <= 0:
        raise EventError("the issue author has no valid id")
    if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
        raise EventError("the issue has no valid number")
    try:
        created = parse_ts(issue.get("created_at"))
    except ValueError as exc:
        raise EventError(f"the issue has no valid created_at ({exc})") from exc
    return GiftRequest(
        issue=number,
        login=login,
        user_id=user_id,
        user_type=str(user_type or "Unknown"),
        created_at=created,
        toy=toy,
    )


def _is_bot_login(login: str) -> bool:
    return login.endswith("[bot]") and bool(LOGIN_RE.fullmatch(login[:-5]))
