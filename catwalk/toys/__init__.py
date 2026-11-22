"""The cat's toy box: visitors give toys through GitHub issues; Python validates, rate-limits and expires them.

    events.py   GitHub issue event  -> GiftRequest (only GitHub-vouched fields are trusted)
    engine.py   the rules as pure functions: duplicates, cooldown, lifetimes, display cap, expiry
    models.py   data/toys.json as typed objects with strict loading
    rules.py    config/toys.json (editable lifetimes, cooldown, limits, copy)
    replies.py  fixed reply templates for the issue comment
    store.py    load and save the state file
"""

from .engine import ACCEPTED, COOLDOWN, DUPLICATE, NOT_A_PERSON, STALE, UNKNOWN_TOY, Decision, expire, handle, prune, visible
from .events import EventError, GiftRequest, Ignored, parse_issue_event, parse_toy_title
from .models import Gift, Giver, LedgerEntry, StateError, ToyState
from .rules import ToyKind, ToyRules, load_rules

__all__ = [
    "ACCEPTED",
    "COOLDOWN",
    "DUPLICATE",
    "NOT_A_PERSON",
    "STALE",
    "UNKNOWN_TOY",
    "Decision",
    "EventError",
    "Gift",
    "GiftRequest",
    "Giver",
    "Ignored",
    "LedgerEntry",
    "StateError",
    "ToyKind",
    "ToyRules",
    "ToyState",
    "expire",
    "handle",
    "load_rules",
    "parse_issue_event",
    "parse_toy_title",
    "prune",
    "visible",
]
