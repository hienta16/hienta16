"""Load and save data/toys.json. A missing file means an empty toy box; a corrupt one stops the run."""

from __future__ import annotations

from pathlib import Path

from ..jsonio import read_json, write_json
from .models import ToyState
from .rules import ToyRules


def load_state(path: Path, rules: ToyRules) -> ToyState:
    if not Path(path).exists():
        return ToyState.empty(list(rules.kinds))
    return ToyState.from_json(read_json(path), list(rules.kinds))


def save_state(path: Path, state: ToyState) -> bool:
    """Write the state; returns True when the file changed."""
    return write_json(path, state.to_json())
