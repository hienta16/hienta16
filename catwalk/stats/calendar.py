"""The contribution calendar and every number derived from it.

A *contribution* is what GitHub's calendar counts: commits to a default branch, pull requests, issues and reviews
(private ones too, as plain numbers, when the profile shows private contributions). It is not the same as a commit;
the commit count lives in snapshot.py and is labelled separately everywhere.

Dates are calendar dates in GitHub's profile calendar. Arithmetic uses `date` objects, so a machine's time zone
can never shift a day.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from statistics import median
from typing import Iterable, Sequence

WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")

# Fixed, labelled levels, shared by the 3D calendar, the legend and the website. Upper bound inclusive.
LEVELS: tuple[tuple[int, int | None], ...] = ((0, 0), (1, 5), (6, 15), (16, 40), (41, None))


class CalendarError(ValueError):
    """The calendar is not internally consistent (gaps, negative counts, totals that do not add up)."""


@dataclass(frozen=True)
class Day:
    index: int
    date: date
    count: int

    @property
    def weekday(self) -> int:
        """Monday = 0 … Sunday = 6."""
        return self.date.weekday()

    @property
    def row(self) -> int:
        """Row in GitHub's Sunday-first calendar: Sunday = 0 … Saturday = 6."""
        return (self.date.weekday() + 1) % 7


@dataclass(frozen=True)
class Calendar:
    start: date
    counts: tuple[int, ...]

    def __post_init__(self) -> None:
        if not self.counts:
            raise CalendarError("the calendar has no days")
        for value in self.counts:
            if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                raise CalendarError(f"day counts must be whole numbers >= 0, got {value!r}")

    @property
    def end(self) -> date:
        return self.start + timedelta(days=len(self.counts) - 1)

    @property
    def total(self) -> int:
        return sum(self.counts)

    def days(self) -> list[Day]:
        return [Day(i, self.start + timedelta(days=i), c) for i, c in enumerate(self.counts)]

    def week_of(self, day: Day) -> int:
        """Column in the Sunday-first grid; column 0 holds the first (possibly partial) week."""
        first_row = (self.start.weekday() + 1) % 7
        return (first_row + day.index) // 7

    @property
    def weeks(self) -> int:
        return self.week_of(self.days()[-1]) + 1

    def last_weeks(self, weeks: int) -> "Calendar":
        """The trailing `weeks` whole columns (the compact calendar on phones)."""
        days = self.days()
        keep = [d for d in days if self.week_of(d) >= self.weeks - weeks]
        return Calendar(keep[0].date, tuple(d.count for d in keep))

    # ---- (de)serialisation -------------------------------------------------------------------------------------

    @classmethod
    def from_pairs(cls, pairs: Iterable[tuple[str, int]]) -> "Calendar":
        """Build from (YYYY-MM-DD, count) pairs as the GraphQL API returns them; they must be consecutive days."""
        items = [(date.fromisoformat(d), int(c)) for d, c in pairs]
        if not items:
            raise CalendarError("the calendar has no days")
        for (prev, _), (cur, _) in zip(items, items[1:]):
            if cur - prev != timedelta(days=1):
                raise CalendarError(f"calendar gap after {prev.isoformat()}")
        return cls(items[0][0], tuple(c for _, c in items))

    @classmethod
    def from_json(cls, raw: dict) -> "Calendar":
        try:
            start, end = date.fromisoformat(raw["from"]), date.fromisoformat(raw["to"])
            counts = tuple(raw["days"])
            total = raw["total"]
        except (KeyError, TypeError, ValueError) as exc:
            raise CalendarError(f"calendar is missing a field ({exc})") from exc
        cal = cls(start, counts)
        if cal.end != end:
            raise CalendarError("calendar length does not match its dates")
        if cal.total != total:
            raise CalendarError("calendar days do not add up to its total")
        return cal

    def to_json(self) -> dict:
        return {"from": self.start.isoformat(), "to": self.end.isoformat(), "total": self.total, "days": list(self.counts)}


