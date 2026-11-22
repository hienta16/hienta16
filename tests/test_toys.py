"""The toy box: issue validation, one gift per day, lifetimes and expiry, duplicates, the display cap, state files."""

import json
import unittest
from datetime import timedelta

from catwalk.config import Paths
from catwalk.toys import (
    ACCEPTED,
    COOLDOWN,
    DUPLICATE,
    NOT_A_PERSON,
    STALE,
    UNKNOWN_TOY,
    EventError,
    GiftRequest,
    Ignored,
    StateError,
    ToyRules,
    ToyState,
    expire,
    handle,
    load_rules,
    parse_issue_event,
    parse_toy_title,
    prune,
    visible,
)
from catwalk.toys.replies import close_reason, reply_for
from catwalk.toys.store import load_state, save_state

from helpers import ROOT, at, temp_root

RULES = load_rules(Paths(ROOT).toy_rules)
REPO = "hienta16/hienta16"
NOW = at("2026-12-01T12:00:00Z")


def event(title="[cat-toy] yarn", login="visitor", uid=101, kind="User", number=1, created="2026-12-01T11:59:00Z", **over):
    issue = {"number": number, "title": title, "body": "ignored", "created_at": created, "user": {"login": login, "id": uid, "type": kind}}
    issue.update(over.pop("issue", {}))
    payload = {"action": "opened", "repository": {"full_name": REPO}, "issue": issue}
    payload.update(over)
    return payload


def request(**kw):
    req = parse_issue_event(event(**kw), RULES, REPO)
    assert isinstance(req, GiftRequest), req
    return req


def give(state, now=NOW, **kw):
    return handle(state, request(**kw), RULES, now)


def empty():
    return ToyState.empty(list(RULES.kinds))


class Titles(unittest.TestCase):
    def test_accepted_spellings(self):
        for title, toy in [
            ("[cat-toy] yarn", "yarn"),
            ("[CAT-TOY]   Yarn ball", "yarn"),
            ("[cat-toy] give a box", "box"),
            ("[cat-toy] feather toy!", "feather"),
        ]:
            self.assertEqual(parse_toy_title(title, RULES), (True, toy), title)

    def test_prefix_without_a_known_toy(self):
        for title in ("[cat-toy] laser", "[cat-toy] yarn; rm -rf /", "[cat-toy] $(curl evil)", "[cat-toy] " + "yarn " * 40):
            self.assertEqual(parse_toy_title(title, RULES), (True, None), title)

    def test_not_a_toy_request(self):
        for title in ("yarn please", "Re: [cat-toy] yarn", "", None):
            self.assertEqual(parse_toy_title(title, RULES), (False, None))


class Events(unittest.TestCase):
    def test_valid_event(self):
        req = request()
        self.assertEqual((req.issue, req.login, req.user_id, req.toy), (1, "visitor", 101, "yarn"))

    def test_ignored_events(self):
        cases = [
            event(action="edited"),
            event(repository={"full_name": "someone/fork"}),
            event(issue={"pull_request": {"url": "x"}}),
            event(title="Hello there"),
        ]
        for payload in cases:
            self.assertIsInstance(parse_issue_event(payload, RULES, REPO), Ignored)

    def test_malformed_events_raise(self):
        cases = [
            "not a dict",
            {"action": "opened", "repository": {"full_name": REPO}},
            event(issue={"user": None}),
            event(login="bad login!"),
            event(uid=0),
            event(uid="101"),
            event(number=-3),
            event(created="yesterday"),
            event(created="2026-12-01T11:59:00"),  # no time zone
        ]
        for payload in cases:
            with self.assertRaises(EventError):
                parse_issue_event(payload, RULES, REPO)

    def test_the_body_is_never_used(self):
        a = request()
        b = parse_issue_event(event(issue={"body": "[cat-toy] box\n<script>alert(1)</script>"}), RULES, REPO)
        self.assertEqual(a, b)


