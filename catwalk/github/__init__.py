"""Talking to GitHub: an API client (REST + GraphQL) and a reader for the public contribution calendar."""

from .client import GitHubClient, GitHubError, RateLimited, discover_token
from .public_calendar import parse_public_calendar

__all__ = ["GitHubClient", "GitHubError", "RateLimited", "discover_token", "parse_public_calendar"]
