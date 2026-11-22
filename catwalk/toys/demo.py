"""`python -m catwalk toys demo`: an inspectable local demonstration of the toy box, with no GitHub involved.

Builds real-shaped GitHub `issues` event payloads for a handful of made-up visitors (logins start with
`example-`), feeds them through the exact code the workflow runs (parse_issue_event -> handle -> expire), and
prints what happened and why. With --write it saves the result as data/toys.demo.json, which the website can
show in preview mode (marked "Demo data") so you can see persisted toys before the toy box goes live.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from ..config import Paths, SiteConfig
from ..jsonio import write_json
from ..timeutil import iso
from . import engine
from .events import Ignored, parse_issue_event
from .models import ToyState
from .replies import reply_for
from .rules import ToyRules

# (hours before now, login, user id, account type, title, issue number)
SCRIPT = [
    (150, "example-visitor-1", 9000001, "User", "[cat-toy] yarn", 1),
    (148, "example-visitor-1", 9000001, "User", "[cat-toy] feather", 2),
    (72, "example-visitor-2", 9000002, "User", "[cat-toy] feather", 3),
    (40, "example-visitor-3", 9000003, "User", "[Cat-Toy]  Box", 4),
    (20, "example-visitor-2", 9000002, "User", "[cat-toy] laser pointer", 5),
    (5, "example-bot", 9000009, "Bot", "[cat-toy] yarn", 6),
    (3, "example-visitor-4", 9000004, "User", "[cat-toy] give a yarn ball", 8),
    (3, "example-visitor-4", 9000004, "User", "[cat-toy] give a yarn ball", 8),  # the same event delivered twice
    (2, "example-visitor-5", 9000005, "User", "Love the cat!", 9),  # an ordinary issue: not for the toy box
]


def payload(site: SiteConfig, hours_ago: float, login: str, uid: int, kind: str, title: str, number: int, now: datetime) -> dict:
    return {
        "action": "opened",
        "repository": {"full_name": site.hub_repo},
        "issue": {
            "number": number,
            "title": title,
            "body": "Anything here is ignored; <script>alert(1)</script> included.",
            "created_at": iso(now - timedelta(hours=hours_ago)),
            "user": {"login": login, "id": uid, "type": kind},
        },
    }


def run_demo(paths: Paths, rules: ToyRules, site: SiteConfig, *, write: bool, now: datetime) -> int:
    state = ToyState.empty(list(rules.kinds))
    print(f"Toy box demo at {iso(now)} (no GitHub calls; made-up visitors)\n")
    print(f"{'#':>3}  {'opened':>8}  {'visitor':<18} {'title':<28} outcome")
    for hours, login, uid, kind, title, number in SCRIPT:
        request = parse_issue_event(payload(site, hours, login, uid, kind, title, number, now), rules, site.hub_repo)
        if isinstance(request, Ignored):
            print(f"{number:>3}  {f'-{hours}h':>8}  {login:<18} {title[:28]:<28} ignored ({request.reason})")
            continue
        # replay each event at the moment it happened, so lifetimes and cooldowns play out as they would live
        at = now - timedelta(hours=hours) + timedelta(minutes=1)
        before = {g.id: g for g in state.active}
        state, decision = engine.handle(state, request, rules, at)
        after = {g.id for g in state.active} | {g.id for g in decision.displaced}
        for gone_id in sorted(set(before) - after):
            g = before[gone_id]
            print(f"     · the {g.toy} from #{g.issue} went back on the shelf (its time ran out at {iso(g.expires_at)})")
        extra = ""
        if decision.gift:
            extra = f" -> {decision.gift.toy} ({decision.gift.variant}) until {iso(decision.gift.expires_at)}"
        if decision.retry_after:
            extra = f" -> may give again after {iso(decision.retry_after)}"
        print(f"{number:>3}  {f'-{hours}h':>8}  {login:<18} {title[:28]:<28} {decision.outcome}{extra}")
        if decision.outcome == engine.ACCEPTED and number == 1:
            print("\n     bot reply to #1:\n     " + (reply_for(decision, rules, login, site.site_url) or "").replace("\n", "\n     ") + "\n")
    state, gone = engine.expire(state, now)
    print(f"\nExpired now: {', '.join(f'{g.toy} #{g.issue}' for g in gone) or 'none'}")
    live = engine.visible(state, now)
    print(f"In the scene: {len(live)} toy(s): " + ", ".join(f"{g.toy} from @{g.giver.login}" for g in live))
    print(f"Given so far: {sum(state.totals.values())} {dict(state.totals)}")
    if write:
        data = state.to_json()
        data["demo"] = True
        write_json(paths.toy_demo_state, data)
        print("\nwrote data/toys.demo.json (shown on the website only in preview mode, labelled Demo data)")
    return 0
