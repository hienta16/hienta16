"""Time helpers. Everything is stored and compared in UTC; local time zones never enter the data."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

UTC = timezone.utc


def utcnow() -> datetime:
    """The current time in UTC, to the second (stored timestamps never carry microseconds)."""
    return datetime.now(UTC).replace(microsecond=0)


def parse_ts(value: object) -> datetime:
    """Parse an ISO-8601 timestamp such as GitHub's '2026-11-23T06:00:00Z' into an aware UTC datetime.

    Naive timestamps (no zone) are refused: guessing a zone is how off-by-hours bugs start.
    """
    if not isinstance(value, str) or not value.strip():
        raise ValueError("a timestamp must be a non-empty string")
    text = value.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    moment = datetime.fromisoformat(text)
    if moment.tzinfo is None:
        raise ValueError(f"timestamp has no time zone: {value!r}")
    return moment.astimezone(UTC)


def iso(moment: datetime) -> str:
    """Format a datetime as '2026-11-23T06:00:00Z'."""
    if moment.tzinfo is None:
        raise ValueError("refusing to format a naive datetime")
    return moment.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_date(value: object) -> date:
    if not isinstance(value, str):
        raise ValueError("a date must be a string like 2026-11-23")
    return date.fromisoformat(value)


def ceil_minute(moment: datetime) -> datetime:
    """Round up to the next whole minute, so a time shown to the minute is never earlier than the real one."""
    floor = moment.replace(second=0, microsecond=0)
    return floor if floor == moment else floor + timedelta(minutes=1)


def human_utc(moment: datetime) -> str:
    """'Sat 30 Nov 2026, 14:05 UTC': for replies and image captions."""
    m = moment.astimezone(UTC)
    return f"{m:%a} {m.day} {m:%b %Y}, {m:%H:%M} UTC"


def human_date(moment: datetime | date) -> str:
    """'30 Nov 2026'."""
    return f"{moment.day} {moment:%b %Y}"


def duration_words(span: timedelta) -> str:
    """'7 days', '48 hours', '14 days': how long a toy stays, in the words people use."""
    hours = round(span.total_seconds() / 3600)
    if hours % 24 == 0 and hours >= 72:
        days = hours // 24
        return f"{days} days"
    return f"{hours} hour{'s' if hours != 1 else ''}"
