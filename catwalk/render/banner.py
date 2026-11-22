"""The profile banner: the hello, the role, the tortoiseshell cat in her blue circle, and the measuring tape
along the bottom with the little ruler cat walking it (the same tape that tops every page of the website).
"""

from __future__ import annotations

from ..config import Paths, SiteConfig
from . import art
from .svg import document, f, measure, text
from .theme import BLUE, CREAM, INK, INK_2, ORANGE, PINK

INTRO = (
    "I find patterns: in datasets, in playlists, and in the way",
    "a cat studies a room before it moves.",
)


def render(paths: Paths, site: SiteConfig) -> str:
    W, H = 1200, 430
    hello = f"Hi, I'm {site.display_name}!"
    role_w = measure(paths, site.role, "black", 44) + 36
    tape_y = 384

    cat_w = 262
    cat_h = art.height_for(paths, "tortie-front", cat_w)
    disc_cx, disc_cy, disc_r = 952, 192, 158
    cat_x, cat_y = disc_cx - cat_w / 2, disc_cy + disc_r - cat_h + 22

    ticks = []
    for i, x in enumerate(range(0, W + 1, 12)):
        long = i % 10 == 0
        ticks.append(f"M{x} {tape_y}v{14 if long else (9 if i % 5 == 0 else 6)}")
    numbers = "".join(
        text(x + 4, tape_y + 34, str(i * 10), "label", 11, INK) for i, x in enumerate(range(0, W, 120)) if i
    )

    css = (
        ".walker{animation:walk 26s linear infinite}"
        "@keyframes walk{from{transform:translateX(-90px)}to{transform:translateX(1210px)}}"
        ".rcat__leg{transform-box:fill-box;transform-origin:50% 0}"
        ".rcat--walk .rcat__leg--a{animation:leg .38s linear infinite}"
        ".rcat--walk .rcat__leg--b{animation:leg .38s linear infinite reverse}"
        "@keyframes leg{0%,100%{transform:rotate(-24deg)}50%{transform:rotate(24deg)}}"
        ".blink{animation:blink 6s infinite}"
        "@keyframes blink{0%,94%,100%{opacity:0}96%{opacity:1}}"
        "@media (prefers-reduced-motion:reduce){.walker,.rcat__leg--a,.rcat__leg--b{animation:none}.walker{transform:translateX(980px)}}"
    )
    body = (
        f'<rect width="{W}" height="{H}" rx="28" fill="{CREAM}"/>'
        # the cat in her circle, with a status pill
        + f'<circle cx="{disc_cx}" cy="{disc_cy}" r="{disc_r}" fill="{BLUE}"/>'
        + f'<circle cx="{disc_cx - 118}" cy="{disc_cy - 112}" r="16" fill="{PINK}"/>'
        + f'<circle cx="{disc_cx + 150}" cy="{disc_cy - 40}" r="9" fill="{ORANGE}"/>'
        + art.place(paths, "tortie-front", cat_x, cat_y, cat_w, "cat")
        + f'<rect x="{disc_cx - 214}" y="{disc_cy + 98}" width="186" height="38" rx="19" fill="{INK}"/>'
        + f'<circle cx="{disc_cx - 194}" cy="{disc_cy + 117}" r="6" fill="{ORANGE}"/>'
        + text(disc_cx - 180, disc_cy + 123, "Untangling a dataset", "text", 14.5, CREAM)
        # the words
        + text(56, 148, hello, "black", 78, INK)
        + f'<rect x="56" y="178" width="{f(role_w)}" height="66" rx="14" fill="{ORANGE}"/>'
        + text(74, 228, site.role, "black", 44, INK)
        + text(58, 296, INTRO[0], "text", 21, INK_2)
        + text(58, 326, INTRO[1], "text", 21, INK_2)
        # the measuring tape and the ruler cat walking it
        + f'<path d="M0 {tape_y}H{W}V{H - 28}a28 28 0 0 1-28 28H28a28 28 0 0 1-28-28z" fill="{PINK}"/>'
        + f'<path d="{"".join(ticks)}" stroke="{INK}" stroke-width="1.6"/>'
        + numbers
        + f'<g class="walker">{art.place(paths, "ruler-walk", 0, tape_y - 44, 72, "ruler")}</g>'
    )
    return document(
        paths,
        W,
        H,
        body,
        title=f"Hi, I'm {site.display_name}! {site.role}.",
        desc=(
            f"{site.display_name}, {site.role}. A tortoiseshell cat with yellow-green eyes sits in a blue circle; "
            "a small cat walks along a pink measuring tape."
        ),
        css=css,
    )
