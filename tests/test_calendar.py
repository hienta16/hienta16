"""Contribution aggregation: streaks, months, weekdays, levels, validation."""

import unittest
from datetime import date

from catwalk.stats.calendar import (
    Calendar,
    CalendarError,
    current_streak,
    level_of,
    longest_streak,
    metrics,
    month_totals,
    weekday_totals,
)


def cal(counts, start=date(2026, 3, 1)):  # 1 March 2026 is a Sunday
    return Calendar(start, tuple(counts))


class CalendarModel(unittest.TestCase):
    def test_total_and_end(self):
        c = cal([1, 0, 3])
        self.assertEqual(c.total, 4)
        self.assertEqual(c.end, date(2026, 3, 3))

    def test_rejects_negative_or_non_integer_counts(self):
        for bad in ([1, -1], [1, 2.5], [True]):
            with self.assertRaises(CalendarError):
                cal(bad)

    def test_from_pairs_needs_consecutive_days(self):
        with self.assertRaises(CalendarError):
            Calendar.from_pairs([("2026-03-01", 1), ("2026-03-03", 1)])

    def test_from_json_checks_total_and_length(self):
        good = {"from": "2026-03-01", "to": "2026-03-03", "total": 4, "days": [1, 0, 3]}
        self.assertEqual(Calendar.from_json(good).total, 4)
        with self.assertRaises(CalendarError):
            Calendar.from_json({**good, "total": 5})
        with self.assertRaises(CalendarError):
            Calendar.from_json({**good, "to": "2026-03-04"})
        with self.assertRaises(CalendarError):
            Calendar.from_json({"from": "2026-03-01"})  # missing values

    def test_weeks_are_sunday_first_columns(self):
        c = cal([1] * 8)  # Sun 1 Mar … Sun 8 Mar
        days = c.days()
        self.assertEqual(days[0].row, 0)  # Sunday
        self.assertEqual(c.week_of(days[6]), 0)  # Saturday 7 Mar
        self.assertEqual(c.week_of(days[7]), 1)  # Sunday 8 Mar starts column 1
        self.assertEqual(c.weeks, 2)

    def test_last_weeks_keeps_whole_trailing_columns(self):
        c = cal([1] * 21)
        tail = c.last_weeks(2)
        self.assertEqual(tail.start, date(2026, 3, 8))
        self.assertEqual(len(tail.counts), 14)


class Streaks(unittest.TestCase):
    def test_longest_prefers_the_most_recent_tie(self):
        s = longest_streak(cal([1, 1, 0, 2, 2, 0]).days())
        self.assertEqual((s.length, s.start, s.end), (2, date(2026, 3, 4), date(2026, 3, 5)))
        self.assertFalse(s.running)

    def test_longest_running_to_the_last_day(self):
        s = longest_streak(cal([0, 1, 1, 1]).days())
        self.assertEqual(s.length, 3)
        self.assertTrue(s.running)

    def test_empty_calendar_has_no_streak(self):
        self.assertEqual(longest_streak(cal([0, 0]).days()).length, 0)

    def test_current_streak_survives_an_empty_today(self):
        s = current_streak(cal([0, 3, 4, 0]).days())
        self.assertEqual((s.length, s.today_pending), (2, True))
        self.assertEqual(s.end, date(2026, 3, 3))

    def test_current_streak_broken_yesterday_is_zero(self):
        s = current_streak(cal([5, 0, 0]).days())
        self.assertEqual(s.length, 0)


class Aggregates(unittest.TestCase):
    def test_month_totals_mark_partial_months(self):
        months = month_totals(cal([1] * 40).days())  # 1 Mar … 9 Apr
        self.assertEqual([m["month"] for m in months], ["2026-03", "2026-04"])
        self.assertEqual(months[0]["total"], 31)
        self.assertFalse(months[0]["partial"])
        self.assertTrue(months[1]["partial"])

    def test_weekday_totals_are_monday_first(self):
        totals = weekday_totals(cal([7, 1, 0, 0, 0, 0, 0]).days())  # Sunday 7, Monday 1
        self.assertEqual(totals, [1, 0, 0, 0, 0, 0, 7])

    def test_levels(self):
        self.assertEqual([level_of(n) for n in (0, 1, 5, 6, 15, 16, 40, 41, 999)], [0, 1, 1, 2, 2, 3, 3, 4, 4])

    def test_metrics_shape_and_values(self):
        m = metrics(cal([0, 0, 2, 0, 4, 6]))
        self.assertEqual(m["activeDays"], 3)
        self.assertEqual(m["firstContribution"], "2026-03-03")
        self.assertEqual(m["daysSinceFirst"], 4)
        self.assertEqual(m["activeShareSinceFirst"], 0.75)
        self.assertEqual(m["bestDay"], {"date": "2026-03-06", "count": 6})
        self.assertEqual(m["meanPerActiveDay"], 4.0)
        self.assertEqual(sum(lv["days"] for lv in m["levels"]), 6)

    def test_metrics_with_no_activity(self):
        m = metrics(cal([0, 0, 0]))
        self.assertIsNone(m["firstContribution"])
        self.assertIsNone(m["bestDay"])
        self.assertEqual(m["longestStreak"]["length"], 0)


if __name__ == "__main__":
    unittest.main()
