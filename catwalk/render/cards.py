"""The stats cards: the headline numbers, top languages and the weekday rhythm.

Every number comes from data/github.json. A missing number is drawn as "—" with "not available", never guessed.
Contributions and commits are labelled separately: they are different measures.
"""

from __future__ import annotations

from ..config import Paths
from ..timeutil import parse_date
from .svg import document, f, measure, text
from .theme import BLUE, CREAM, INK, INK_2, NIGHT_2, ORANGE, PALE, PINK, WHITE


def _n(value: object) -> str:
    return f"{value:,}" if isinstance(value, int) else "—"


def _icon(kind: str, cx: float, cy: float, color: str) -> str:
    """Small flat glyphs in a coloured disc."""
    r = 17
    disc = f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{r}" fill="{color}"/>'
    s = f'stroke="{INK}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" fill="none"'
    x, y = cx, cy
    glyphs = {
        "commit": f'<path d="M{f(x - 10)} {f(y)}h5M{f(x + 5)} {f(y)}h5" {s}/><circle cx="{f(x)}" cy="{f(y)}" r="5" {s}/>',
        "pr": f'<circle cx="{f(x - 6)}" cy="{f(y - 7)}" r="2.6" {s}/><circle cx="{f(x - 6)}" cy="{f(y + 7)}" r="2.6" {s}/>'
        f'<circle cx="{f(x + 6)}" cy="{f(y + 7)}" r="2.6" {s}/><path d="M{f(x - 6)} {f(y - 4)}v8M{f(x + 6)} {f(y + 4)}v-6a3 3 0 0 0-3-3h-4m2-2-2 2 2 2" {s}/>',
        "issue": f'<circle cx="{f(x)}" cy="{f(y)}" r="8" {s}/><circle cx="{f(x)}" cy="{f(y)}" r="1.8" fill="{INK}"/>',
        "streak": f'<path d="M{f(x + 2)} {f(y - 10)}l-8 11h7l-3 9 9-12h-7z" fill="{INK}"/>',
        "repos": f'<path d="M{f(x - 8)} {f(y - 8)}h11v14h-11zM{f(x - 3)} {f(y - 3)}h11v14h-11z" {s}/>',
        "star": f'<path d="M{f(x)} {f(y - 9)}l2.7 5.6 6.1.8-4.5 4.2 1.1 6-5.4-2.9-5.4 2.9 1.1-6-4.5-4.2 6.1-.8z" {s}/>',
    }
    return disc + glyphs[kind]


def stats_card(paths: Paths, snap: dict, refreshed: str) -> str:
    W, H = 1200, 340
    cal, m = snap["calendar"], snap["metrics"]
    counts = snap.get("counts") or {}
    repos = snap.get("repositories") or {}
    longest = (m.get("longestStreak") or {}).get("length")
    first = m.get("firstContribution")
    since = parse_date(first) if first else None

    total = f"{cal['total']:,}"
    tag_w = measure(paths, "contributions", "bold", 26) + 28
    left = [
        text(48, 66, "Last 12 months", "label", 14, INK_2),
        text(42, 158, total, "black", 98, INK),
        f'<rect x="48" y="178" width="{f(tag_w)}" height="42" rx="10" fill="{ORANGE}"/>',
        text(62, 207, "contributions", "bold", 26, INK),
    ]
    if since:
        share = m.get("activeShareSinceFirst")
        left.append(text(48, 258, f"{m['activeDays']} active days since {since.day} {since:%b %Y}", "bold", 19, INK))
        if isinstance(share, float):
            left.append(text(48, 282, f"{round(share * 100)}% of the days since my first contribution", "text", 15, INK_2))

    tiles = [
        ("commit", ORANGE, _n(counts.get("commitsLastYear")), "Commits I authored"),
        ("pr", PINK, _n(counts.get("pullRequestsLastYear")), "Pull requests"),
        ("issue", BLUE, _n(counts.get("issuesLastYear")), "Issues opened"),
        ("streak", ORANGE, f"{longest} days" if isinstance(longest, int) else "—", "Longest streak"),
        ("repos", PINK, _n(counts.get("contributedToLastYear")), "Repos contributed to"),
        ("star", BLUE, _n(repos.get("stars")), "Stars earned"),
    ]
    grid = []
    x0, y0, tw, th, gap = 560, 34, 186, 112, 14
    for i, (icon, color, value, label) in enumerate(tiles):
        col, row = i % 3, i // 3
        x, y = x0 + col * (tw + gap), y0 + row * (th + gap)
        missing = value == "—"
        grid.append(f'<rect x="{x}" y="{y}" width="{tw}" height="{th}" rx="18" fill="{PALE}"/>')
        grid.append(_icon(icon, x + 32, y + 32, color))
        grid.append(text(x + 18, y + 84, value, "bold", 34 if len(value) < 8 else 28, INK))
        grid.append(text(x + 18, y + 102, label + (" · n/a" if missing else ""), "label", 11.5, INK_2))

    scope = counts.get("scope")
    footer_note = "private repositories counted as numbers only" if scope == "public-and-private" else "public repositories only"
    footer = (
        f'<path d="M0 {H - 44}H{W}V{H - 28}a28 28 0 0 1-28 28H28a28 28 0 0 1-28-28z" fill="{INK}"/>'
        + text(48, H - 16, f"Updated {refreshed} · {footer_note} · commits made by bots are not mine and are not counted", "text", 14, CREAM)
    )
    body = f'<rect width="{W}" height="{H}" rx="28" fill="{CREAM}"/>' + "".join(left) + "".join(grid) + footer
    return document(
        paths,
        W,
        H,
        body,
        title=f"{total} contributions in the last year",
        desc=(
            f"{total} contributions in the last 12 months; {_n(counts.get('commitsLastYear'))} commits I authored, "
            f"{_n(counts.get('pullRequestsLastYear'))} pull requests, {_n(counts.get('issuesLastYear'))} issues; "
            f"longest streak {longest} days."
        ),
    )


