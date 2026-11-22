"""Command line: `python -m catwalk <command>`. Every GitHub Action step is one of these commands.

    refresh                 fetch GitHub stats into data/github.json (keeps last good sections on failure)
    render [--only ...]     draw assets/generated/*.svg and the generated parts of README.md from the data files
    toys handle --event F   process one GitHub `issues` event (the cat-toys workflow); writes data/toys.json
    toys respond --result F comment on and close the issue, from the result `toys handle` wrote
    toys expire             drop toys whose time is up (run by the refresh workflow)
    toys status             print the toy box
    toys demo               run sample events through the real rules, without GitHub (an inspectable local demo)
    check                   validate config and data files (used by the tests workflow)

Exit codes: 0 done (warnings are printed), 1 nothing could be done, 2 bad input.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from .config import Paths, load_site_config
from .jsonio import read_json, read_json_or, write_json
from .timeutil import iso, parse_ts, utcnow


def _now(args: argparse.Namespace) -> datetime:
    return parse_ts(args.now) if getattr(args, "now", None) else utcnow()


def _warn(message: str) -> None:
    prefix = "::warning::" if os.environ.get("GITHUB_ACTIONS") else "! "
    print(f"{prefix}{message}", file=sys.stderr)


# ---- refresh ---------------------------------------------------------------------------------------------------


def cmd_refresh(args: argparse.Namespace, paths: Paths) -> int:
    from .github import GitHubClient, discover_token
    from .stats.snapshot import SnapshotError, build_snapshot

    site = load_site_config(paths)
    previous = read_json_or(paths.github_data, None)
    client = GitHubClient(discover_token())
    try:
        snap = build_snapshot(client, site.login, previous, _now(args), public_only=args.public_only, log=print)
    except SnapshotError as exc:
        _warn(str(exc))
        return 0 if args.soft else 1
    for problem in snap["refresh"]["problems"]:
        _warn(problem)
    for note in snap["refresh"]["notes"]:
        print(f"  note: {note}")
    changed = write_json(paths.github_data, snap)
    cal, counts = snap["calendar"], snap["counts"] or {}
    print(
        f"{'wrote' if changed else 'unchanged'} data/github.json: {cal['total']:,} contributions "
        f"({cal['from']} to {cal['to']}), {counts.get('commitsLastYear', '?')} commits authored, scope {counts.get('scope', '?')}"
    )
    return 0


# ---- render ----------------------------------------------------------------------------------------------------


def cmd_render(args: argparse.Namespace, paths: Paths) -> int:
    from .render import render_all

    only = {x.strip() for x in args.only.split(",")} if args.only else None
    written = render_all(paths, only=only, now=_now(args))
    for name, changed in written:
        print(f"{'wrote' if changed else 'same '} {name}")
    return 0


# ---- toys ------------------------------------------------------------------------------------------------------


def cmd_toys(args: argparse.Namespace, paths: Paths) -> int:
    from . import toys
    from .toys import replies
    from .toys.store import load_state, save_state

    rules = toys.load_rules(paths.toy_rules)
    site = load_site_config(paths)
    now = _now(args)

    if args.toys_command == "handle":
        payload = read_json(Path(args.event))
        result: dict = {"outcome": "ignored", "issue": None, "toy": None, "login": None, "changed": False}
        try:
            request = toys.parse_issue_event(payload, rules, site.hub_repo)
        except toys.EventError as exc:
            print(f"bad event: {exc}", file=sys.stderr)
            return 2
        if isinstance(request, toys.Ignored):
            print(f"ignored: {request.reason}")
        else:
            state = load_state(paths.toy_state, rules)
            new, decision = toys.handle(state, request, rules, now)
            changed = save_state(paths.toy_state, new) if new != state else False
            result = {
                "outcome": decision.outcome,
                "issue": request.issue,
                "toy": decision.toy,
                "login": request.login,
                "changed": changed,
                "expiresAt": iso(decision.gift.expires_at) if decision.gift else None,
                "retryAfter": iso(decision.retry_after) if decision.retry_after else None,
                "displaced": [g.id for g in decision.displaced],
                "reply": replies.reply_for(decision, rules, request.login, site.site_url),
                "close": replies.close_reason(decision.outcome),
            }
            print(f"#{request.issue} from @{request.login}: {decision.outcome}" + (f" ({decision.toy})" if decision.toy else ""))
        if args.result:
            write_json(Path(args.result), result)
        return 0

    if args.toys_command == "commit-message":
        r = read_json_or(Path(args.result), {}) or {}
        print(replies.commit_message(str(r.get("outcome", "")), r.get("issue"), r.get("toy"), r.get("login")))
        return 0

    if args.toys_command == "respond":
        return _respond(args, rules, site)

    if args.toys_command == "expire":
        state = load_state(paths.toy_state, rules)
        new, gone = toys.expire(state, now)
        new = toys.prune(new, rules, now)
        changed = save_state(paths.toy_state, new) if new != state else False
        print(f"expired {len(gone)} toy(s); {'wrote' if changed else 'unchanged'} data/toys.json")
        return 0

    if args.toys_command == "status":
        state = load_state(paths.toy_state, rules)
        live = toys.visible(state, now)
        print(f"{len(live)} toy(s) in the scene, {sum(state.totals.values())} given in total {dict(state.totals)}")
        for g in live:
            print(f"  {g.toy:<8} {g.variant:<7} from @{g.giver.login:<20} until {iso(g.expires_at)}")
        return 0

    if args.toys_command == "demo":
        from .toys.demo import run_demo

        return run_demo(paths, rules, site, write=args.write, now=now)
    return 2


def _respond(args: argparse.Namespace, rules, site) -> int:
    """Comment on and close the issue. Runs with the workflow's own GITHUB_TOKEN (the bot), never a personal token."""
    from .github import GitHubClient, GitHubError, discover_token
    from .toys import replies

    result = read_json_or(Path(args.result), None)
    pushed = Path(args.pushed_marker).exists() if args.pushed_marker else True
    if not isinstance(result, dict) or not result.get("issue"):
        print("nothing to answer (ignored or failed before a decision)")
        return 0
    outcome = str(result.get("outcome"))
    body, reason = result.get("reply"), result.get("close")
    if not pushed and outcome != "duplicate":
        outcome = replies.BUSY
        body, reason = replies.reply_for(None, rules, str(result.get("login")), site.site_url, outcome=outcome), replies.close_reason(outcome)
    if not body and not reason:
        print(f"#{result['issue']}: {outcome}, no reply needed")
        return 0
    token = discover_token(("GITHUB_TOKEN",), use_gh_cli=False)
    if not token:
        print("GITHUB_TOKEN is not set; printing the reply instead:\n" + str(body))
        return 0
    client = GitHubClient(token)
    number = int(result["issue"])
    try:
        if body:
            client.rest(f"repos/{site.hub_repo}/issues/{number}/comments", method="POST", payload={"body": body})
        if reason:
            client.rest(f"repos/{site.hub_repo}/issues/{number}", method="PATCH", payload={"state": "closed", "state_reason": reason})
    except GitHubError as exc:
        _warn(f"could not answer #{number}: {exc}")
        return 1
    print(f"#{number}: answered ({outcome}) and closed as {reason}")
    return 0


