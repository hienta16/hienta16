"""The cat's toy box as a README image: the cat on her rug with the toys visitors gave, and the box's numbers.

Drawn from data/toys.json after every accepted gift and on every refresh (so expired toys disappear).
Only toys accepted by the workflow are drawn; nothing here comes straight from an issue.
"""

from __future__ import annotations

from datetime import datetime

from ..config import Paths, SiteConfig
from ..toys.engine import visible
from ..toys.models import ToyState
from ..toys.rules import ToyRules
from ..timeutil import duration_words
from . import art
from .svg import document, f, text
from .theme import CREAM, INK, INK_2, PALE, PINK

# Where toys land on the rug, nearest the cat first (x centre, y of the toy's bottom edge)
SLOTS = (
    (300, 396), (690, 402), (190, 438), (770, 440), (414, 452), (584, 456),
    (110, 404), (860, 410), (500, 472), (262, 478), (730, 480), (610, 412),
)


def _toy_art(toy: str, variant: str) -> str:
    return f"toy-yarn-{variant}" if toy == "yarn" else f"toy-{toy}"


def render(paths: Paths, site: SiteConfig, rules: ToyRules, state: ToyState, now: datetime) -> str:
    W, H = 1200, 500
    live = visible(state, now)[-rules.max_visible :]
    given = sum(state.totals.values())

    rug = (
        f'<ellipse cx="492" cy="440" rx="420" ry="58" fill="{CREAM}"/>'
        f'<ellipse cx="492" cy="440" rx="370" ry="44" fill="none" stroke="{PINK}" stroke-width="5" stroke-dasharray="2 12" stroke-linecap="round"/>'
        f'<ellipse cx="492" cy="440" rx="300" ry="32" fill="none" stroke="{PALE}" stroke-width="7"/>'
    )
    cat_w = 214
    cat_h = art.height_for(paths, "tortie-front", cat_w)
    cat = art.place(paths, "tortie-front" if live else "tortie-sleep", 492 - cat_w / 2, 452 - cat_h, cat_w, "cat")

    toys = []
    for gift, (x, y) in zip(reversed(live), SLOTS):
        size = 86 if gift.toy == "box" else 62
        h = art.height_for(paths, _toy_art(gift.toy, gift.variant), size, 1.0)
        toys.append(art.place(paths, _toy_art(gift.toy, gift.variant), x - size / 2, y - h, size, f"t{gift.issue}"))
        toys.append(text(x, y + 16, f"@{gift.giver.login}", "text", 12.5, INK, "middle"))

    if live:
        note = ""
    elif site.toys_live:
        note = text(492, 168, "The box is empty. Be the first to give a toy.", "bold", 22, INK, "middle")
    else:
        note = text(492, 168, "The toy box opens when this profile goes public.", "bold", 22, INK, "middle")

    side_x = 952
    lifetimes = "".join(
        text(side_x, 318 + i * 30, f"{k.label} · {duration_words(k.lifetime)}", "text", 16, INK) for i, k in enumerate(rules.kinds.values())
    )
    side = (
        f'<rect x="{side_x - 28}" y="36" width="{W - side_x - 8}" height="{H - 72}" rx="22" fill="{CREAM}"/>'
        + text(side_x, 88, "In the box now", "label", 13, INK_2)
        + text(side_x, 146, str(len(live)), "black", 60, INK)
        + text(side_x, 196, "Given so far", "label", 13, INK_2)
        + text(side_x, 254, f"{given:,}", "black", 60, INK)
        + text(side_x, 294, "How long toys stay", "label", 13, INK_2)
        + lifetimes
        + text(side_x, 424, "One gift per account", "text", 13.5, INK_2)
        + text(side_x, 442, f"every {duration_words(rules.cooldown)}", "text", 13.5, INK_2)
    )
    body = (
        f'<rect width="{W}" height="{H}" rx="28" fill="{PINK}"/>'
        + text(44, 78, "The cat's toy box", "black", 40, INK)
        + text(44, 112, "Give Hien's cat a toy with a GitHub issue. Each toy stays a while, then goes back on the shelf.", "text", 17, INK)
        + rug
        + cat
        + "".join(toys)
        + note
        + side
    )
    names = ", ".join(f"{g.toy} from @{g.giver.login}" for g in live) or "no toys yet"
    return document(
        paths,
        W,
        H,
        body,
        title="The cat's toy box",
        desc=f"Hien's tortoiseshell cat on a rug with {len(live)} toy(s): {names}. {given} gifts so far.",
    )


__all__ = ["render", "SLOTS", "f"]
assert len(SLOTS) >= 12, "one place on the rug for every toy the rules allow"
