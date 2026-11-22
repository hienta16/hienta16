"""The contribution beat as an animated image: every day since my first contribution is one step, busier days
are taller, and a play-head sweeps across them on a loop (pure CSS, so it plays inside the README).

The sound version is on the website, where a visitor presses play: GitHub's README cannot (and should not)
play audio. The image honours prefers-reduced-motion by standing still.
"""

from __future__ import annotations

from math import sqrt

from ..config import SiteConfig, Paths
from ..stats.calendar import Calendar
from .svg import document, f, text
from .theme import BLUE, CREAM, INK, ORANGE, PINK, WHITE

STEP_SECONDS = 0.11  # the website plays one step every ~112 ms; the image keeps the same tempo


def render(paths: Paths, cal: Calendar, site: SiteConfig) -> str:
    W, H = 1200, 260
    days = cal.days()
    first = next((d for d in days if d.count > 0), None)
    run = days[first.index :] if first else []
    x0, x1, base, tall = 44, W - 44, 222, 92
    pills = []
    css = ""
    if run:
        top = max(d.count for d in run)
        step = (x1 - x0) / len(run)
        pw = max(2.0, min(10.0, step * 0.62))
        period = len(run) * STEP_SECONDS + 1.6
        for i, d in enumerate(run):
            cx = x0 + step * i + step / 2
            delay = i * STEP_SECONDS - period
            if d.count:
                h = 10 + (tall - 10) * sqrt(d.count / top)
                pills.append(
                    f'<rect class="p" x="{f(cx - pw / 2)}" y="{f(base - h)}" width="{f(pw)}" height="{f(h)}" rx="{f(pw / 2)}" '
                    f'fill="{CREAM}" style="animation-delay:{delay:.2f}s"/>'
                )
            else:
                pills.append(f'<circle cx="{f(cx)}" cy="{base - 3}" r="2.2" fill="{CREAM}" opacity=".45"/>')
        css = (
            f".p{{transform-box:fill-box;transform-origin:50% 100%;animation:hit {period:.2f}s linear infinite}}"
            f"@keyframes hit{{0%{{fill:{ORANGE};transform:scaleY(1.16)}}5%{{fill:{PINK};transform:scaleY(1)}}"
            f"55%{{fill:{PINK}}}70%,100%{{fill:{CREAM}}}}}"
            "@media (prefers-reduced-motion:reduce){.p{animation:none}}"
        )
    else:
        pills.append(text(x0, base - 20, "No contributions in the last year yet: the beat starts with the first one.", "text", 17, WHITE))

    span = f"{run[0].date.day} {run[0].date:%b} – {run[-1].date.day} {run[-1].date:%b %Y} · {len(run)} steps" if run else ""
    body = (
        f'<rect width="{W}" height="{H}" rx="28" fill="{BLUE}"/>'
        + text(44, 64, "Contribution beat", "black", 34, WHITE)
        + text(44, 94, "Every day since my first contribution is one step; busier days hit harder.", "text", 17, WHITE)
        + text(x1, 64, span, "bold", 18, WHITE, "end")
        + text(x1, 94, f"Press play with sound at {site.site_url.removeprefix('https://')}", "text", 15, WHITE, "end")
        + "".join(pills)
        + f'<path d="M{x0} {base + 12}H{x1}" stroke="{WHITE}" stroke-opacity=".35" stroke-width="2"/>'
    )
    return document(
        paths,
        W,
        H,
        body,
        title="Contribution beat",
        desc=f"An animated strip: one step per day since my first contribution ({len(run)} days), taller on busier days.",
        css=css,
    )


__all__ = ["render", "INK"]
