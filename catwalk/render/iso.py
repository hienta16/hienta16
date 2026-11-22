"""The contribution year as an isometric calendar on a slab: one block per day, the slab's front edge a pink
measuring tape with week ticks and month names.

Design choices (v3):
* Camera: the grid is turned 18° and seen from 40° above, so the year runs gently down to the right instead of
  a steep diagonal. Weekday rows recede; the tops of the blocks stay readable as a grid.
* Height is stepped by level (the same five levels as the legend) and kept low: the busiest level stands just under
  one cell tall, so a single busy day cannot tower over the year. No peak is labelled.
* Faces are shaded from the level colour toward ink (top lit, front a step darker, side darker still).

Two variants share the geometry:
* readme  a self-contained card (ink panel, headline, legend, refresh time) for the GitHub profile
* site    the bare drawing with data attributes; the website adds the headline, hover tooltips and the rise animation
"""

from __future__ import annotations

from dataclasses import dataclass
from math import cos, hypot, radians, sin

from ..config import Paths
from ..stats.calendar import LEVELS, Calendar, Day, level_of
from .svg import STYLE_CSS, document, esc, f, measure, pts, text
from .theme import CREAM, INK, INK_3, LEVEL_TOP, NIGHT_2, PINK, mix

THETA = radians(18)
PHI = radians(40)
GAP = 0.14
LEVEL_H = (0.0, 0.24, 0.42, 0.64, 0.9)
SLAB_DEPTH = 0.82
SLAB_PAD = 0.42
SLAB_TOP = "#2C2F4A"
SLAB_SIDE = "#1B1D30"
MONTHS = ("JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC")


@dataclass(frozen=True)
class Projection:
    scale: float
    ox: float = 0.0
    oy: float = 0.0

    def __call__(self, u: float, v: float, h: float = 0.0) -> tuple[float, float]:
        ct, st, sp, cp = cos(THETA), sin(THETA), sin(PHI), cos(PHI)
        return (self.ox + (u * ct - v * st) * self.scale, self.oy + ((u * st + v * ct) * sp - h * cp) * self.scale)

    def moved(self, dx: float, dy: float) -> "Projection":
        return Projection(self.scale, self.ox + dx, self.oy + dy)


@dataclass(frozen=True)
class Scene:
    body: str
    min_x: float
    min_y: float
    max_x: float
    max_y: float

    @property
    def width(self) -> float:
        return self.max_x - self.min_x

    @property
    def height(self) -> float:
        return self.max_y - self.min_y


def _extent(cal: Calendar, p: Projection) -> tuple[float, float, float, float]:
    w = cal.weeks
    u0, u1, v0, v1 = -SLAB_PAD, w + SLAB_PAD, -SLAB_PAD, 7 + SLAB_PAD
    corners = [p(u0, v0, LEVEL_H[-1]), p(u1, v0, LEVEL_H[-1]), p(u0, v1, -SLAB_DEPTH), p(u1, v1, -SLAB_DEPTH), p(u0, v1, 0), p(u1, v0, 0)]
    xs, ys = [c[0] for c in corners], [c[1] for c in corners]
    return min(xs), min(ys), max(xs), max(ys)


def draw(cal: Calendar, p: Projection, *, interactive: bool) -> str:
    """The slab, the tape and the blocks, drawn back to front."""
    w = cal.weeks
    days = cal.days()
    u0, u1, v0, v1 = -SLAB_PAD, w + SLAB_PAD, -SLAB_PAD, 7 + SLAB_PAD
    d = -SLAB_DEPTH
    out = [
        f'<polygon class="iso-slab" points="{pts([p(u0, v0), p(u1, v0), p(u1, v1), p(u0, v1)])}" fill="{SLAB_TOP}"/>',
        f'<polygon class="iso-tape" points="{pts([p(u0, v1), p(u1, v1), p(u1, v1, d), p(u0, v1, d)])}" fill="{PINK}"/>',
        f'<polygon points="{pts([p(u1, v0), p(u1, v1), p(u1, v1, d), p(u1, v0, d)])}" fill="{SLAB_SIDE}"/>',
    ]
    # the tape: a tick per week, a longer one every four
    ticks = []
    for wk in range(w + 1):
        a, b = p(wk, v1, 0), p(wk, v1, -0.2 if wk % 4 else -0.34)
        ticks.append(f"M{f(a[0])} {f(a[1])}L{f(b[0])} {f(b[1])}")
    out.append(f'<path d="{"".join(ticks)}" stroke="{INK}" stroke-width="{f(p.scale * 0.045)}"/>')
    # month names printed on the tape: along the slab edge, upright on the face
    ct, st, sp = cos(THETA), sin(THETA), sin(PHI)
    ux, uy = ct, st * sp
    n = hypot(ux, uy)
    ux, uy = ux / n, uy / n
    for day in days:
        if day.date.day == 1 and day.index > 10:
            wk = cal.week_of(day)
            a, b = p(wk, v1, 0), p(wk, v1, d)
            at = p(wk + 0.22, v1, -SLAB_DEPTH * 0.82)
            out.append(f'<path d="M{f(a[0])} {f(a[1])}L{f(b[0])} {f(b[1])}" stroke="{INK}" stroke-width="{f(p.scale * 0.07)}"/>')
            out.append(
                f'<text class="iso-month" transform="matrix({f(ux)} {f(uy)} 0 1 {f(at[0])} {f(at[1])})" '
                f'font-size="{f(p.scale * 0.5)}" fill="{INK}">{MONTHS[day.date.month - 1]}</text>'
            )
    # blocks: back row first, left to right, so nearer blocks overlap farther ones
    order = sorted(days, key=lambda dd: (dd.row, cal.week_of(dd)))
    out.append('<g class="iso-blocks">')
    for day in order:
        out.append(_block(cal, day, p, interactive))
    out.append("</g>")
    return "".join(out)


