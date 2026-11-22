"""README buttons drawn in the site's style (instead of third-party badges), so the profile reads as one system."""

from __future__ import annotations

from ..config import Paths, SiteConfig
from ..toys.rules import ToyRules
from . import art
from .svg import document, f, measure, text
from .theme import BLUE, CREAM, INK, ORANGE, PINK, WHITE

TOY_FILL = {"yarn": PINK, "feather": ORANGE, "box": "#F0C48E"}
TOY_ART = {"yarn": "toy-yarn-pink", "feather": "toy-feather", "box": "toy-box"}


def pill(paths: Paths, label: str, fill: str, ink: str, *, icon: str | None = None, dot: str | None = None, arrow: bool = False) -> str:
    h, size = 48, 18
    lead = 52 if icon else (34 if dot else 22)
    tail = 40 if arrow else 22
    w = lead + measure(paths, label, "bold", size) + tail
    parts = [f'<rect x="1" y="1" width="{f(w - 2)}" height="{h - 2}" rx="{(h - 2) / 2}" fill="{fill}" stroke="{INK}" stroke-width="2"/>']
    if icon:
        parts.append(art.place(paths, icon, 12, 7, 34, "i"))
    if dot:
        parts.append(f'<circle cx="21" cy="{h / 2}" r="6" fill="{dot}"/>')
    parts.append(text(lead, 31, label, "bold", size, ink))
    if arrow:
        x = w - 30
        parts.append(f'<path d="M{f(x)} 30l10-10m-7 0h7v7" stroke="{ink}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round"/>')
    return document(paths, w, h, "".join(parts), title=label, desc=f"Button: {label}")


def render_all(paths: Paths, site: SiteConfig, rules: ToyRules) -> dict[str, str]:
    out = {
        "btn-site.svg": pill(paths, site.site_url.removeprefix("https://"), INK, CREAM, dot=ORANGE, arrow=True),
        "btn-linkedin.svg": pill(paths, "LinkedIn", BLUE, WHITE, arrow=True),
    }
    for key, kind in rules.kinds.items():
        out[f"btn-{key}.svg"] = pill(paths, kind.action, TOY_FILL.get(key, CREAM), INK, icon=TOY_ART.get(key))
    return out
