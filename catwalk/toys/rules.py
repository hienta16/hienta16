"""The toy box rules, loaded from config/toys.json so they can be changed without touching code.

    title_prefix    issues must start with this (e.g. "[cat-toy] yarn"); anything else is not a toy request
    cooldown_hours  one accepted gift per GitHub account per rolling window of this many hours
    max_visible     at most this many toys in the scene (1–12); a new gift puts the oldest one away early
    history_days    how long accepted gifts are remembered (duplicates, cooldowns). Must outlast the cooldown by a day.
    exempt_logins   accounts the cooldown does not apply to (empty by default)
    toys.<key>      label, button text, lifetime_hours, variants (colours), behaviour words, arrival message
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path

from ..jsonio import read_json

KEY_RE = re.compile(r"^[a-z]{2,16}$")
MAX_LIFETIME = timedelta(days=90)


@dataclass(frozen=True)
class ToyKind:
    key: str
    label: str
    action: str
    lifetime: timedelta
    variants: tuple[str, ...]
    behavior: str
    arrival: str

    def variant_for(self, issue_number: int) -> str:
        """Deterministic colour choice: yarn alternates pink / blue by issue number."""
        return self.variants[issue_number % len(self.variants)]

    def to_json(self) -> dict:
        return {
            "label": self.label,
            "action": self.action,
            "lifetime_hours": int(self.lifetime.total_seconds() // 3600),
            "variants": list(self.variants),
            "behavior": self.behavior,
            "arrival": self.arrival,
        }


@dataclass(frozen=True)
class ToyRules:
    title_prefix: str
    cooldown: timedelta
    max_visible: int
    history: timedelta
    exempt_logins: frozenset[str]
    kinds: dict[str, ToyKind]

    @classmethod
    def from_dict(cls, raw: dict) -> "ToyRules":
        if not isinstance(raw, dict):
            raise ValueError("config/toys.json must hold an object")
        prefix = raw.get("title_prefix")
        if not isinstance(prefix, str) or not (3 <= len(prefix) <= 24) or not prefix.strip() == prefix:
            raise ValueError("title_prefix must be 3–24 characters without outer spaces")
        cooldown = timedelta(hours=_whole(raw, "cooldown_hours", 1, 24 * 14))
        history = timedelta(days=_whole(raw, "history_days", 1, 365))
        if history < cooldown + timedelta(days=1):
            raise ValueError("history_days must outlast cooldown_hours by at least a day, or cooldowns are forgotten")
        exempt = raw.get("exempt_logins", [])
        if not isinstance(exempt, list) or not all(isinstance(x, str) for x in exempt):
            raise ValueError("exempt_logins must be a list of logins")
        toys = raw.get("toys")
        if not isinstance(toys, dict) or not toys:
            raise ValueError("toys must define at least one toy")
        kinds = {}
        for key, spec in toys.items():
            if not KEY_RE.fullmatch(key) or not isinstance(spec, dict):
                raise ValueError(f"toy key {key!r} must be 2–16 lowercase letters")
            lifetime = timedelta(hours=_whole(spec, "lifetime_hours", 1, int(MAX_LIFETIME.total_seconds() // 3600)))
            variants = spec.get("variants") or ["default"]
            if not isinstance(variants, list) or not all(isinstance(v, str) and KEY_RE.fullmatch(v) for v in variants):
                raise ValueError(f"toy {key!r}: variants must be lowercase words")
            kinds[key] = ToyKind(
                key=key,
                label=_words(spec, "label", 40),
                action=_words(spec, "action", 40),
                lifetime=lifetime,
                variants=tuple(variants),
                behavior=_words(spec, "behavior", 60),
                arrival=_words(spec, "arrival", 200),
            )
        return cls(
            title_prefix=prefix,
            cooldown=cooldown,
            max_visible=_whole(raw, "max_visible", 1, 12),
            history=history,
            exempt_logins=frozenset(x.lower() for x in exempt),
            kinds=kinds,
        )

    def to_json(self) -> dict:
        """The public view of the rules, copied to the website so it shows exactly what the server enforces."""
        return {
            "title_prefix": self.title_prefix,
            "cooldown_hours": int(self.cooldown.total_seconds() // 3600),
            "max_visible": self.max_visible,
            "history_days": self.history.days,
            "toys": {k: v.to_json() for k, v in self.kinds.items()},
        }


def load_rules(path: Path) -> ToyRules:
    return ToyRules.from_dict(read_json(path))


def _whole(raw: dict, key: str, lo: int, hi: int) -> int:
    value = raw.get(key)
    if not isinstance(value, int) or isinstance(value, bool) or not lo <= value <= hi:
        raise ValueError(f"{key} must be a whole number between {lo} and {hi}")
    return value


def _words(raw: dict, key: str, limit: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f"{key} must be text of at most {limit} characters")
    return value.strip()