def languages_card(paths: Paths, snap: dict) -> str:
    W, H = 588, 330
    repos = snap.get("repositories") or {}
    langs = ((repos.get("languages") or {}).get("byBytes")) or []
    rows = []
    if not langs:
        rows.append(text(40, 170, "Language data is not available right now.", "text", 16, NIGHT_2))
    else:
        top = max(l["share"] for l in langs)
        bar_x, bar_w = 196, 300
        for i, lang in enumerate(langs[:6]):
            y = 118 + i * 34
            other = lang["name"] == "Other"
            w = max(4.0, bar_w * lang["share"] / top)
            rows.append(text(40, y + 6, lang["name"], "bold", 18, NIGHT_2 if other else CREAM))
            rows.append(f'<rect x="{bar_x}" y="{y - 9}" width="{f(w)}" height="18" rx="5" fill="{NIGHT_2 if other else ORANGE}" opacity="{0.45 if other else 1}"/>')
            rows.append(text(W - 40, y + 6, f"{round(lang['share'] * 100)}%", "bold", 17, CREAM, "end"))
    body = (
        f'<rect width="{W}" height="{H}" rx="28" fill="{INK}"/>'
        + text(40, 58, "Top languages", "black", 28, CREAM)
        + text(40, 84, f"Share of code across my {repos.get('withLanguages', 0)} repositories", "text", 14, NIGHT_2)
        + "".join(rows)
    )
    names = ", ".join(f"{l['name']} {round(l['share'] * 100)}%" for l in langs)
    return document(paths, W, H, body, title="Top languages", desc=f"Top languages by code size: {names or 'not available'}.")


def rhythm_card(paths: Paths, snap: dict) -> str:
    W, H = 588, 330
    week = snap["metrics"]["weekdays"]
    top = max((d["total"] for d in week), default=0) or 1
    base, tall, bw = 268, 132, 46
    step = (W - 80) / 7
    bars = []
    for i, d in enumerate(week):
        cx = 40 + step * i + step / 2
        h = max(3.0, tall * d["total"] / top) if d["total"] else 3.0
        bars.append(f'<rect x="{f(cx - bw / 2)}" y="{f(base - h)}" width="{bw}" height="{f(h)}" rx="6" fill="{BLUE}"/>')
        bars.append(text(cx, base - h - 10, f"{d['total']:,}", "bold", 16, INK, "middle"))
        bars.append(text(cx, base + 26, d["day"], "label", 12.5, INK_2, "middle"))
    body = (
        f'<rect width="{W}" height="{H}" rx="28" fill="{PALE}"/>'
        + text(40, 58, "Weekly rhythm", "black", 28, INK)
        + text(40, 84, "Contributions by day of the week, last 12 months", "text", 14, INK_2)
        + f'<path d="M40 {base}H{W - 40}" stroke="{INK}" stroke-opacity=".25" stroke-width="1.5"/>'
        + "".join(bars)
    )
    desc = ", ".join(f"{d['day']} {d['total']}" for d in week)
    return document(paths, W, H, body, title="Weekly rhythm", desc=f"Contributions by weekday over the last year: {desc}.")


__all__ = ["stats_card", "languages_card", "rhythm_card", "WHITE"]
