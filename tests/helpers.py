"""Shared test helpers: a fake GitHub (canned responses, no network) and a temporary repository root."""

from __future__ import annotations

import json
import shutil
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from catwalk.config import Paths
from catwalk.github.client import GitHubClient, Response

ROOT = Path(__file__).resolve().parent.parent
UTC = timezone.utc


def at(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def temp_root() -> Paths:
    """A throwaway copy of config/ and assets/fonts (enough to run any command) in a temp folder."""
    tmp = Path(tempfile.mkdtemp(prefix="catwalk-test-"))
    shutil.copytree(ROOT / "config", tmp / "config")
    shutil.copytree(ROOT / "assets" / "fonts", tmp / "assets" / "fonts")
    shutil.copy(ROOT / "README.md", tmp / "README.md")
    return Paths(tmp)


def calendar_days(start: date, counts: list[int]) -> list[dict]:
    """Days as the GraphQL API returns them, grouped in weeks of 7."""
    days = [{"date": (start + timedelta(days=i)).isoformat(), "contributionCount": c} for i, c in enumerate(counts)]
    return [{"contributionDays": days[i : i + 7]} for i in range(0, len(days), 7)]


def public_page(start: date, counts: list[int]) -> str:
    """A minimal copy of github.com/users/<login>/contributions markup."""
    cells, tips = [], []
    for i, c in enumerate(counts):
        d = (start + timedelta(days=i)).isoformat()
        cid = f"contribution-day-component-{i % 7}-{i // 7}"
        cells.append(f'<td tabindex="0" data-ix="{i // 7}" aria-selected="false" data-date="{d}" id="{cid}" class="day"></td>')
        label = "No contributions" if c == 0 else f"{c:,} contribution{'s' if c != 1 else ''}"
        tips.append(f'<tool-tip id="tt-{i}" for="{cid}" popover="manual">{label} on {d}.</tool-tip>')
    return "<table>" + "".join(cells) + "</table>" + "".join(tips)


class FakeGitHub:
    """Routes requests to canned answers. `fail` maps a substring of the URL or GraphQL query to an HTTP status."""

    def __init__(self, *, login="hienta16", start=date(2026, 1, 1), counts=None, public=None, viewer="hienta16", fail=None):
        self.login = login
        self.start = start
        self.counts = counts if counts is not None else [0, 2, 0, 5, 7, 0, 1] * 2
        self.public = public if public is not None else self.counts
        self.viewer = viewer
        self.fail = fail or {}
        self.calls: list[str] = []

    def client(self) -> GitHubClient:
        return GitHubClient("test-token", transport=self.transport, sleep=lambda _s: None)

    def transport(self, method, url, headers, body, timeout) -> Response:
        query = json.loads(body)["query"] if body and url.endswith("/graphql") else ""
        key = url + query
        self.calls.append(key)
        for needle, status in self.fail.items():
            if needle in key:
                return Response(status, {}, b'{"message":"nope"}')
        if url.startswith("https://github.com/users/"):
            return Response(200, {}, public_page(self.start, self.public).encode())
        if url.endswith("/graphql"):
            return Response(200, {}, json.dumps({"data": self._graphql(query)}).encode())
        if "/search/commits" in url:
            return Response(200, {}, b'{"total_count": 42}')
        if "/search/issues" in url:
            return Response(200, {}, json.dumps({"total_count": 7 if "type%3Apr" in url else 3}).encode())
        return Response(404, {}, b"{}")

    def _graphql(self, query: str) -> dict:
        if "viewer" in query:
            return {"viewer": {"login": self.viewer}}
        if "contributionCalendar" in query:
            return {
                "user": {
                    "login": self.login,
                    "name": "Test Person",
                    "url": f"https://github.com/{self.login}",
                    "avatarUrl": "https://avatars.example/x.png",
                    "createdAt": "2025-05-09T00:00:00Z",
                    "followers": {"totalCount": 3},
                    "contributionsCollection": {
                        "restrictedContributionsCount": 10,
                        "contributionCalendar": {
                            "totalContributions": sum(self.counts),
                            "weeks": calendar_days(self.start, self.counts),
                        },
                    },
                }
            }
        if "repositoriesContributedTo" in query:
            return {"user": {"repositoriesContributedTo": {"totalCount": 2}}}
        if "repositories(" in query:
            nodes = [
                {"isPrivate": True, "stargazerCount": 1, "languages": {"edges": [{"size": 900, "node": {"name": "Python"}}, {"size": 100, "node": {"name": "CSS"}}]}},
                {"isPrivate": False, "stargazerCount": 4, "languages": {"edges": [{"size": 50, "node": {"name": "TypeScript"}}]}},
            ]
            return {"user": {"repositories": {"pageInfo": {"hasNextPage": False, "endCursor": None}, "nodes": nodes}}}
        return {}
