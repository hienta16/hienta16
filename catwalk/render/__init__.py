"""Drawing: pure functions from the data files to SVG text. render_all() writes every image and README section.

    banner.svg       hello, the role, the tortoiseshell cat, the measuring tape with the ruler cat walking
    stats.svg        contributions, commits I authored, PRs, issues, streaks (with the refresh time)
    iso.svg          the 3D contribution year (README card)
    beat.svg         the contribution beat, animated (sound lives on the website)
    languages.svg    top languages by code size
    rhythm.svg       contributions by weekday
    toybox.svg       the cat's toy box with the toys visitors gave
    btn-*.svg        README buttons in the same style
    iso-site*.svg    the website's copy of the 3D year (bare drawing with data attributes)
"""

from __future__ import annotations

from datetime import datetime

from ..config import Paths, load_site_config
from ..jsonio import read_json, write_text
from ..stats.calendar import Calendar
from ..timeutil import human_utc, parse_ts, utcnow

ALL = ("banner", "stats", "iso", "beat", "languages", "rhythm", "toybox", "buttons", "site", "readme")


def render_all(paths: Paths, *, only: set[str] | None = None, now: datetime | None = None) -> list[tuple[str, bool]]:
    from ..toys import load_rules
    from ..toys.store import load_state
    from . import banner, beat, buttons, cards, iso, readme, toybox

    now = now or utcnow()
    want = set(ALL) if not only else set(only)
    unknown = want - set(ALL)
    if unknown:
        raise ValueError(f"unknown render target(s): {', '.join(sorted(unknown))}")
    site = load_site_config(paths)
    snap = read_json(paths.github_data)
    cal = Calendar.from_json(snap["calendar"])
    refreshed = human_utc(parse_ts(snap["calendar"]["asOf"]))
    rules = load_rules(paths.toy_rules)
    state = load_state(paths.toy_state, rules)
    out: list[tuple[str, bool]] = []

    def put(name: str, svg: str) -> None:
        out.append((f"assets/generated/{name}", write_text(paths.generated / name, svg)))

    if "banner" in want:
        put("banner.svg", banner.render(paths, site))
    if "stats" in want:
        put("stats.svg", cards.stats_card(paths, snap, refreshed))
    if "iso" in want:
        put("iso.svg", iso.readme_svg(paths, cal, refreshed=refreshed, profile_url=snap["profile"]["url"]))
    if "beat" in want:
        put("beat.svg", beat.render(paths, cal, site))
    if "languages" in want:
        put("languages.svg", cards.languages_card(paths, snap))
    if "rhythm" in want:
        put("rhythm.svg", cards.rhythm_card(paths, snap))
    if "toybox" in want:
        put("toybox.svg", toybox.render(paths, site, rules, state, now))
    if "buttons" in want:
        for name, svg in buttons.render_all(paths, site, rules).items():
            put(name, svg)
    if "site" in want:
        label = f"{cal.total:,} GitHub contributions in the last year, one isometric block per day."
        put("iso-site.svg", iso.site_svg(cal, label=label))
        put("iso-site-compact.svg", iso.site_svg(cal.last_weeks(26), label=label))
    if "readme" in want:
        out.append(("README.md", readme.update(paths, site, rules, snap, state, now)))
    return out


__all__ = ["ALL", "render_all"]
