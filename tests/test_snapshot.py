"""The GitHub snapshot: public-page parsing, the privacy check, missing values and failures, scope handling."""

import unittest
from datetime import date

from catwalk.github import GitHubClient, GitHubError, RateLimited, parse_public_calendar
from catwalk.github.client import Response
from catwalk.stats.calendar import Calendar, CalendarError
from catwalk.stats.snapshot import COMPLETE, PUBLIC, SnapshotError, build_snapshot, verify_against_public

from helpers import FakeGitHub, at, public_page

NOW = at("2026-01-14T12:00:00Z")


class PublicCalendarParser(unittest.TestCase):
    def test_reads_counts_including_thousands_and_none(self):
        html = public_page(date(2026, 1, 1), [0, 1, 36, 1234])
        self.assertEqual(
            parse_public_calendar(html),
            {"2026-01-01": 0, "2026-01-02": 1, "2026-01-03": 36, "2026-01-04": 1234},
        )

    def test_only_the_leading_number_counts(self):
        # regression: "36 contributions on September 6th." once parsed as 366
        html = '<td data-date="2026-09-06" id="contribution-day-component-0-0"></td><tool-tip for="contribution-day-component-0-0">36 contributions on September 6th.</tool-tip>'
        self.assertEqual(parse_public_calendar(html), {"2026-09-06": 36})

    def test_unreadable_tooltip_is_none_not_a_guess(self):
        html = '<td data-date="2026-09-06" id="contribution-day-component-0-0"></td><tool-tip for="contribution-day-component-0-0">lots</tool-tip>'
        self.assertEqual(parse_public_calendar(html), {"2026-09-06": None})


class PrivacyCheck(unittest.TestCase):
    def test_identical_calendars_pass(self):
        c = Calendar(date(2026, 1, 1), (1, 0, 2, 3, 0, 0, 1, 0))
        public = {d.date.isoformat(): d.count for d in c.days()}
        self.assertEqual(verify_against_public(c, public)[0], c)

    def test_any_earlier_difference_refuses(self):
        c = Calendar(date(2026, 1, 1), (1, 0, 2, 3, 0, 0, 1, 0))
        public = {d.date.isoformat(): d.count for d in c.days()}
        public["2026-01-03"] = 0  # the API shows a day the public cannot see
        with self.assertRaises(CalendarError):
            verify_against_public(c, public)

    def test_today_takes_the_smaller_value(self):
        c = Calendar(date(2026, 1, 1), (1, 0, 2, 3, 0, 0, 1, 5))
        public = {d.date.isoformat(): d.count for d in c.days()}
        public["2026-01-08"] = 4
        fixed, notes = verify_against_public(c, public)
        self.assertEqual(fixed.counts[-1], 4)
        self.assertTrue(notes)

    def test_yesterday_may_still_be_settling_too(self):
        c = Calendar(date(2026, 1, 1), (1, 0, 2, 3, 0, 0, 7, 5))
        public = {d.date.isoformat(): d.count for d in c.days()}
        public["2026-01-07"] = 6  # the cached page lags on the latest activity
        fixed, _ = verify_against_public(c, public)
        self.assertEqual(fixed.counts[-2:], (6, 5))
        public["2026-01-04"] = 0  # but a day further back is a real difference
        with self.assertRaises(CalendarError):
            verify_against_public(c, public)

    def test_unreadable_page_refuses(self):
        c = Calendar(date(2026, 1, 1), tuple([1] * 30))
        with self.assertRaises(CalendarError):
            verify_against_public(c, {})


