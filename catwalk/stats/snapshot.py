"""Build data/github.json: the one file both the README and the website read their GitHub numbers from.

The snapshot has independent sections, each with its own `asOf` time:

    profile + calendar  GraphQL contribution calendar, verified day by day against the public page
    counts              commits, pull requests and issues I authored (search API), repositories contributed to
    repositories        repository count, stars, language shares (no repository names are kept)

If one section fails (network, rate limit, missing field, a calendar that does not match the public page), that
section keeps its last good value and the problem is written to `refresh.problems`. Nothing is ever estimated.

Scope: with a personal token (CATWALK_STATS_TOKEN locally or in Actions) the counts include private repositories,
as numbers only. With only the workflow's GITHUB_TOKEN they would be public-only, so a public-only run never
overwrites complete counts; it keeps them and says how old they are.

Commits are not contributions. `commitsLastYear` counts commits whose author is me. Commits made by automation
(github-actions[bot], including this repository's own refresh commits) have a different author, so they are in
neither the commit count nor the contribution calendar.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Callable

from ..github import GitHubClient, GitHubError, parse_public_calendar
from ..timeutil import iso
from .calendar import Calendar, CalendarError, metrics
from .languages import language_shares

SCHEMA = 2
PUBLIC_CALENDAR_URL = "https://github.com/users/{login}/contributions"

PROFILE_QUERY = """
query($login: String!) {
  user(login: $login) {
    login name url avatarUrl createdAt
    followers { totalCount }
    contributionsCollection {
      restrictedContributionsCount
      contributionCalendar { totalContributions weeks { contributionDays { date contributionCount } } }
    }
  }
}
"""

CONTRIBUTED_QUERY = """
query($login: String!) {
  user(login: $login) {
    repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, ISSUE, PULL_REQUEST, REPOSITORY]) { totalCount }
  }
}
"""

REPOSITORIES_QUERY = """
query($login: String!, $cursor: String) {
  user(login: $login) {
    repositories(first: 100, after: $cursor, ownerAffiliations: OWNER, isFork: false) {
      pageInfo { hasNextPage endCursor }
      nodes {
        isPrivate stargazerCount
        languages(first: 20, orderBy: { field: SIZE, direction: DESC }) { edges { size node { name } } }
      }
    }
  }
}
"""

VIEWER_QUERY = "query { viewer { login } }"

PUBLIC = "public"
COMPLETE = "public-and-private"

_SECTION_ERRORS = (GitHubError, CalendarError, KeyError, TypeError, ValueError, AttributeError)


class SnapshotError(RuntimeError):
    """Nothing usable could be built (not even a previous calendar to fall back on)."""


def detect_scope(client: GitHubClient, login: str, public_only: bool) -> str:
    """COMPLETE when the token belongs to `login` itself (so it can see private repositories), else PUBLIC."""
    if public_only or not client.token:
        return PUBLIC
    try:
        viewer = client.graphql(VIEWER_QUERY).get("viewer") or {}
    except GitHubError:
        return PUBLIC
    return COMPLETE if str(viewer.get("login", "")).lower() == login.lower() else PUBLIC


def verify_against_public(cal: Calendar, public: dict[str, int | None]) -> tuple[Calendar, list[str]]:
    """Return the calendar a stranger would see, or raise if the API shows anything the public page does not.

    Today is the one exception: the public page is cached and can lag a few minutes behind, so for the last day the
    smaller of the two numbers wins (never show more than a stranger sees).
    """
    days = cal.days()
    if sum(1 for d in days if d.date.isoformat() in public) < len(days) - 7:
        raise CalendarError("could not read the public calendar (did GitHub change the page?)")
    *earlier, last = days
    differs = [d for d in earlier if public.get(d.date.isoformat(), 0) != d.count]
    if differs:
        raise CalendarError(
            f"the public calendar differs on {len(differs)} day(s), first {differs[0].date.isoformat()}; "
            "the profile may hide private contributions, so nothing from the API is published"
        )
    notes: list[str] = []
    counts = list(cal.counts)
    shown = public.get(last.date.isoformat())
    if isinstance(shown, int) and shown != last.count:
        counts[-1] = min(shown, last.count)
        notes.append(f"today is still settling (API {last.count}, public page {shown}); using {counts[-1]}")
    return Calendar(cal.start, tuple(counts)), notes


def fetch_profile_and_calendar(client: GitHubClient, login: str) -> tuple[dict, dict, list[str]]:
    user = client.graphql(PROFILE_QUERY, {"login": login}).get("user")
    if not user:
        raise GitHubError(f"no GitHub user {login!r}")
    collection = user["contributionsCollection"]
    raw = collection["contributionCalendar"]
    cal = Calendar.from_pairs(
        (d["date"], int(d["contributionCount"])) for week in raw["weeks"] for d in week["contributionDays"]
    )
    if cal.total != raw["totalContributions"]:
        raise CalendarError("calendar days do not add up to GitHub's total")
    public = parse_public_calendar(client.fetch_page(PUBLIC_CALENDAR_URL.format(login=login)))
    cal, notes = verify_against_public(cal, public)
    profile = {
        "name": user.get("name") or user["login"],
        "url": user["url"],
        "avatarUrl": user["avatarUrl"],
        "joined": str(user["createdAt"])[:10],
        "followers": int(user["followers"]["totalCount"]),
    }
    calendar = {
        **cal.to_json(),
        "privateContributions": int(collection["restrictedContributionsCount"]),
        "verifiedAgainstPublicProfile": True,
    }
    return profile, calendar, notes


def fetch_counts(client: GitHubClient, login: str, since: str, scope: str) -> dict:
    visibility = " is:public" if scope == PUBLIC else ""

    def count(kind: str, query: str) -> int:
        return client.search_count(kind, query + visibility)

    contributed = client.graphql(CONTRIBUTED_QUERY, {"login": login})["user"]["repositoriesContributedTo"]["totalCount"]
    return {
        "commitsLastYear": count("commits", f"author:{login} author-date:>={since}"),
        "pullRequestsLastYear": count("issues", f"author:{login} type:pr created:>={since}"),
        "issuesLastYear": count("issues", f"author:{login} type:issue created:>={since}"),
        "pullRequestsAllTime": count("issues", f"author:{login} type:pr"),
        "issuesAllTime": count("issues", f"author:{login} type:issue"),
        "contributedToLastYear": int(contributed),
    }


def fetch_repositories(client: GitHubClient, login: str, scope: str) -> dict:
    nodes: list[dict] = []
    cursor = None
    for _ in range(10):  # at most 1,000 repositories
        page = client.graphql(REPOSITORIES_QUERY, {"login": login, "cursor": cursor})["user"]["repositories"]
        nodes.extend(page["nodes"])
        if not page["pageInfo"]["hasNextPage"]:
            break
        cursor = page["pageInfo"]["endCursor"]
    if scope == PUBLIC:
        nodes = [n for n in nodes if not n["isPrivate"]]
    languages = [
        {e["node"]["name"]: int(e["size"]) for e in n["languages"]["edges"] if int(e["size"]) > 0} for n in nodes
    ]
    languages = [m for m in languages if m]
    return {
        "total": len(nodes),
        "public": sum(1 for n in nodes if not n["isPrivate"]),
        "private": sum(1 for n in nodes if n["isPrivate"]),
        "stars": sum(int(n["stargazerCount"]) for n in nodes),
        "withLanguages": len(languages),
        "languages": {"byBytes": language_shares(languages, "bytes"), "byRepos": language_shares(languages, "repos")},
    }


def build_snapshot(
    client: GitHubClient,
    login: str,
    previous: dict | None,
    now: datetime,
    *,
    public_only: bool = False,
    log: Callable[[str], None] = lambda _msg: None,
) -> dict:
    prev = previous if isinstance(previous, dict) and previous.get("schema") == SCHEMA else {}
    problems: list[str] = []
    notes: list[str] = []
    stamp = iso(now)
    scope = detect_scope(client, login, public_only)
    log(f"scope: {scope}")

    # 1. Profile and calendar (one GraphQL call, then the public-page check)
    try:
        profile, calendar, calendar_notes = fetch_profile_and_calendar(client, login)
        profile["asOf"] = calendar["asOf"] = stamp
        notes += calendar_notes
    except _SECTION_ERRORS as exc:
        problems.append(f"calendar: {exc}")
        profile, calendar = prev.get("profile"), prev.get("calendar")
    if calendar is None:
        raise SnapshotError("no calendar: GitHub could not be read and there is no earlier snapshot to keep")
    since = calendar["from"]

    # 2. Counts, and 3. repositories: keep complete numbers rather than overwrite them with public-only ones
    def section(name: str, fetch: Callable[[], dict]) -> dict | None:
        old = prev.get(name)
        if scope == PUBLIC and isinstance(old, dict) and old.get("scope") == COMPLETE:
            problems.append(
                f"{name}: this run can only see public repositories (no CATWALK_STATS_TOKEN); "
                f"kept the complete numbers from {old.get('asOf')}"
            )
            return old
        try:
            return {"scope": scope, "asOf": stamp, **fetch()}
        except _SECTION_ERRORS as exc:
            problems.append(f"{name}: {exc}")
            return old if isinstance(old, dict) else None

    counts = section("counts", lambda: fetch_counts(client, login, since, scope))
    repositories = section("repositories", lambda: fetch_repositories(client, login, scope))

    complete = not problems
    return {
        "schema": SCHEMA,
        "login": login,
        "generatedAt": stamp,
        "profile": profile,
        "calendar": calendar,
        "metrics": metrics(Calendar.from_json(calendar)),
        "counts": counts,
        "repositories": repositories,
        "refresh": {
            "attemptedAt": stamp,
            "ok": complete,
            "lastCompleteAt": stamp if complete else (prev.get("refresh") or {}).get("lastCompleteAt"),
            "problems": problems,
            "notes": notes,
            "schedule": "every 6 hours by GitHub Actions, and on demand",
        },
    }


def age(snapshot: dict, now: datetime) -> timedelta | None:
    from ..timeutil import parse_ts

    try:
        return now - parse_ts(snapshot["calendar"]["asOf"])
    except (KeyError, TypeError, ValueError):
        return None