class Rules(unittest.TestCase):
    def test_accepted_gift_has_utc_lifetime(self):
        state, d = give(empty())
        self.assertEqual(d.outcome, ACCEPTED)
        self.assertEqual(d.gift.created_at, at("2026-12-01T11:59:00Z"))
        self.assertEqual(d.gift.expires_at, at("2026-12-08T11:59:00Z"))  # yarn: 7 days
        self.assertEqual(state.totals["yarn"], 1)
        self.assertEqual(len(visible(state, NOW)), 1)

    def test_lifetimes_per_toy(self):
        for toy, hours in (("yarn", 168), ("feather", 48), ("box", 336)):
            _, d = give(empty(), title=f"[cat-toy] {toy}")
            self.assertEqual(d.gift.expires_at - d.gift.created_at, timedelta(hours=hours), toy)

    def test_one_gift_per_account_per_rolling_24_hours(self):
        state, _ = give(empty(), number=1, created="2026-12-01T10:00:00Z")
        state, d = give(state, number=2, created="2026-12-02T09:59:59Z", now=at("2026-12-02T10:00:00Z"))
        self.assertEqual(d.outcome, COOLDOWN)
        self.assertEqual(d.retry_after, at("2026-12-02T10:00:00Z"))
        state, d = give(state, number=3, created="2026-12-02T10:00:00Z", now=at("2026-12-02T10:01:00Z"))
        self.assertEqual(d.outcome, ACCEPTED)  # exactly 24 hours later is allowed

    def test_cooldown_uses_the_account_id_not_the_login(self):
        state, _ = give(empty(), number=1, login="old-name", uid=7)
        _, d = give(state, number=2, login="new-name", uid=7, created="2026-12-01T11:59:30Z")
        self.assertEqual(d.outcome, COOLDOWN)
        _, d = give(state, number=3, login="old-name", uid=8, created="2026-12-01T11:59:30Z")
        self.assertEqual(d.outcome, ACCEPTED)  # a different account that took the old login

    def test_cooldown_does_not_depend_on_processing_order(self):
        later, _ = give(empty(), number=2, created="2026-12-01T11:00:00Z")
        _, d = give(later, number=1, created="2026-12-01T09:00:00Z")  # the earlier issue arrives second
        self.assertEqual(d.outcome, COOLDOWN)

    def test_refusals_do_not_count_towards_the_cooldown(self):
        state, d = give(empty(), number=1, title="[cat-toy] laser")
        self.assertEqual(d.outcome, UNKNOWN_TOY)
        _, d = give(state, number=2, created="2026-12-01T11:59:30Z")
        self.assertEqual(d.outcome, ACCEPTED)

    def test_bots_are_refused(self):
        _, d = give(empty(), kind="Bot", login="helper[bot]")
        self.assertEqual(d.outcome, NOT_A_PERSON)
        _, d = give(empty(), kind="Organization")
        self.assertEqual(d.outcome, NOT_A_PERSON)

    def test_exempt_logins_skip_the_cooldown(self):
        rules = ToyRules.from_dict({**json.loads((ROOT / "config" / "toys.json").read_text()), "exempt_logins": ["Hienta16"]})
        state, _ = handle(empty(), request(login="hienta16", number=1), rules, NOW)
        _, d = handle(state, request(login="hienta16", number=2, created="2026-12-01T11:59:30Z"), rules, NOW)
        self.assertEqual(d.outcome, ACCEPTED)

    def test_duplicate_events_change_nothing(self):
        state, _ = give(empty(), number=5)
        again, d = give(state, number=5)
        self.assertEqual(d.outcome, DUPLICATE)
        self.assertEqual(again, state)
        self.assertIsNone(reply_for(d, RULES, "visitor", "https://x"))
        self.assertIsNone(close_reason(d.outcome))

    def test_refused_requests_are_remembered_as_duplicates_too(self):
        state, _ = give(empty(), number=5, title="[cat-toy] laser")
        _, d = give(state, number=5, title="[cat-toy] laser")
        self.assertEqual(d.outcome, DUPLICATE)

    def test_stale_events_are_skipped_without_a_trace(self):
        state, d = give(empty(), created="2026-10-01T00:00:00Z")
        self.assertEqual(d.outcome, STALE)
        self.assertEqual(state, empty())

    def test_future_timestamps_are_clamped(self):
        _, d = give(empty(), created="2027-01-01T00:00:00Z")
        self.assertLessEqual(d.gift.created_at, NOW + timedelta(minutes=5))

    def test_full_scene_puts_the_oldest_toy_away_but_keeps_the_count(self):
        state = empty()
        for i in range(RULES.max_visible):
            state, _ = give(state, number=i + 1, uid=1000 + i, created=f"2026-12-01T0{i % 10}:00:00Z")
        state, d = give(state, number=99, uid=5000)
        self.assertEqual(len(d.displaced), 1)
        self.assertEqual(d.displaced[0].issue, 1)
        self.assertEqual(len(visible(state, NOW)), RULES.max_visible)
        self.assertEqual(state.totals["yarn"], RULES.max_visible + 1)