class Snapshot(unittest.TestCase):
    def test_complete_snapshot(self):
        fake = FakeGitHub()
        snap = build_snapshot(fake.client(), "hienta16", None, NOW)
        self.assertTrue(snap["refresh"]["ok"])
        self.assertEqual(snap["calendar"]["total"], sum(fake.counts))
        self.assertEqual(snap["counts"]["scope"], COMPLETE)
        self.assertEqual(snap["counts"]["commitsLastYear"], 42)
        self.assertEqual(snap["counts"]["pullRequestsLastYear"], 7)
        self.assertEqual(snap["repositories"]["stars"], 5)
        self.assertEqual(snap["repositories"]["languages"]["byBytes"][0]["name"], "Python")
        self.assertEqual(snap["metrics"]["activeDays"], 8)
        self.assertNotIn("name", snap["repositories"])  # no repository names anywhere

    def test_mismatch_with_public_page_keeps_previous_calendar(self):
        good = build_snapshot(FakeGitHub().client(), "hienta16", None, NOW)
        hidden = FakeGitHub(public=[0] * 14)  # the profile hides contributions from strangers
        snap = build_snapshot(hidden.client(), "hienta16", good, NOW)
        self.assertEqual(snap["calendar"], good["calendar"])
        self.assertFalse(snap["refresh"]["ok"])
        self.assertTrue(any(p.startswith("calendar:") for p in snap["refresh"]["problems"]))

    def test_no_calendar_and_nothing_to_keep_raises(self):
        broken = FakeGitHub(fail={"contributionCalendar": 502})
        with self.assertRaises(SnapshotError):
            build_snapshot(broken.client(), "hienta16", None, NOW)

    def test_a_failed_section_keeps_its_last_value(self):
        good = build_snapshot(FakeGitHub().client(), "hienta16", None, NOW)
        flaky = FakeGitHub(fail={"/search/": 503})
        snap = build_snapshot(flaky.client(), "hienta16", good, at("2026-01-14T18:00:00Z"))
        self.assertEqual(snap["counts"], good["counts"])  # asOf still says when it was true
        self.assertEqual(snap["calendar"]["asOf"], "2026-01-14T18:00:00Z")
        self.assertIn("counts:", " ".join(snap["refresh"]["problems"]))

    def test_missing_section_without_history_is_null_not_zero(self):
        snap = build_snapshot(FakeGitHub(fail={"/search/": 503}).client(), "hienta16", None, NOW)
        self.assertIsNone(snap["counts"])

    def test_public_only_token_never_overwrites_complete_counts(self):
        good = build_snapshot(FakeGitHub().client(), "hienta16", None, NOW)
        workflow_token = FakeGitHub(viewer="github-actions[bot]")
        snap = build_snapshot(workflow_token.client(), "hienta16", good, NOW)
        self.assertEqual(snap["counts"], good["counts"])
        self.assertEqual(snap["counts"]["scope"], COMPLETE)

    def test_public_scope_adds_is_public_to_searches(self):
        fake = FakeGitHub(viewer="someone-else")
        snap = build_snapshot(fake.client(), "hienta16", None, NOW)
        self.assertEqual(snap["counts"]["scope"], PUBLIC)
        self.assertTrue(all("is%3Apublic" in c for c in fake.calls if "/search/" in c))
        self.assertEqual(snap["repositories"]["total"], 1)  # the private repository is left out


class Client(unittest.TestCase):
    def test_rate_limit_raises_without_retrying(self):
        calls = []

        def transport(*args):
            calls.append(args)
            return Response(403, {"x-ratelimit-remaining": "0", "x-ratelimit-reset": "1700000000"}, b"API rate limit exceeded")

        with self.assertRaises(RateLimited):
            GitHubClient("t", transport=transport, sleep=lambda _s: None).rest("search/commits")
        self.assertEqual(len(calls), 1)

    def test_server_errors_are_retried_then_reported(self):
        calls = []

        def transport(*args):
            calls.append(args)
            return Response(502)

        with self.assertRaises(GitHubError):
            GitHubClient("t", transport=transport, retries=2, sleep=lambda _s: None).rest("x")
        self.assertEqual(len(calls), 3)

    def test_writes_are_never_retried_so_nothing_is_posted_twice(self):
        calls = []

        def transport(*args):
            calls.append(args)
            return Response(502)

        client = GitHubClient("t", transport=transport, retries=3, sleep=lambda _s: None)
        with self.assertRaises(GitHubError):
            client.rest("repos/x/y/issues/1/comments", method="POST", payload={"body": "hi"})
        self.assertEqual(len(calls), 1)

    def test_token_is_never_sent_off_api_github_com(self):
        seen = {}

        def transport(method, url, headers, body, timeout):
            seen[url] = dict(headers)
            return Response(200, {}, b"<html></html>")

        GitHubClient("secret", transport=transport).fetch_page("https://github.com/users/x/contributions")
        self.assertNotIn("Authorization", seen["https://github.com/users/x/contributions"])
        self.assertNotIn("secret", repr(GitHubClient("secret")))


if __name__ == "__main__":
    unittest.main()
