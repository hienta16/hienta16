"""The toy box rules, as pure functions over ToyState. No I/O here, so every rule is unit-tested directly.

handle(state, request, rules, now) runs one gift request through, in this order:

1. duplicate    the issue was already processed (a re-run, a redelivered event): nothing changes
2. stale        the issue is older than the history window: skipped, not recorded
3. not_a_person the author is a bot or an organisation account: refused (recorded)
4. unknown_toy  the title names no toy we know: refused (recorded)
5. cooldown     this account (by numeric id) already had a gift accepted within ±cooldown of this
                issue's creation time: refused (recorded). Measured on GitHub's created_at, so the
                order in which runs happen does not matter.
6. accepted     the gift goes into the scene with created_at = issue creation and
                expires_at = created_at + the toy's lifetime. If the scene is full, the oldest toy is
                put away early. totals[toy] goes up by one and stays up after the toy expires.

expire(state, now) removes toys whose expires_at has passed; prune(state, rules, now) forgets ledger
entries older than the history window. Times are UTC throughout.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from .events import GiftRequest
from .models import Gift, Giver, LedgerEntry, ToyState
from .rules import ToyRules

ACCEPTED = "accepted"
DUPLICATE = "duplicate"
STALE = "stale"
NOT_A_PERSON = "not_a_person"
UNKNOWN_TOY = "unknown_toy"
COOLDOWN = "cooldown"

CLOCK_SKEW = timedelta(minutes=5)


@dataclass(frozen=True)
class Decision:
    outcome: str
    issue: int
    toy: str | None = None
    gift: Gift | None = None
    displaced: tuple[Gift, ...] = ()
    retry_after: datetime | None = None

    @property
    def records(self) -> bool:
        """Whether this decision is written to the ledger (so a re-run is recognised as a duplicate)."""
        return self.outcome not in (DUPLICATE, STALE)


def visible(state: ToyState, now: datetime) -> list[Gift]:
    """Toys that are in the scene right now, oldest first."""
    return sorted((g for g in state.active if g.expires_at > now), key=lambda g: (g.created_at, g.issue))


def decide(state: ToyState, request: GiftRequest, rules: ToyRules, now: datetime) -> Decision:
    if state.processed(request.issue):
        return Decision(DUPLICATE, request.issue, request.toy)
    created = min(request.created_at, now + CLOCK_SKEW)
    if created < now - rules.history:
        return Decision(STALE, request.issue, request.toy)
    if request.user_type != "User" or request.login.endswith("[bot]"):
        return Decision(NOT_A_PERSON, request.issue, request.toy)
    if request.toy is None or request.toy not in rules.kinds:
        return Decision(UNKNOWN_TOY, request.issue, None)

    if request.login.lower() not in rules.exempt_logins:
        recent = [
            e.at
            for e in state.ledger
            if e.outcome == ACCEPTED and e.user_id == request.user_id and abs(e.at - created) < rules.cooldown
        ]
        if recent:
            return Decision(COOLDOWN, request.issue, request.toy, retry_after=max(recent) + rules.cooldown)

    kind = rules.kinds[request.toy]
    gift = Gift(
        id=f"gift-{request.issue}",
        toy=kind.key,
        variant=kind.variant_for(request.issue),
        issue=request.issue,
        giver=Giver(request.login, request.user_id),
        created_at=created,
        expires_at=created + kind.lifetime,
    )
    scene = visible(state, now)
    displaced: list[Gift] = []
    if gift.expires_at > now:
        while len(scene) - len(displaced) >= rules.max_visible:
            displaced.append(scene[len(displaced)])
    return Decision(ACCEPTED, request.issue, kind.key, gift=gift, displaced=tuple(displaced))


def apply(state: ToyState, decision: Decision, request: GiftRequest, now: datetime) -> ToyState:
    if not decision.records:
        return state
    entry = LedgerEntry(
        issue=decision.issue,
        outcome=decision.outcome,
        at=min(request.created_at, now + CLOCK_SKEW),
        processed_at=now,
        user_id=request.user_id,
        toy=decision.toy,
    )
    active = state.active
    totals = dict(state.totals)
    if decision.outcome == ACCEPTED and decision.gift is not None:
        gone = {g.id for g in decision.displaced}
        active = tuple(g for g in active if g.id not in gone)
        if decision.gift.expires_at > now:
            active = active + (decision.gift,)
        totals[decision.gift.toy] = totals.get(decision.gift.toy, 0) + 1
    return state.with_changes(active=active, totals=totals, ledger=state.ledger + (entry,), updated_at=now)


def expire(state: ToyState, now: datetime) -> tuple[ToyState, list[Gift]]:
    gone = [g for g in state.active if g.expires_at <= now]
    if not gone:
        return state, []
    keep = tuple(g for g in state.active if g.expires_at > now)
    return state.with_changes(active=keep, updated_at=now), gone


def prune(state: ToyState, rules: ToyRules, now: datetime) -> ToyState:
    keep = tuple(e for e in state.ledger if e.at >= now - rules.history)
    if len(keep) == len(state.ledger):
        return state
    return state.with_changes(ledger=keep)


def handle(state: ToyState, request: GiftRequest, rules: ToyRules, now: datetime) -> tuple[ToyState, Decision]:
    decision = decide(state, request, rules, now)
    new = apply(state, decision, request, now)
    new, _ = expire(new, now)
    new = prune(new, rules, now)
    return new, decision