# ---- check -----------------------------------------------------------------------------------------------------


def cmd_check(args: argparse.Namespace, paths: Paths) -> int:
    from .stats.calendar import Calendar
    from .toys import load_rules
    from .toys.store import load_state

    problems = []
    try:
        load_site_config(paths)
    except (OSError, ValueError) as exc:
        problems.append(f"config/catwalk.json: {exc}")
    try:
        rules = load_rules(paths.toy_rules)
        load_state(paths.toy_state, rules)
    except (OSError, ValueError) as exc:
        problems.append(f"toys: {exc}")
    snap = read_json_or(paths.github_data, None)
    if snap is not None:
        try:
            Calendar.from_json(snap["calendar"])
        except (KeyError, TypeError, ValueError) as exc:
            problems.append(f"data/github.json: {exc}")
    for p in problems:
        print(f"x {p}")
    print("ok" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


# ---- wiring ----------------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m catwalk", description="Hien Ta's GitHub profile automation")
    parser.add_argument("--root", help="repository root (default: this checkout)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("refresh", help="fetch GitHub stats into data/github.json")
    p.add_argument("--public-only", action="store_true", help="count only what an anonymous visitor could count")
    p.add_argument("--soft", action="store_true", help="never fail (keep the old file if GitHub cannot be read)")
    p.add_argument("--now", help=argparse.SUPPRESS)

    p = sub.add_parser("render", help="draw the SVGs and README sections")
    p.add_argument("--only", help="comma list: banner,stats,iso,beat,languages,rhythm,toybox,buttons,site,readme")
    p.add_argument("--now", help=argparse.SUPPRESS)

    p = sub.add_parser("toys", help="the cat's toy box")
    tsub = p.add_subparsers(dest="toys_command", required=True)
    t = tsub.add_parser("handle", help="process one issues event")
    t.add_argument("--event", required=True, help="path to the event JSON (GITHUB_EVENT_PATH)")
    t.add_argument("--result", help="where to write the decision for the respond step")
    t.add_argument("--now", help="pretend the time is this (tests and demos)")
    t = tsub.add_parser("respond", help="comment on and close the processed issue")
    t.add_argument("--result", required=True)
    t.add_argument("--pushed-marker", help="file that exists only if the state change was pushed")
    t = tsub.add_parser("commit-message", help="print the commit message for a result")
    t.add_argument("--result", required=True)
    for name in ("expire", "status"):
        t = tsub.add_parser(name)
        t.add_argument("--now")
    t = tsub.add_parser("demo", help="run sample visitors through the real rules")
    t.add_argument("--write", action="store_true", help="also save the result as data/toys.demo.json for the website preview")
    t.add_argument("--now")

    sub.add_parser("check", help="validate config and data files")
    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # Windows consoles default to a legacy code page
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")
    args = build_parser().parse_args(argv)
    paths = Paths(Path(args.root).resolve()) if args.root else Paths.default()
    handlers = {"refresh": cmd_refresh, "render": cmd_render, "toys": cmd_toys, "check": cmd_check}
    try:
        return handlers[args.command](args, paths)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"x {exc}", file=sys.stderr)
        return 2