def _block(cal: Calendar, day: Day, p: Projection, interactive: bool) -> str:
    level = level_of(day.count)
    wk = cal.week_of(day)
    a0, a1 = wk + GAP, wk + 1 - GAP
    b0, b1 = day.row + GAP, day.row + 1 - GAP
    h = LEVEL_H[level]
    top = LEVEL_TOP[level]
    faces = []
    if h > 0:
        faces.append((pts([p(a0, b1, h), p(a1, b1, h), p(a1, b1), p(a0, b1)]), mix(top, INK, 0.22), "f"))
        faces.append((pts([p(a1, b0, h), p(a1, b1, h), p(a1, b1), p(a1, b0)]), mix(top, INK, 0.42), "s"))
    faces.append((pts([p(a0, b0, h), p(a1, b0, h), p(a1, b1, h), p(a0, b1, h)]), top, "t"))
    polys = "".join(f'<polygon points="{d}" fill="{c}" class="iso-{k}"/>' for d, c, k in faces)
    if not interactive:
        return polys if h > 0 else polys
    base = p((a0 + a1) / 2, (b0 + b1) / 2)
    return (
        f'<g class="iso-b iso-l{level}" data-date="{day.date.isoformat()}" data-count="{day.count}" '
        f'style="--w:{wk};transform-origin:{f(base[0])}px {f(base[1])}px">{polys}</g>'
    )


def scene(cal: Calendar, scale: float, *, interactive: bool) -> Scene:
    p = Projection(scale)
    x0, y0, x1, y1 = _extent(cal, p)
    pad = scale * 0.35
    p = p.moved(-x0 + pad, -y0 + pad)
    return Scene(draw(cal, p, interactive=interactive), 0, 0, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)


def site_svg(cal: Calendar, *, scale: float = 18.0, label: str = "") -> str:
    """The website's drawing: no panel, no text but the tape; data-date / data-count on every block."""
    s = scene(cal, scale, interactive=True)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {f(s.width)} {f(s.height)}" class="iso-svg" role="img" '
        f'aria-label="{esc(label)}">{s.body}</svg>\n'
    )


def readme_svg(paths: Paths, cal: Calendar, *, refreshed: str, profile_url: str) -> str:
    W = 1200
    margin = 44
    scale = (W - 2 * margin) / ((cal.weeks + 2 * SLAB_PAD) * cos(THETA) + (7 + 2 * SLAB_PAD) * sin(THETA))
    p = Projection(scale)
    x0, y0, x1, y1 = _extent(cal, p)
    total = f"{cal.total:,}"
    head_h = 118
    # Headline in the empty top-right corner: push the year down only as far as the corner needs.
    title_w = measure(paths, "A year in blocks", "black", 44)
    head_left = W - margin - max(title_w, 360)
    # The back edge of the year (at the tallest possible block) slopes down to the right. Find how far below the
    # top of the drawing it passes under the headline's left edge, and push the drawing down only if it must.
    bl, br = p(-SLAB_PAD, -SLAB_PAD, LEVEL_H[-1]), p(cal.weeks + SLAB_PAD, -SLAB_PAD, LEVEL_H[-1])
    under = head_left - margin + x0
    drop = bl[1] + (under - bl[0]) / (br[0] - bl[0]) * (br[1] - bl[1]) - y0
    top = max(margin, margin + head_h + 18 - drop)
    p = p.moved(-x0 + margin, -y0 + top)
    body_h = (y1 - y0) + top
    H = round(body_h + 64)

    legend_x = W - margin
    sw = 15
    legend = []
    lx = legend_x - 5 * (sw + 5) - measure(paths, "More", "label", 12) - 8
    legend.append(text(lx - 8, margin + 104, "Less", "label", 12, NIGHT_2, "end"))
    for i, c in enumerate(LEVEL_TOP):
        legend.append(f'<rect x="{f(lx + i * (sw + 5))}" y="{f(margin + 92)}" width="{sw}" height="{sw}" rx="3" fill="{c}"/>')
    legend.append(text(legend_x, margin + 104, "More", "label", 12, NIGHT_2, "end"))
    ranges = " · ".join(f"{lo}" if hi == lo else (f"{lo}+" if hi is None else f"{lo}–{hi}") for lo, hi in LEVELS)

    body = (
        f'<rect width="{W}" height="{H}" rx="28" fill="{INK}"/>'
        + draw(cal, p, interactive=False)
        + text(W - margin, margin + 46, "A year in blocks", "black", 44, CREAM, "end")
        + text(W - margin, margin + 76, f"{total} contributions · {_span(cal)}", "bold", 18, PINK, "end")
        + "".join(legend)
        + text(margin, H - 30, f"One block per day · levels {ranges} · refreshed {refreshed}", "text", 14, NIGHT_2)
    )
    return document(
        paths,
        W,
        H,
        body,
        title=f"{total} GitHub contributions in the last year",
        desc=f"An isometric calendar of {profile_url}: one block per day from {cal.start} to {cal.end}, taller and warmer on busier days.",
        css=".iso-month{" + STYLE_CSS["label"] + "}",
    )


def _span(cal: Calendar) -> str:
    a, b = cal.start, cal.end
    return f"{a.day} {a:%b %Y} – {b.day} {b:%b %Y}"


__all__ = ["readme_svg", "site_svg", "scene", "Projection", "LEVEL_H", "INK_3"]