class Expiry(unittest.TestCase):
    def test_toys_leave_exactly_at_expires_at(self):
        state, d = give(empty(), title="[cat-toy] feather")
        end = d.gift.expires_at
        kept, gone = expire(state, end - timedelta(seconds=1))
        self.assertEqual((len(kept.active), gone), (1, []))
        kept, gone = expire(state, end)
        self.assertEqual((len(kept.active), len(gone)), (0, 1))
        self.assertEqual(kept.totals["feather"], 1)  # history is kept

    def test_prune_forgets_old_ledger_entries_only(self):
        state, _ = give(empty(), number=1)
        later = NOW + RULES.history + timedelta(minutes=5)
        self.assertEqual(prune(state, RULES, NOW).ledger, state.ledger)
        self.assertEqual(prune(state, RULES, later).ledger, ())

    def test_handle_drops_toys_that_ran_out(self):
        state, _ = give(empty(), number=1, title="[cat-toy] feather")
        later = NOW + timedelta(hours=49)
        state, _ = give(state, number=2, uid=202, created="2026-12-03T12:59:00Z", now=later)
        self.assertEqual([g.toy for g in visible(state, later)], ["yarn"])


class StateFiles(unittest.TestCase):
    def test_round_trip_is_exact_and_deterministic(self):
        state, _ = give(empty(), number=3)
        state, _ = give(state, number=4, uid=202, title="[cat-toy] box", created="2026-12-01T11:58:00Z")
        raw = state.to_json()
        again = ToyState.from_json(json.loads(json.dumps(raw)), list(RULES.kinds))
        self.assertEqual(again, state)
        self.assertEqual(again.to_json(), raw)
        self.assertEqual([g["issue"] for g in raw["active"]], [4, 3])  # ordered by creation time

    def test_save_and_load(self):
        paths = temp_root()
        state, _ = give(empty())
        self.assertTrue(save_state(paths.toy_state, state))
        self.assertFalse(save_state(paths.toy_state, state))  # unchanged: nothing rewritten
        self.assertEqual(load_state(paths.toy_state, RULES), state)

    def test_missing_file_is_an_empty_box(self):
        self.assertEqual(load_state(temp_root().toy_state, RULES), empty())

    def test_malformed_state_is_refused(self):
        good = give(empty())[0].to_json()
        bad_cases = [
            [],
            {**good, "schema": 99},
            {**good, "active": [{"id": "x"}]},
            {**good, "totals": {"yarn": -1}},
            {**good, "ledger": good["ledger"] * 2},
            {**good, "active": [{**good["active"][0], "giver": {"login": "<img src=x>", "id": 1}}]},
        ]
        for raw in bad_cases:
            with self.assertRaises(StateError):
                ToyState.from_json(raw, list(RULES.kinds))


class Config(unittest.TestCase):
    def test_rules_reject_nonsense(self):
        base = json.loads((ROOT / "config" / "toys.json").read_text())
        for change in (
            {"cooldown_hours": 0},
            {"max_visible": 500},
            {"history_days": 0},
            {"toys": {}},
            {"toys": {"Yarn!": base["toys"]["yarn"]}},
            {"toys": {"yarn": {**base["toys"]["yarn"], "lifetime_hours": -1}}},
        ):
            with self.assertRaises(ValueError, msg=str(change)):
                ToyRules.from_dict({**base, **change})

    def test_replies_never_echo_the_title(self):
        state, d = give(empty(), title="[cat-toy] laser <b>bold</b>")
        self.assertNotIn("laser", reply_for(d, RULES, "visitor", "https://x"))


if __name__ == "__main__":
    unittest.main()