def level_of(count: int) -> int:
    for i, (lo, hi) in enumerate(LEVELS):
        if count >= lo and (hi is None or count <= hi):
            return i
    raise ValueError(f"no level for {count}")


@dataclass(frozen=True)
class Streak:
    length: int
    start: date | None = None
    end: date | None = None
    running: bool = False

    def to_json(self) -> dict:
        return {
            "length": self.length,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "running": self.running,
        }


def longest_streak(days: Sequence[Day]) -> Streak:
    """The longest run of consecutive active days. Ties go to the most recent run."""
    best = Streak(0)
    run_start: Day | None = None
    for i, d in enumerate(days):
        if d.count > 0:
            run_start = run_start or d
            length = d.index - run_start.index + 1
            if length >= best.length and length > 0:
                best = Streak(length, run_start.date, d.date, i == len(days) - 1)
        else:
            run_start = None
    return best


@dataclass(frozen=True)
class CurrentStreak:
    length: int
    start: date | None
    end: date | None
    today_pending: bool

    def to_json(self) -> dict:
        return {
            "length": self.length,
            "start": self.start.isoformat() if self.start else None,
            "end": self.end.isoformat() if self.end else None,
            "todayPending": self.today_pending,
        }


def current_streak(days: Sequence[Day]) -> CurrentStreak:
    """Consecutive active days up to today. Like GitHub, an empty *today* does not break it (the day isn't over)."""
    if not days:
        return CurrentStreak(0, None, None, False)
    i = len(days) - 1
    pending = days[i].count == 0
    if pending:
        i -= 1
    n = 0
    while i - n >= 0 and days[i - n].count > 0:
        n += 1
    if not n:
        return CurrentStreak(0, None, None, pending)
    return CurrentStreak(n, days[i - n + 1].date, days[i].date, pending)


def month_totals(days: Sequence[Day]) -> list[dict]:
    months: dict[str, dict] = {}
    for d in days:
        key = d.date.strftime("%Y-%m")
        m = months.setdefault(key, {"month": key, "total": 0, "activeDays": 0, "days": 0, "partial": False})
        m["total"] += d.count
        m["activeDays"] += 1 if d.count else 0
        m["days"] += 1
    for key, m in months.items():
        year, month = map(int, key.split("-"))
        nxt = date(year + (month == 12), month % 12 + 1, 1)
        m["partial"] = m["days"] < (nxt - date(year, month, 1)).days
    return list(months.values())


def weekday_totals(days: Sequence[Day]) -> list[int]:
    """Totals by weekday, Monday first."""
    out = [0] * 7
    for d in days:
        out[d.weekday] += d.count
    return out


def level_counts(days: Sequence[Day]) -> list[int]:
    out = [0] * len(LEVELS)
    for d in days:
        out[level_of(d.count)] += 1
    return out


def metrics(cal: Calendar) -> dict:
    """Everything the README and the website show about the calendar, computed once, here."""
    days = cal.days()
    active = [d for d in days if d.count > 0]
    first = active[0] if active else None
    since_first = days[first.index :] if first else []
    best = max(active, key=lambda d: (d.count, d.index)) if active else None
    return {
        "activeDays": len(active),
        "firstContribution": first.date.isoformat() if first else None,
        "daysSinceFirst": len(since_first),
        "activeShareSinceFirst": round(len(active) / len(since_first), 4) if since_first else None,
        "longestStreak": longest_streak(days).to_json(),
        "currentStreak": current_streak(days).to_json(),
        "bestDay": {"date": best.date.isoformat(), "count": best.count} if best else None,
        "meanPerActiveDay": round(sum(d.count for d in active) / len(active), 1) if active else None,
        "medianPerActiveDay": median(d.count for d in active) if active else None,
        "months": month_totals(days),
        "weekdays": [{"day": name, "total": total} for name, total in zip(WEEKDAYS, weekday_totals(days))],
        "levels": [
            {"min": lo, "max": hi, "days": n} for (lo, hi), n in zip(LEVELS, level_counts(days))
        ],
    }
