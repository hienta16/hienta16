"""Top languages, measured two honest ways.

* by_bytes: GitHub's own measure, all code pooled. One large codebase can dominate.
* by_repos: every repository counts once, split by its own language mix, so a small project still shows up.

Only language names and shares leave this module: repository names are never stored or published.
"""

from __future__ import annotations

from typing import Iterable, Mapping


def language_shares(repos: Iterable[Mapping[str, int]], mode: str, limit: int = 5) -> list[dict]:
    if mode not in ("bytes", "repos"):
        raise ValueError("mode is 'bytes' or 'repos'")
    totals: dict[str, float] = {}
    for repo in repos:
        size = sum(v for v in repo.values() if v > 0)
        if not size:
            continue
        for lang, n in repo.items():
            if n > 0:
                totals[lang] = totals.get(lang, 0.0) + (n if mode == "bytes" else n / size)
    grand = sum(totals.values())
    if not grand:
        return []
    ranked = sorted(totals.items(), key=lambda kv: (-kv[1], kv[0]))
    head = [{"name": name, "share": round(v / grand, 4)} for name, v in ranked[:limit]]
    rest = sum(v for _, v in ranked[limit:])
    if rest:
        head.append({"name": "Other", "share": round(rest / grand, 4)})
    return head
