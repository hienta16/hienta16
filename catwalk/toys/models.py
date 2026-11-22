"""The toy box state (data/toys.json) as typed objects, with strict loading and deterministic saving.

    active   gifts currently in the scene (each with created_at and expires_at, UTC)
    totals   every accepted gift ever, per toy: kept when toys expire or are put away
    ledger   every processed issue within the history window (dedupe + cooldown memory)

Only what is needed is stored: the giver's public login (shown as "from @login") and numeric account id
(the identity used for the cooldown, because logins can be renamed). Issue bodies are never stored.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from datetime import datetime

from ..config import LOGIN_RE
from ..timeutil import iso, parse_ts

SCHEMA = 1
_WORD = re.compile(r"^[a-z]{2,16}$")


class StateError(ValueError):
    """data/toys.json is malformed. The workflow stops instead of overwriting it."""


@dataclass(frozen=True)
class Giver:
    login: str
    id: int

    def __post_init__(self) -> None:
        if not LOGIN_RE.fullmatch(self.login):
            raise StateError(f"not a GitHub login: {self.login!r}")
        if not isinstance(self.id, int) or isinstance(self.id, bool) or self.id <= 0:
            raise StateError("giver id must be a positive integer")


@dataclass(frozen=True)
class Gift:
    id: str
    toy: str
    variant: str
    issue: int
    giver: Giver
    created_at: datetime
    expires_at: datetime
    source: str = "github-issue"

    def to_json(self) -> dict:
        return {
            "id": self.id,
            "toy": self.toy,
            "variant": self.variant,
            "issue": self.issue,
            "giver": {"login": self.giver.login, "id": self.giver.id},
            "createdAt": iso(self.created_at),
            "expiresAt": iso(self.expires_at),
            "source": self.source,
        }

    @classmethod
    def from_json(cls, raw: dict) -> "Gift":
        try:
            gift = cls(
                id=str(raw["id"]),
                toy=str(raw["toy"]),
                variant=str(raw["variant"]),
                issue=_positive(raw["issue"]),
                giver=Giver(str(raw["giver"]["login"]), _positive(raw["giver"]["id"])),
                created_at=parse_ts(raw["createdAt"]),
                expires_at=parse_ts(raw["expiresAt"]),
                source=str(raw.get("source", "github-issue")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StateError(f"malformed gift: {exc}") from exc
        if gift.expires_at <= gift.created_at:
            raise StateError(f"gift {gift.id} expires before it was created")
        if not _WORD.fullmatch(gift.toy) or not _WORD.fullmatch(gift.variant):
            raise StateError(f"gift {gift.id} has an odd toy or variant name")
        return gift


@dataclass(frozen=True)
class LedgerEntry:
    issue: int
    outcome: str
    at: datetime  # when the issue was opened (GitHub's created_at), the moment the cooldown is measured from
    processed_at: datetime
    user_id: int | None = None
    toy: str | None = None

    def to_json(self) -> dict:
        out = {"issue": self.issue, "outcome": self.outcome, "at": iso(self.at), "processedAt": iso(self.processed_at)}
        if self.user_id is not None:
            out["userId"] = self.user_id
        if self.toy is not None:
            out["toy"] = self.toy
        return out

    @classmethod
    def from_json(cls, raw: dict) -> "LedgerEntry":
        try:
            return cls(
                issue=_positive(raw["issue"]),
                outcome=str(raw["outcome"]),
                at=parse_ts(raw["at"]),
                processed_at=parse_ts(raw["processedAt"]),
                user_id=_positive(raw["userId"]) if raw.get("userId") is not None else None,
                toy=str(raw["toy"]) if raw.get("toy") is not None else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise StateError(f"malformed ledger entry: {exc}") from exc


@dataclass(frozen=True)
class ToyState:
    updated_at: datetime | None = None
    active: tuple[Gift, ...] = ()
    totals: dict[str, int] = field(default_factory=dict)
    ledger: tuple[LedgerEntry, ...] = ()

    def __post_init__(self) -> None:
        # One canonical order, so equal states compare equal and save to identical files.
        object.__setattr__(self, "active", tuple(sorted(self.active, key=lambda g: (g.created_at, g.issue))))
        object.__setattr__(self, "ledger", tuple(sorted(self.ledger, key=lambda e: e.issue)))

    @classmethod
    def empty(cls, toy_keys: list[str] | tuple[str, ...]) -> "ToyState":
        return cls(totals={k: 0 for k in toy_keys})

    def processed(self, issue: int) -> LedgerEntry | None:
        return next((e for e in self.ledger if e.issue == issue), None)

    def with_changes(self, **changes) -> "ToyState":
        return replace(self, **changes)

    def to_json(self) -> dict:
        return {
            "schema": SCHEMA,
            "updatedAt": iso(self.updated_at) if self.updated_at else None,
            "active": [g.to_json() for g in sorted(self.active, key=lambda g: (g.created_at, g.issue))],
            "totals": dict(sorted(self.totals.items())),
            "giftsTotal": sum(self.totals.values()),
            "ledger": [e.to_json() for e in sorted(self.ledger, key=lambda e: e.issue)],
        }

    @classmethod
    def from_json(cls, raw: object, toy_keys: list[str] | tuple[str, ...]) -> "ToyState":
        if not isinstance(raw, dict) or raw.get("schema") != SCHEMA:
            raise StateError(f"data/toys.json must be an object with schema {SCHEMA}")
        try:
            totals = {str(k): _whole(v) for k, v in dict(raw.get("totals") or {}).items()}
            for k in toy_keys:
                totals.setdefault(k, 0)
            active = tuple(Gift.from_json(g) for g in raw.get("active") or [])
            ledger = tuple(LedgerEntry.from_json(e) for e in raw.get("ledger") or [])
            updated = parse_ts(raw["updatedAt"]) if raw.get("updatedAt") else None
        except (TypeError, ValueError) as exc:
            raise StateError(str(exc)) from exc
        issues = [e.issue for e in ledger]
        if len(issues) != len(set(issues)):
            raise StateError("the ledger lists an issue twice")
        return cls(updated_at=updated, active=active, totals=totals, ledger=ledger)


def _positive(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
        raise ValueError(f"expected a positive integer, got {value!r}")
    return value


def _whole(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 0:
        raise ValueError(f"expected a whole number, got {value!r}")
    return value
