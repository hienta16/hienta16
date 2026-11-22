"""The contribution year as an isometric calendar on a slab: one block per day, the slab's front edge a pink
measuring tape with week ticks and month names.

Design choices (v3):
* Camera: the grid is turned 18° and seen from 40° above, so the year runs gently down to the right instead of
  a steep diagonal. Weekday rows recede; the tops of the blocks stay readable as a grid.
* Height is the data (see column_height): linear in each day's real contribution count, scaled so the busiest day
  in the displayed range stands MAX_H cells tall (about 55-60 px on a desktop screen, roughly 1.5 cm). Colour still
  follows the five legend levels, so two days of the same colour can differ in height. No peak is labelled.
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
# Column heights, in cell widths (one cell = one day's footprint). The busiest day is meant to stand about
# 55-60 px on a desktop screen (roughly 1.5 cm). The two surfaces draw cells at different sizes, so each has its own:
MAX_H_SITE = 5.6  # website dashboard at 1440 px: one cell height = ~10.4 px, so the busiest day is ~58 px
MAX_H_README = 4.9  # README card shown ~896 px wide on github.com: one cell height = ~11.8 px, so ~58 px
MAX_H = MAX_H_SITE
MIN_H = 0.3  # any day with a contribution stands at least this tall (~3 px), so it never sinks into the slab
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


def column_height(count: int, busiest: int, max_h: float = MAX_H) -> float:
    """How tall a day's column stands, in cell widths. Deterministic and linear in the real count:

        h = max_h * count / busiest        busiest = the highest daily count in the displayed range
        h = max(h, MIN_H)                  for any day with at least one contribution
        h = 0                              for a day with none (a flat tile on the slab)

    So the busiest day is exactly max_h tall, a day with half its count is half as tall, and a quiet day with one or
    two contributions still clears the slab. Nothing is stepped, so equal colours do not mean equal heights.
    """
    if count <= 0 or busiest <= 0:
        return 0.0
    return max(MIN_H, max_h * min(count, busiest) / busiest)


def _busiest(cal: Calendar) -> int:
    return max(cal.counts, default=0)


def _cell(cal: Calendar, day: Day) -> tuple[float, float, float, float]:
    wk = cal.week_of(day)
    return wk + GAP, wk + 1 - GAP, day.row + GAP, day.row + 1 - GAP


def _extent(cal: Calendar, p: Projection, max_h: float) -> tuple[float, float, float, float]:
    """The drawing's bounding box: the slab plus the actual tops of the columns (not a worst case)."""
    w = cal.weeks
    u0, u1, v0, v1 = -SLAB_PAD, w + SLAB_PAD, -SLAB_PAD, 7 + SLAB_PAD
    points = [p(u0, v0), p(u1, v0), p(u0, v1, -SLAB_DEPTH), p(u1, v1, -SLAB_DEPTH), p(u0, v1), p(u1, v0)]
    busiest = _busiest(cal)
    for day in cal.days():
        h = column_height(day.count, busiest, max_h)
        if h:
            a0, a1, b0, b1 = _cell(cal, day)
            points += [p(a0, b0, h), p(a1, b0, h), p(a0, b1, h), p(a1, b1, h)]
    xs, ys = [c[0] for c in points], [c[1] for c in points]
    return min(xs), min(ys), max(xs), max(ys)


def draw(cal: Calendar, p: Projection, *, interactive: bool, max_h: float) -> str:
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
    busiest = _busiest(cal)
    out.append('<g class="iso-blocks">')
    for day in order:
        out.append(_block(cal, day, p, interactive, busiest, max_h))
    out.append("</g>")
    return "".join(out)


def _block(cal: Calendar, day: Day, p: Projection, interactive: bool, busiest: int, max_h: float) -> str:
    level = level_of(day.count)
    wk = cal.week_of(day)
    a0, a1, b0, b1 = _cell(cal, day)
    h = column_height(day.count, busiest, max_h)
    top = LEVEL_TOP[level]
    faces = []
    if h > 0:
        faces.append((pts([p(a0, b1, h), p(a1, b1, h), p(a1, b1), p(a0, b1)]), mix(top, INK, 0.22), "f"))
        faces.append((pts([p(a1, b0, h), p(a1, b1, h), p(a1, b1), p(a1, b0)]), mix(top, INK, 0.42), "s"))
    faces.append((pts([p(a0, b0, h), p(a1, b0, h), p(a1, b1, h), p(a0, b1, h)]), top, "t"))
    polys = "".join(f'<polygon points="{d}" fill="{c}" class="iso-{k}"/>' for d, c, k in faces)
    if not interactive:
        return polys
    base = p((a0 + a1) / 2, (b0 + b1) / 2)
    return (
        f'<g class="iso-b iso-l{level}" data-date="{day.date.isoformat()}" data-count="{day.count}" '
        f'style="--w:{wk};transform-origin:{f(base[0])}px {f(base[1])}px">{polys}</g>'
    )


def scene(cal: Calendar, scale: float, *, interactive: bool, max_h: float = MAX_H_SITE) -> Scene:
    p = Projection(scale)
    x0, y0, x1, y1 = _extent(cal, p, max_h)
    pad = scale * 0.35
    p = p.moved(-x0 + pad, -y0 + pad)
    return Scene(draw(cal, p, interactive=interactive, max_h=max_h), 0, 0, x1 - x0 + 2 * pad, y1 - y0 + 2 * pad)


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
    x0, y0, x1, y1 = _extent(cal, p, MAX_H_README)
    total = f"{cal.total:,}"
    head_h = 118
    # Headline in the empty top-right corner: push the year down only as far as the corner needs.
    title_w = measure(paths, "A year in blocks", "black", 44)
    head_left = W - margin - max(title_w, 360)
    # The headline sits in the empty top-right corner. Find the highest column top (or slab corner) under it and
    # push the drawing down only as far as needed to keep them apart.
    busiest = _busiest(cal)
    under: list[float] = [p(cal.weeks + SLAB_PAD, -SLAB_PAD)[1]]
    for day in cal.days():
        h = column_height(day.count, busiest, MAX_H_README)
        a0, a1, b0, b1 = _cell(cal, day)
        for pt in (p(a0, b0, h), p(a1, b0, h)):
            if pt[0] - x0 + margin >= head_left - 12:
                under.append(pt[1])
    drop = min(under) - y0
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
        + draw(cal, p, interactive=False, max_h=MAX_H_README)
        + text(W - margin, margin + 46, "A year in blocks", "black", 44, CREAM, "end")
        + text(W - margin, margin + 76, f"{total} contributions · {_span(cal)}", "bold", 18, PINK, "end")
        + "".join(legend)
        + text(margin, H - 30, f"One block per day · height = that day's contributions · colour levels {ranges} · refreshed {refreshed}", "text", 14, NIGHT_2)
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


__all__ = ["readme_svg", "site_svg", "scene", "column_height", "Projection", "MAX_H", "MAX_H_README", "MAX_H_SITE", "MIN_H", "INK_3"]
