"""Embed the illustrated art (the tortoiseshell cat, the ruler cat, the toys) into generated SVGs.

The art is drawn once, as React components on the website (src/components/TortieCat.tsx, Cat.tsx), because there
it moves and reacts. `npm run export:art` in the website repository renders static copies into assets/art/ here.
This module nests those files inside the README images, prefixing their ids so two copies never clash.
If a file is missing (a fresh checkout before the export), a simple silhouette stands in, so rendering never fails.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from ..config import Paths
from .svg import f
from .theme import INK, ORANGE

_VIEWBOX = re.compile(r'viewBox="([\d.\s-]+)"')
_ID = re.compile(r'\bid="([^"]+)"')


@dataclass(frozen=True)
class Art:
    name: str
    box: tuple[float, float, float, float]
    inner: str

    @property
    def ratio(self) -> float:
        return self.box[3] / self.box[2]


@lru_cache(maxsize=32)
def _read(path: str) -> Art | None:
    p = Path(path)
    if not p.exists():
        return None
    raw = p.read_text(encoding="utf-8")
    vb = _VIEWBOX.search(raw)
    start, end = raw.find(">", raw.find("<svg")) + 1, raw.rfind("</svg>")
    if not vb or start <= 0 or end < start:
        return None
    x, y, w, h = (float(v) for v in vb.group(1).split())
    return Art(p.stem, (x, y, w, h), raw[start:end])


def load(paths: Paths, name: str) -> Art | None:
    return _read(str(paths.art / f"{name}.svg"))


def place(paths: Paths, name: str, x: float, y: float, width: float, prefix: str, *, extra: str = "") -> str:
    """The art `name` as a nested <svg> at (x, y), `width` wide, height from its own proportions."""
    art = load(paths, name)
    if art is None:
        return _fallback(name, x, y, width)
    ids = set(_ID.findall(art.inner))
    inner = art.inner
    if ids:
        pattern = re.compile(r'(\bid="|url\(#|href="#)(' + "|".join(re.escape(i) for i in sorted(ids, key=len, reverse=True)) + r')(?=["\)])')
        inner = pattern.sub(lambda m: f"{m.group(1)}{prefix}-{m.group(2)}", inner)
    bx, by, bw, bh = art.box
    height = width * art.ratio
    return (
        f'<svg x="{f(x)}" y="{f(y)}" width="{f(width)}" height="{f(height)}" viewBox="{f(bx)} {f(by)} {f(bw)} {f(bh)}" '
        f'overflow="visible"{(" " + extra) if extra else ""}>{inner}</svg>'
    )


def height_for(paths: Paths, name: str, width: float, default_ratio: float = 1.19) -> float:
    art = load(paths, name)
    return width * (art.ratio if art else default_ratio)


def _fallback(name: str, x: float, y: float, width: float) -> str:
    h = width * 1.19
    cx = x + width / 2
    return (
        f'<g data-fallback="{name}"><ellipse cx="{f(cx)}" cy="{f(y + h * 0.72)}" rx="{f(width * 0.36)}" ry="{f(h * 0.27)}" fill="{INK}"/>'
        f'<circle cx="{f(cx)}" cy="{f(y + h * 0.36)}" r="{f(width * 0.26)}" fill="{INK}"/>'
        f'<circle cx="{f(cx - width * 0.09)}" cy="{f(y + h * 0.34)}" r="{f(width * 0.05)}" fill="{ORANGE}"/>'
        f'<circle cx="{f(cx + width * 0.09)}" cy="{f(y + h * 0.34)}" r="{f(width * 0.05)}" fill="{ORANGE}"/></g>'
    )
