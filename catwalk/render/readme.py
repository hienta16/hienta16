"""Keep the generated parts of README.md up to date. Everything outside the markers is hand-written and untouched:

    <!-- catwalk:toys:start --> … <!-- catwalk:toys:end -->        the Give buttons (or "opens soon"), and the rules
    <!-- catwalk:updated:start --> … <!-- catwalk:updated:end -->  when the numbers were last refreshed

GitHub's README is Markdown, not a web page: no JavaScript runs there. So the toy box uses plain links that open
a pre-filled issue, and the moving, reacting cat lives on the website.
"""

from __future__ import annotations

import re
from datetime import datetime
from urllib.parse import quote, urlencode

from ..config import Paths, SiteConfig
from ..jsonio import write_text
from ..timeutil import duration_words, human_utc, parse_ts
from ..toys.models import ToyState
from ..toys.rules import ToyRules

ISSUE_BODY = (
    "Just press Create, there is nothing to write. A GitHub Action checks the gift "
    "(one per GitHub account every {cooldown}) and the toy appears in the toy box within a few minutes."
)


def issue_link(site: SiteConfig, rules: ToyRules, key: str) -> str:
    query = urlencode(
        {"title": f"{rules.title_prefix} {key}", "body": ISSUE_BODY.format(cooldown=duration_words(rules.cooldown))},
        quote_via=quote,
    )
    return f"https://github.com/{site.hub_repo}/issues/new?{query}"


def toys_section(site: SiteConfig, rules: ToyRules) -> str:
    stays = ", ".join(f"{k.label.lower()} {duration_words(k.lifetime)}" for k in rules.kinds.values())
    how = [
        "<details>",
        "<summary>How the toy box works</summary>",
        "",
        f"- Each button opens a GitHub issue with the title filled in, like `{rules.title_prefix} yarn`. Press **Create**.",
        "- A GitHub Action runs Python that reads three things GitHub vouches for: who opened the issue, when, and the toy named in the title. The issue text is never read or run.",
        f"- One gift per GitHub account every {duration_words(rules.cooldown)}. Toys stay a while: {stays}.",
        f"- Up to {rules.max_visible} toys at once; when the box is full, the oldest goes back on the shelf. Every gift still counts in the total.",
        "- The Action replies on your issue, closes it, and redraws the picture above. The code is in [`catwalk/toys/`](catwalk/toys).",
        "",
        "</details>",
    ]
    if site.toys_live:
        buttons = "\n".join(
            f'  <a href="{issue_link(site, rules, key).replace("&", "&amp;")}"><img src="assets/generated/btn-{key}.svg" height="44" alt="{kind.action}"></a>'
            for key, kind in rules.kinds.items()
        )
        lead = [
            '<p align="center">',
            buttons,
            "</p>",
            '<p align="center"><sub>Each button opens a pre-filled issue. Press <b>Create</b> and the toy appears within a few minutes.</sub></p>',
        ]
    else:
        lead = [
            '<p align="center"><sub>The toy box opens when this profile goes public. Until then, the cat is practising alone.</sub></p>',
        ]
    return "\n".join(lead + ["", *how])


def updated_line(site: SiteConfig, snap: dict) -> str:
    when = human_utc(parse_ts(snap["calendar"]["asOf"]))
    cadence = (
        "redrawn by GitHub Actions every 6 hours"
        if site.hub_public
        else "a snapshot; the automatic refresh switches on when this profile goes public"
    )
    return (
        f"<sub>Numbers from the GitHub API, drawn by Python in [`catwalk/`](catwalk) · last refresh {when}, {cadence}. "
        "Private repositories are counted as numbers only; commits by bots are not counted.</sub>"
    )


def replace_block(readme: str, name: str, content: str) -> str:
    pattern = re.compile(rf"(<!-- catwalk:{name}:start -->).*?(<!-- catwalk:{name}:end -->)", re.DOTALL)
    if not pattern.search(readme):
        raise ValueError(f"README.md has no catwalk:{name} markers")
    return pattern.sub(lambda m: f"{m.group(1)}\n{content}\n{m.group(2)}", readme, count=1)


def update(paths: Paths, site: SiteConfig, rules: ToyRules, snap: dict, state: ToyState, now: datetime) -> bool:
    text = paths.readme.read_text(encoding="utf-8")
    text = replace_block(text, "toys", toys_section(site, rules))
    text = replace_block(text, "updated", updated_line(site, snap))
    return write_text(paths.readme, text)
