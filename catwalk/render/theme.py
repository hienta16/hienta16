"""Electric Baby Pop: the one palette shared by the README images and the website (src/styles/base.css).

Text pairings (WCAG 2): ink on cream 15.4:1 · ink on pale 12.8 · ink on pink 7.4 · ink on orange 5.5 ·
cream on ink 15.4 · orange on ink 5.5 · pink on ink 7.4 · white on blue 5.0. Orange is never text on cream.
"""

from __future__ import annotations

CREAM = "#FFF9F4"
PINK = "#F49CB6"
BLUE = "#2463F6"
ORANGE = "#FF7029"
PALE = "#FFE5EE"
INK = "#22243A"
WHITE = "#FFFFFF"
INK_2 = "#4E4F63"  # secondary text on light fields
INK_3 = "#2C2F4A"  # a step up from ink, surfaces on the ink field
NIGHT_2 = "#C9CAD8"  # secondary text on ink

# The five contribution levels (see catwalk.stats.calendar.LEVELS): an empty day, then pale pink to orange.
LEVEL_TOP = ("#383B5C", "#FFE5EE", "#F9C2D3", "#F49CB6", "#FF7029")

# Toys
YARN = {"pink": ("#F49CB6", "#D9708F", "#FFE5EE"), "blue": ("#2463F6", "#1A47B8", "#8DB0FF")}
FEATHER = ("#FF7029", "#FFB089", "#C94E16")
KRAFT = ("#D9A066", "#C18447", "#9E6A35", "#F0C48E")


def mix(a: str, b: str, k: float) -> str:
    """Blend colour `a` toward `b` by k (0 … 1)."""
    ca = [int(a[i : i + 2], 16) for i in (1, 3, 5)]
    cb = [int(b[i : i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(x + (y - x) * k):02X}" for x, y in zip(ca, cb))
