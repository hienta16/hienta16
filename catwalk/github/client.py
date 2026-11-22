"""A small GitHub API client on the standard library (urllib), so the Actions need no pip install.

What it handles for you:
* Retries with backoff on network errors and 5xx answers (GitHub has bad minutes too).
* Rate limits: a 403/429 that says "rate limit" raises RateLimited at once instead of hammering the API.
* Tokens: sent only to api.github.com, never logged, never written to a file.

For tests, pass `transport=` a function that returns canned Responses; nothing then touches the network.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Any, Callable, Mapping

API = "https://api.github.com"
USER_AGENT = "catwalk-profile-automation (+https://github.com/hienta16)"


class GitHubError(RuntimeError):
    """GitHub could not give us what we asked for. The message is safe to print (no token, no payload)."""


class RateLimited(GitHubError):
    def __init__(self, message: str, reset_at: float | None = None):
        super().__init__(message)
        self.reset_at = reset_at


@dataclass
class Response:
    status: int
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""

    def json(self) -> Any:
        return json.loads(self.body.decode("utf-8")) if self.body else None

    def text(self) -> str:
        return self.body.decode("utf-8", errors="replace")


Transport = Callable[[str, str, Mapping[str, str], "bytes | None", float], Response]


def urllib_transport(method: str, url: str, headers: Mapping[str, str], body: bytes | None, timeout: float) -> Response:
    request = urllib.request.Request(url, data=body, method=method, headers=dict(headers))
    try:
        with urllib.request.urlopen(request, timeout=timeout) as reply:  # noqa: S310 (fixed https hosts only)
            return Response(reply.status, {k.lower(): v for k, v in reply.headers.items()}, reply.read())
    except urllib.error.HTTPError as error:
        payload = error.read() if error.fp is not None else b""
        return Response(error.code, {k.lower(): v for k, v in (error.headers or {}).items()}, payload)


class GitHubClient:
    def __init__(
        self,
        token: str | None = None,
        *,
        transport: Transport = urllib_transport,
        timeout: float = 25.0,
        retries: int = 3,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.token = (token or "").strip() or None
        self.transport = transport
        self.timeout = timeout
        self.retries = retries
        self.sleep = sleep

    def __repr__(self) -> str:  # never show the token, even in a traceback
        return f"GitHubClient(token={'set' if self.token else 'none'})"

    # ---- low level -------------------------------------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        auth: bool = True,
        body: bytes | None = None,
        accept: str = "application/vnd.github+json",
        retry: bool = True,
    ) -> Response:
        headers = {"User-Agent": USER_AGENT, "Accept": accept}
        if auth and self.token and url.startswith(API + "/"):
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-GitHub-Api-Version"] = "2022-11-28"
        if body is not None:
            headers["Content-Type"] = "application/json"
        last: GitHubError = GitHubError("no attempt was made")
        for attempt in range(self.retries + 1):
            try:
                reply = self.transport(method, url, headers, body, self.timeout)
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                last = GitHubError(f"network error talking to GitHub ({exc.__class__.__name__})")
            else:
                if reply.status in (403, 429) and _is_rate_limit(reply):
                    reset = reply.headers.get("x-ratelimit-reset")
                    raise RateLimited(f"GitHub rate limit reached ({_where(url)})", float(reset) if reset and reset.isdigit() else None)
                if reply.status >= 500 or reply.status == 408:
                    last = GitHubError(f"GitHub answered {reply.status} for {_where(url)}")
                else:
                    return reply
            if attempt < self.retries and retry:
                self.sleep(min(2**attempt, 8))
            elif not retry:
                break
        raise last

    # ---- helpers -----------------------------------------------------------------------------------------------

    def graphql(self, query: str, variables: dict | None = None) -> dict:
        if not self.token:
            raise GitHubError("the GraphQL API needs a token")
        body = json.dumps({"query": query, "variables": variables or {}}).encode("utf-8")
        reply = self.request("POST", f"{API}/graphql", body=body)
        if reply.status != 200:
            raise GitHubError(f"GraphQL answered {reply.status}")
        payload = reply.json() or {}
        errors = payload.get("errors")
        if errors:
            messages = "; ".join(str(e.get("message", "unknown error")) for e in errors if isinstance(e, dict))
            raise GitHubError(f"GraphQL: {messages[:300]}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise GitHubError("GraphQL answered without data")
        return data

    def rest(self, path: str, params: Mapping[str, Any] | None = None, *, method: str = "GET", payload: Any = None, auth: bool = True) -> Any:
        url = f"{API}/{path.lstrip('/')}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        # Reads are retried; writes (a comment, closing an issue) are not, so nothing is ever posted twice.
        reply = self.request(method, url, auth=auth, body=body, retry=method == "GET")
        if reply.status >= 400:
            raise GitHubError(f"REST {method} /{path.split('?')[0].lstrip('/')} answered {reply.status}")
        return reply.json()

    def search_count(self, kind: str, query: str) -> int:
        """How many results a search has (commits or issues), without downloading them."""
        result = self.rest(f"search/{kind}", {"q": query, "per_page": 1})
        total = result.get("total_count") if isinstance(result, dict) else None
        if not isinstance(total, int) or total < 0:
            raise GitHubError(f"search/{kind} returned no count")
        return total

    def fetch_page(self, url: str) -> str:
        """An anonymous GET of a public github.com page (no token is ever sent off api.github.com)."""
        if not url.startswith("https://github.com/"):
            raise GitHubError("only github.com pages are fetched")
        reply = self.request("GET", url, auth=False, accept="text/html")
        if reply.status != 200:
            raise GitHubError(f"{_where(url)} answered {reply.status}")
        return reply.text()


def _is_rate_limit(reply: Response) -> bool:
    if reply.headers.get("x-ratelimit-remaining") == "0" or "retry-after" in reply.headers:
        return True
    return b"rate limit" in reply.body[:2000].lower()


def _where(url: str) -> str:
    parts = urllib.parse.urlsplit(url)
    return parts.netloc + parts.path


def discover_token(names: tuple[str, ...] = ("CATWALK_STATS_TOKEN", "GITHUB_TOKEN", "GH_TOKEN"), *, env: Mapping[str, str] | None = None, use_gh_cli: bool = True) -> str | None:
    """Find a token: the first non-empty environment variable in `names`, else `gh auth token` (local runs).

    In GitHub Actions, CATWALK_STATS_TOKEN is an optional personal token that lets the counts include private
    repositories; GITHUB_TOKEN is the workflow's own token, which only sees public data and this repository.
    """
    env = os.environ if env is None else env
    for name in names:
        value = (env.get(name) or "").strip()
        if value:
            return value
    if use_gh_cli and not env.get("GITHUB_ACTIONS") and shutil.which("gh"):
        try:
            done = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=15, check=False)
        except (OSError, subprocess.SubprocessError):
            return None
        token = done.stdout.strip()
        return token or None
    return None
