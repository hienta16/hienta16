"""Tiny SVG toolkit: escaping, number formatting, the embedded font, text measurement, and the document shell.

Every generated image is self-contained (font included as base64), because GitHub serves README images through
its image proxy, which blocks external fonts and scripts. CSS animations inside the SVG still play.
"""

from __future__ import annotations

import base64
import json
from functools import lru_cache
from html import escape
from pathlib import Path
from typing import Iterable

from ..config import Paths


def esc(value: object) -> str:
    """Escape text for SVG/XML content and attribute values."""
    return escape(str(value), quote=True)


def f(value: float) -> str:
    """Compact coordinates: 12.0 -> '12', 3.14159 -> '3.14'."""
    text = f"{value:.2f}".rstrip("0").rstrip(".")
    return "0" if text in ("-0", "", "-") else text


def pts(points: Iterable[tuple[float, float]]) -> str:
    return " ".join(f"{f(x)},{f(y)}" for x, y in points)


@lru_cache(maxsize=4)
def _font_data(fonts_dir: str) -> str:
    path = Path(fonts_dir) / "anybody-subset.woff2"
    return base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else ""


def font_css(paths: Paths) -> str:
    data = _font_data(str(paths.fonts))
    if not data:
        return ""
    return (
        "@font-face{font-family:'Anybody';font-weight:100 900;font-stretch:50% 150%;"
        f"src:url(data:font/woff2;base64,{data}) format('woff2');}}"
    )


DISPLAY = "Anybody,'Arial Narrow',Arial,sans-serif"
TEXT = "-apple-system,BlinkMacSystemFont,'Segoe UI',Helvetica,Arial,sans-serif"

# Text styles. The names match assets/fonts/anybody-metrics.json, so measure() knows their glyph widths.
STYLE_CSS = {
    "black": "font-family:" + DISPLAY + ";font-weight:850;font-stretch:100%;",
    "bold": "font-family:" + DISPLAY + ";font-weight:760;font-stretch:88%;",
    "label": "font-family:" + DISPLAY + ";font-weight:700;font-stretch:76%;letter-spacing:.06em;text-transform:uppercase;",
    "text": "font-family:" + TEXT + ";font-weight:500;",
}


@lru_cache(maxsize=4)
def _metrics(fonts_dir: str) -> dict:
    path = Path(fonts_dir) / "anybody-metrics.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def measure(paths: Paths, text: str, style: str, size: float, tracking: float = 0.0) -> float:
    """Width of `text` in px at `size`, from recorded advance widths. Falls back to an average glyph width."""
    m = _metrics(str(paths.fonts))
    if style == "label":
        text = text.upper()
        tracking = tracking or 0.06
    spec = (m.get("styles") or {}).get(style)
    if not spec:
        return len(text) * size * (0.5 if style != "black" else 0.58)
    upem = m.get("unitsPerEm", 1000)
    adv = spec["advances"]
    width = sum(adv.get(ch, spec["fallback"]) for ch in text) / upem * size
    return width + tracking * size * max(0, len(text) - 1)


def classes_css(extra: str = "") -> str:
    base = "".join(f".{name}{{{css}}}" for name, css in STYLE_CSS.items())
    return base + extra


def document(
    paths: Paths,
    width: float,
    height: float,
    body: str,
    *,
    title: str,
    desc: str,
    css: str = "",
    with_font: bool = True,
) -> str:
    style = (font_css(paths) if with_font else "") + classes_css(css)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{f(width)}" height="{f(height)}" '
        f'viewBox="0 0 {f(width)} {f(height)}" role="img" aria-labelledby="title desc" fill="none">'
        f'<title id="title">{esc(title)}</title><desc id="desc">{esc(desc)}</desc>'
        f"<style>{style}</style>{body}</svg>\n"
    )


def text(x: float, y: float, content: str, cls: str, size: float, fill: str, anchor: str = "start", extra: str = "") -> str:
    return (
        f'<text x="{f(x)}" y="{f(y)}" class="{cls}" font-size="{f(size)}" fill="{fill}" '
        f'text-anchor="{anchor}"{(" " + extra) if extra else ""}>{esc(content)}</text>'
    )
